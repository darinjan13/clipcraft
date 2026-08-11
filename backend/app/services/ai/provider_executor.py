import inspect
from dataclasses import dataclass, field
from collections.abc import Mapping as MappingABC
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Mapping

from .adapters import AdapterValidationError, PreparedExecutionContext, PreparedProviderRequest, ProviderAdapter
from .credential_resolution import ExecutionContext

ExecutionLifecycle = ("prepared", "validated", "ready", "executing", "completed", "failed")
SUPPORTED_CAPABILITIES = frozenset({"text_generation", "image_generation", "stock_media", "connection_test"})


@dataclass(frozen=True)
class ExecutionError:
    code: str
    message: str


class ProviderExecutionError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.error = ExecutionError(code, message)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.error.code

    @property
    def message(self) -> str:
        return self.error.message


@dataclass(frozen=True)
class ExecutionRequest:
    request_id: str
    provider_id: str
    model_id: str | None
    capability: str
    payload: Mapping[str, object]
    context: PreparedExecutionContext
    runtime_context: ExecutionContext = field(repr=False, compare=False)


@dataclass(frozen=True)
class ExecutionMetadata:
    request_id: str
    provider_id: str
    capability: str
    state: str
    credential_strategy: str
    routing_version: int
    job_id: str | None


@dataclass(frozen=True)
class ExecutionResult:
    state: str
    lifecycle: tuple[str, ...]
    request: ExecutionRequest
    metadata: ExecutionMetadata
    output: "ExecutionOutput | None" = None
    error: ExecutionError | None = None


@dataclass(frozen=True)
class ExecutionOutput:
    provider_id: str
    model_id: str | None
    capability: str
    text: str | None = None
    finish_reason: str | None = None
    usage: Mapping[str, int] = field(default_factory=dict)
    provider_request_id: str | None = None
    elapsed_ms: float | None = None


ExecutionHandler = Callable[[ExecutionRequest], Awaitable[ExecutionOutput] | ExecutionOutput]


class ProviderExecutionRegistry:
    def __init__(self):
        self._handlers: dict[tuple[str, str], ExecutionHandler] = {}

    def register(self, provider_id: str, capability: str, handler: ExecutionHandler) -> None:
        key = (provider_id, capability)
        if key in self._handlers:
            raise ProviderExecutionError("configuration_error", "provider execution is already registered")
        self._handlers[key] = handler

    def get(self, provider_id: str, capability: str) -> ExecutionHandler:
        try:
            return self._handlers[(provider_id, capability)]
        except KeyError:
            raise ProviderExecutionError("execution_not_implemented", "provider execution is not implemented") from None


