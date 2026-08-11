import base64
import binascii
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ai.adapters import default_adapter_registry
from .ai.cloudflare_execution import MAX_RESPONSE_BYTES, register_cloudflare_executions
from .ai.credential_resolution import CredentialResolutionError, CredentialResolver, ExecutionContext
from .ai.gemini_execution import register_gemini_execution
from .ai.provider_executor import ProviderExecutionError, ProviderExecutionRegistry, ProviderExecutor
from .ai.provider_registry import PROVIDER_CONFIGURATION_VERSION, RegistryValidationError
from .ai.routing import DryRunProviderRouter, RoutingConfiguration, RoutingValidationError
from .internal_text_execution import InternalExecutionFailure, _credential_failure, _execution_failure, _routing_failure
from ..config import Settings

MAX_DECODED_IMAGE_BYTES = MAX_RESPONSE_BYTES

_ROUTING_TEXT_PROVIDER = "cloudflare"
_ROUTING_TEXT_MODEL = "@cf/meta/llama-3.1-8b-instruct"
_PROMPT_FIELDS = ("prompt", "image_prompt", "imagePrompt", "visual_prompt", "visualPrompt")


class InternalImageInput(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    prompt: str | None = None
    image_prompt: str | None = None
    imagePrompt: str | None = None
    visual_prompt: str | None = None
    visualPrompt: str | None = None
    scene_id: str | None = None
    scene_index: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1, le=2048)
    height: int | None = Field(default=None, ge=1, le=2048)
    steps: int | None = Field(default=None, ge=1, le=50)
    seed: int | None = Field(default=None, ge=0, le=2**32 - 1)

    @model_validator(mode="after")
    def _require_prompt(self) -> "InternalImageInput":
        if not self._resolved_prompt():
            raise ValueError("a prompt is required")
        return self

    def _resolved_prompt(self) -> str:
        for field in _PROMPT_FIELDS:
            value = getattr(self, field)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""


class InternalImageExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    job_id: UUID
    provider_id: str
    model_id: str
    credential_source: Literal["environment", "stored"]
    operation: Literal["image_generation"]
    input: InternalImageInput
    routing_version: str
    request_id: UUID


class InternalImageExecutionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    request_id: UUID
    job_id: UUID
    provider_id: str
    model_id: str
    capability: Literal["image_generation"]
    status: Literal["completed"]
    image_base64: str
    format: str = "png"
    width: int | None = None
    height: int | None = None
    scene_id: str | None = None
    scene_index: int | None = None
    elapsed_ms: float | None = None
    routing_version: str


class InternalImageExecutionService:
    def __init__(self, settings: Settings, database: object, encryption: object | None):
        self._settings = settings
        self._database = database
        self._encryption = encryption
        self._adapters = default_adapter_registry()
        self._execution_registry = ProviderExecutionRegistry()
        register_gemini_execution(self._execution_registry)
        register_cloudflare_executions(self._execution_registry)

    async def execute(self, request: InternalImageExecutionRequest) -> InternalImageExecutionResponse:
        decision = self._route(request)
        credential = self._resolve_credential(request, decision)
        context = ExecutionContext(decision, (credential,), job_id=str(request.job_id))
        executor = ProviderExecutor(self._execution_registry)
        prompt = request.input._resolved_prompt()
        try:
            adapter = self._adapters.get(request.provider_id)
            prepared = executor.prepare(
                adapter=adapter,
                context=context,
                capability="image_generation",
                model_id=request.model_id,
                parameters={"prompt": prompt},
                request_id=str(request.request_id),
            )
        except ProviderExecutionError as exc:
            raise _execution_failure(exc.code) from None
        except Exception:
            raise _execution_failure("execution_error") from None

        result = await executor.execute(prepared)
        if result.error is not None:
            raise _execution_failure(result.error.code)
        if result.output is None or not result.output.text or not result.output.text.strip():
            raise _execution_failure("empty_response")
        _validate_image_payload(result.output.text)
        return InternalImageExecutionResponse(
            request_id=request.request_id,
            job_id=request.job_id,
            provider_id=request.provider_id,
            model_id=request.model_id,
            capability="image_generation",
            status="completed",
            image_base64=result.output.text,
            format="png",
            width=request.input.width,
            height=request.input.height,
            scene_id=request.input.scene_id,
            scene_index=request.input.scene_index,
            elapsed_ms=result.output.elapsed_ms,
            routing_version=request.routing_version,
        )

    def _route(self, request: InternalImageExecutionRequest):
        if request.routing_version != PROVIDER_CONFIGURATION_VERSION:
            raise InternalExecutionFailure("AI_MODEL_NOT_ALLOWED", "request is not allowed", 422, False)
        router = DryRunProviderRouter(self._settings)
        configuration = RoutingConfiguration(
            text_provider=_ROUTING_TEXT_PROVIDER,
            text_model=_ROUTING_TEXT_MODEL,
            visual_source="ai",
            image_provider=request.provider_id,
            image_model=request.model_id,
            credential_source="environment",
            provider_configuration_version=request.routing_version,
        )
        try:
            decision = router.resolve(configuration)
        except RoutingValidationError as exc:
            raise _routing_failure(exc.code) from None
        except RegistryValidationError as exc:
            raise _routing_failure(exc.code) from None
        return decision.__class__(
            text_provider=decision.text_provider,
            text_model=decision.text_model,
            visual_source=decision.visual_source,
            image_provider=decision.image_provider,
            image_model=decision.image_model,
            credential_strategy=request.credential_source,
            routing_version=decision.routing_version,
        )

    def _resolve_credential(self, request: InternalImageExecutionRequest, decision):
        resolver = CredentialResolver(self._settings, self._database, self._encryption)
        try:
            return resolver.resolve(decision, request.credential_source, request.provider_id)
        except CredentialResolutionError as exc:
            raise _credential_failure(exc.code) from None
        except Exception:
            raise _credential_failure("credential_configuration_error") from None


def _validate_image_payload(image: str) -> None:
    try:
        decoded = base64.b64decode(image, validate=True)
    except (ValueError, binascii.Error, TypeError):
        raise _execution_failure("malformed_response") from None
    if not decoded:
        raise _execution_failure("empty_response") from None
    if len(decoded) > MAX_DECODED_IMAGE_BYTES:
        raise _execution_failure("malformed_response") from None
