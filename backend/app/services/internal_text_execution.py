from dataclasses import dataclass, replace
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .ai.adapters import default_adapter_registry
from .ai.cloudflare_execution import register_cloudflare_executions
from .ai.credential_resolution import CredentialResolutionError, CredentialResolver, ExecutionContext
from .ai.gemini_execution import register_gemini_execution
from .ai.provider_executor import ProviderExecutionError, ProviderExecutionRegistry, ProviderExecutor
from .ai.provider_registry import DEFAULT_IMAGE_MODEL, DEFAULT_IMAGE_PROVIDER, PROVIDER_CONFIGURATION_VERSION, RegistryValidationError
from .ai.routing import DryRunProviderRouter, RoutingConfiguration, RoutingValidationError
from ..config import Settings


class InternalTextInput(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    prompt: str = Field(min_length=1)
    system_prompt: str | None = None
    temperature: float = Field(default=0.6, ge=0, le=2)
    max_output_tokens: int = Field(default=8192, gt=0)
    response_format: Literal["text", "json"] = "text"


class InternalTextExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    job_id: UUID
    provider_id: str
    model_id: str
    credential_source: Literal["environment", "stored"]
    operation: Literal["text_generation"]
    input: InternalTextInput
    routing_version: str
    request_id: UUID


class InternalTextExecutionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    request_id: UUID
    job_id: UUID
    provider_id: str
    model_id: str
    capability: Literal["text_generation"]
    status: Literal["completed"]
    text: str
    finish_reason: str | None = None
    usage: dict[str, int] = {}
    elapsed_ms: float | None = None
    routing_version: str


@dataclass(frozen=True)
class InternalExecutionFailure(Exception):
    code: str
    message: str
    status_code: int
    retryable: bool


class InternalTextExecutionService:
    def __init__(self, settings: Settings, database: object, encryption: object | None):
        self._settings = settings
        self._database = database
        self._encryption = encryption
        self._adapters = default_adapter_registry()
        self._execution_registry = ProviderExecutionRegistry()
        register_gemini_execution(self._execution_registry)
        register_cloudflare_executions(self._execution_registry)

    async def execute(self, request: InternalTextExecutionRequest) -> InternalTextExecutionResponse:
        decision = self._route(request)
        credential = self._resolve_credential(request, decision)
        context = ExecutionContext(decision, (credential,), job_id=str(request.job_id))
        executor = ProviderExecutor(self._execution_registry)
        try:
            adapter = self._adapters.get(request.provider_id)
            parameters = {
                "prompt": request.input.prompt,
                "temperature": request.input.temperature,
                "max_tokens": request.input.max_output_tokens,
            }
            if request.input.system_prompt is not None:
                parameters["system_prompt"] = request.input.system_prompt
            prepared = executor.prepare(
                adapter=adapter,
                context=context,
                capability="text_generation",
                model_id=request.model_id,
                parameters=parameters,
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
        return InternalTextExecutionResponse(
            request_id=request.request_id,
            job_id=request.job_id,
            provider_id=request.provider_id,
            model_id=request.model_id,
            capability="text_generation",
            status="completed",
            text=result.output.text,
            finish_reason=result.output.finish_reason,
            usage=dict(result.output.usage),
            elapsed_ms=result.output.elapsed_ms,
            routing_version=request.routing_version,
        )

    def _route(self, request: InternalTextExecutionRequest):
        if request.routing_version != PROVIDER_CONFIGURATION_VERSION:
            raise InternalExecutionFailure("AI_MODEL_NOT_ALLOWED", "request is not allowed", 422, False)
        routing_settings = self._settings
        if request.credential_source == "stored" and not self._settings.gemini_api_key and request.provider_id == "gemini":
            routing_settings = replace(self._settings, gemini_api_key="stored-credential-validation")
        router = DryRunProviderRouter(routing_settings)
        configuration = RoutingConfiguration(
            text_provider=request.provider_id,
            text_model=request.model_id,
            visual_source="ai",
            image_provider=DEFAULT_IMAGE_PROVIDER,
            image_model=DEFAULT_IMAGE_MODEL,
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

    def _resolve_credential(self, request: InternalTextExecutionRequest, decision):
        resolver = CredentialResolver(self._settings, self._database, self._encryption)
        try:
            return resolver.resolve(decision, request.credential_source, request.provider_id)
        except CredentialResolutionError as exc:
            raise _credential_failure(exc.code) from None
        except Exception:
            raise _credential_failure("credential_configuration_error") from None


def _routing_failure(code: str) -> InternalExecutionFailure:
    mapping = {
        "unknown_provider": ("AI_PROVIDER_UNKNOWN", 422, False),
        "disabled_provider": ("AI_PROVIDER_DISABLED", 422, False),
        "unavailable_provider": ("AI_PROVIDER_UNAVAILABLE", 503, True),
        "unknown_model": ("AI_MODEL_UNKNOWN", 422, False),
        "provider_model_mismatch": ("AI_MODEL_NOT_ALLOWED", 422, False),
        "model_unimplemented": ("AI_MODEL_NOT_ALLOWED", 422, False),
        "provider_unimplemented": ("AI_PROVIDER_DISABLED", 422, False),
    }
    result = mapping.get(code, ("AI_EXECUTION_FAILED", 422, False))
    return InternalExecutionFailure(result[0], "request is not allowed", result[1], result[2])


def _credential_failure(code: str) -> InternalExecutionFailure:
    if code in {"credential_missing", "provider_metadata_missing"}:
        return InternalExecutionFailure("AI_CREDENTIAL_MISSING", "provider credential is unavailable", 503, False)
    if code in {"credential_decryption_error", "encryption_key_missing", "credential_configuration_error"}:
        return InternalExecutionFailure("AI_CREDENTIAL_INVALID", "provider credential is invalid", 503, False)
    return InternalExecutionFailure("AI_CREDENTIAL_INVALID", "provider credential is invalid", 503, False)


def _execution_failure(code: str) -> InternalExecutionFailure:
    mapping = {
        "invalid_credentials": ("AI_CREDENTIAL_INVALID", 401, False),
        "quota_exceeded": ("AI_QUOTA_EXCEEDED", 402, False),
        "rate_limited": ("AI_RATE_LIMITED", 429, True),
        "timeout": ("AI_TIMEOUT", 504, True),
        "unavailable": ("AI_PROVIDER_UNAVAILABLE", 503, True),
        "blocked_response": ("AI_RESPONSE_BLOCKED", 422, False),
        "empty_response": ("AI_RESPONSE_EMPTY", 502, False),
        "malformed_response": ("AI_RESPONSE_INVALID", 502, False),
        "invalid_request": ("AI_EXECUTION_FAILED", 422, False),
    }
    result = mapping.get(code, ("AI_EXECUTION_FAILED", 502, False))
    return InternalExecutionFailure(result[0], "provider execution failed", result[1], result[2])