class ProviderExecutor:
    """Prepare provider execution without invoking a provider or transport."""

    def __init__(self, execution_registry: ProviderExecutionRegistry | None = None):
        self._execution_registry = execution_registry or ProviderExecutionRegistry()

    def prepare(
        self,
        *,
        adapter: ProviderAdapter | None,
        context: ExecutionContext,
        capability: str,
        model_id: str | None,
        parameters: Mapping[str, object],
        request_id: str,
    ) -> ExecutionResult:
        if adapter is None:
            raise ProviderExecutionError("adapter_missing", "provider adapter is required")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ProviderExecutionError("configuration_error", "request ID is required")
        if not isinstance(parameters, Mapping):
            raise ProviderExecutionError("configuration_error", "execution parameters must be a mapping")
        if capability not in SUPPORTED_CAPABILITIES:
            raise ProviderExecutionError("missing_capability", "provider capability is not supported")
        supports = getattr(adapter, "supports", None)
        if callable(supports) and not supports(capability):
            raise ProviderExecutionError("missing_capability", "provider capability is not supported")
        if not self._matches_context(adapter.provider_id, context, capability, model_id):
            raise ProviderExecutionError("invalid_execution_context", "provider, model, or capability does not match context")

        try:
            prepared_context = adapter.prepare_execution_context(context)
            prepared_request = adapter.prepare_request(capability, parameters)
        except AdapterValidationError as exc:
            raise ProviderExecutionError(self._error_code(exc.code), self._safe_message(exc.code)) from None
        except Exception:
            raise ProviderExecutionError("configuration_error", "provider request preparation failed") from None

        if (
            prepared_request.provider_id != adapter.provider_id
            or prepared_request.capability != capability
            or prepared_context.provider_id != adapter.provider_id
            or prepared_context.provider_id != prepared_request.provider_id
        ):
            raise ProviderExecutionError("configuration_error", "adapter returned an invalid prepared request")
        request = ExecutionRequest(
            request_id=request_id,
            provider_id=adapter.provider_id,
            model_id=model_id,
            capability=capability,
            payload=self._freeze(prepared_request.payload),
            context=prepared_context,
            runtime_context=context,
        )
        metadata = ExecutionMetadata(
            request_id=request_id,
            provider_id=adapter.provider_id,
            capability=capability,
            state="ready",
            credential_strategy=prepared_context.credential_strategy,
            routing_version=prepared_context.routing_version,
            job_id=prepared_context.job_id,
        )
        return ExecutionResult("ready", ("prepared", "validated", "ready"), request, metadata)

    async def execute(self, prepared: ExecutionResult) -> ExecutionResult:
        handler = self._execution_registry.get(prepared.request.provider_id, prepared.request.capability)
        executing_metadata = ExecutionMetadata(
            prepared.metadata.request_id,
            prepared.metadata.provider_id,
            prepared.metadata.capability,
            "executing",
            prepared.metadata.credential_strategy,
            prepared.metadata.routing_version,
            prepared.metadata.job_id,
        )
        try:
            output = handler(prepared.request)
            if inspect.isawaitable(output):
                output = await output
            if output.provider_id != prepared.request.provider_id or output.capability != prepared.request.capability:
                raise ProviderExecutionError("execution_error", "provider returned invalid execution metadata")
            completed_metadata = ExecutionMetadata(
                executing_metadata.request_id,
                executing_metadata.provider_id,
                executing_metadata.capability,
                "completed",
                executing_metadata.credential_strategy,
                executing_metadata.routing_version,
                executing_metadata.job_id,
            )
            return ExecutionResult("completed", ("prepared", "validated", "ready", "executing", "completed"), prepared.request, completed_metadata, output=output)
        except ProviderExecutionError as exc:
            failed_error = exc.error
        except Exception:
            failed_error = ExecutionError("execution_error", "provider execution failed")
        failed_metadata = ExecutionMetadata(
            executing_metadata.request_id,
            executing_metadata.provider_id,
            executing_metadata.capability,
            "failed",
            executing_metadata.credential_strategy,
            executing_metadata.routing_version,
            executing_metadata.job_id,
        )
        return ExecutionResult("failed", ("prepared", "validated", "ready", "executing", "failed"), prepared.request, failed_metadata, error=failed_error)

    @staticmethod
    def _matches_context(provider_id: str, context: ExecutionContext, capability: str, model_id: str | None) -> bool:
        decision = context.routing_decision
        if capability == "text_generation":
            return provider_id == decision.text_provider and model_id == decision.text_model
        if capability == "image_generation":
            return provider_id == decision.image_provider and model_id == decision.image_model and decision.visual_source == "ai"
        if capability == "stock_media":
            return provider_id == "pexels" and decision.visual_source == "pexels" and model_id is None
        return provider_id in {decision.text_provider, decision.image_provider}

    @staticmethod
    def _error_code(adapter_code: str) -> str:
        if adapter_code in {"unsupported_capability", "capability_not_supported"}:
            return "missing_capability"
        if adapter_code in {"provider_mismatch", "invalid_request"}:
            return "invalid_execution_context"
        if adapter_code in {"credential_missing", "credential_source_invalid", "credential_resolution_error"}:
            return "credential_resolution_error"
        return "configuration_error"

    @staticmethod
    def _safe_message(adapter_code: str) -> str:
        messages = {
            "unsupported_capability": "provider capability is not supported",
            "provider_mismatch": "provider is not part of the execution context",
            "credential_missing": "provider credential is unavailable",
            "credential_source_invalid": "credential source is invalid",
            "invalid_request": "provider request is invalid",
        }
        return messages.get(adapter_code, "provider request preparation failed")

    @staticmethod
    def _freeze(value: Any) -> Any:
        if isinstance(value, MappingABC):
            return MappingProxyType({key: ProviderExecutor._freeze(nested) for key, nested in value.items()})
        if isinstance(value, (list, tuple)):
            return tuple(ProviderExecutor._freeze(item) for item in value)
        if isinstance(value, (set, frozenset)):
            return frozenset(ProviderExecutor._freeze(item) for item in value)
        return value
