from dataclasses import dataclass
from collections.abc import Mapping as MappingABC
from types import MappingProxyType
from typing import Any, Literal, Mapping

from .credential_resolution import ExecutionContext

Capability = Literal["text_generation", "image_generation", "stock_media", "connection_test"]


class AdapterValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PreparedProviderRequest:
    provider_id: str
    capability: str
    payload: Mapping[str, object]


@dataclass(frozen=True)
class PreparedExecutionContext:
    provider_id: str
    credential_strategy: str
    routing_version: int
    job_id: str | None


@dataclass(frozen=True)
class AdapterHealth:
    provider_id: str
    status: str
    checked_remotely: bool


class ProviderAdapter:
    """Pure provider-specific request preparation; never executes a provider."""

    _sensitive_keys = {
        "secret", "token", "apikey", "authorization", "credential", "encryptedsecret",
        "accesstoken", "refreshtoken", "password", "privatekey", "headers",
    }

    def __init__(self, provider_id: str, capabilities: set[str] | frozenset[str]):
        if not provider_id:
            raise AdapterValidationError("invalid_provider_id", "provider ID is required")
        self.provider_id = provider_id
        self._capabilities = frozenset(capabilities)

    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    def supports(self, capability: str) -> bool:
        return capability in self._capabilities

    def validate_request(self, capability: str, request: Mapping[str, object]) -> None:
        if not isinstance(request, MappingABC) or any(not isinstance(key, str) for key in request):
            raise AdapterValidationError("invalid_request", "request must use string field names")
        if not self.supports(capability):
            raise AdapterValidationError("unsupported_capability", "adapter does not support this capability")
        if self._contains_sensitive_field(request):
            raise AdapterValidationError("sensitive_field_forbidden", "credential fields are not accepted")
        if capability in {"text_generation", "image_generation"}:
            self._require_text(request, "prompt")
        if capability == "stock_media":
            self._require_text(request, "query")

    def prepare_request(self, capability: str, request: Mapping[str, object]) -> PreparedProviderRequest:
        self.validate_request(capability, request)
        return PreparedProviderRequest(self.provider_id, capability, self._freeze(request))

    def prepare_execution_context(self, context: ExecutionContext) -> PreparedExecutionContext:
        allowed = {context.routing_decision.text_provider}
        if context.routing_decision.visual_source == "ai" and context.routing_decision.image_provider:
            allowed.add(context.routing_decision.image_provider)
        if context.routing_decision.visual_source == "pexels":
            allowed.add("pexels")
        if self.provider_id not in allowed:
            raise AdapterValidationError("provider_mismatch", "provider is not part of the execution context")
        if not any(credential.provider_id == self.provider_id for credential in context.credentials):
            raise AdapterValidationError("credential_missing", "provider credential is not in the execution context")
        return PreparedExecutionContext(
            provider_id=self.provider_id,
            credential_strategy=next(credential.credential_strategy for credential in context.credentials if credential.provider_id == self.provider_id),
            routing_version=context.routing_decision.routing_version,
            job_id=context.job_id,
        )

    def health(self) -> AdapterHealth:
        return AdapterHealth(self.provider_id, "registered", False)

    @staticmethod
    def _require_text(request: Mapping[str, object], field: str) -> None:
        value = request.get(field)
        if not isinstance(value, str) or not value.strip():
            raise AdapterValidationError(f"{field}_required", f"{field} is required")

    @classmethod
    def _contains_sensitive_field(cls, value: Any) -> bool:
        if isinstance(value, MappingABC):
            for key, nested in value.items():
                if not isinstance(key, str):
                    return True
                normalized = "".join(character for character in key.lower() if character.isalnum())
                if normalized in cls._sensitive_keys or cls._contains_sensitive_field(nested):
                    return True
        elif isinstance(value, (list, tuple, set, frozenset)):
            return any(cls._contains_sensitive_field(item) for item in value)
        return False

    @staticmethod
    def _freeze(value: Any) -> Any:
        if isinstance(value, MappingABC):
            return MappingProxyType({key: ProviderAdapter._freeze(nested) for key, nested in value.items()})
        if isinstance(value, (list, tuple)):
            return tuple(ProviderAdapter._freeze(item) for item in value)
        if isinstance(value, (set, frozenset)):
            return frozenset(ProviderAdapter._freeze(item) for item in value)
        return value


class GeminiAdapter(ProviderAdapter):
    def __init__(self):
        super().__init__("gemini", {"text_generation", "connection_test"})

    def validate_request(self, capability: str, request: Mapping[str, object]) -> None:
        super().validate_request(capability, request)
        unknown = set(request) - {"prompt", "system_prompt", "temperature", "max_tokens"}
        if unknown:
            raise AdapterValidationError("unsupported_parameter", "unsupported Gemini request parameter")
        if "system_prompt" in request and not isinstance(request["system_prompt"], str):
            raise AdapterValidationError("invalid_system_prompt", "system_prompt must be text")
        if "temperature" in request and (not isinstance(request["temperature"], (int, float)) or not 0 <= request["temperature"] <= 2):
            raise AdapterValidationError("invalid_temperature", "temperature is invalid")
        if "max_tokens" in request and (not isinstance(request["max_tokens"], int) or request["max_tokens"] <= 0):
            raise AdapterValidationError("invalid_max_tokens", "max_tokens is invalid")


class CloudflareAdapter(ProviderAdapter):
    def __init__(self):
        super().__init__("cloudflare", {"text_generation", "image_generation", "connection_test"})

    def validate_request(self, capability: str, request: Mapping[str, object]) -> None:
        super().validate_request(capability, request)
        if capability == "text_generation":
            unknown = set(request) - {"prompt", "system_prompt", "temperature", "max_tokens"}
            if unknown:
                raise AdapterValidationError("unsupported_parameter", "unsupported Cloudflare text request parameter")
            if "system_prompt" in request and not isinstance(request["system_prompt"], str):
                raise AdapterValidationError("invalid_system_prompt", "system_prompt must be text")
            if "temperature" in request and (not isinstance(request["temperature"], (int, float)) or not 0 <= request["temperature"] <= 2):
                raise AdapterValidationError("invalid_temperature", "temperature is invalid")
            if "max_tokens" in request and (not isinstance(request["max_tokens"], int) or request["max_tokens"] <= 0):
                raise AdapterValidationError("invalid_max_tokens", "max_tokens is invalid")
        elif capability == "image_generation":
            unknown = set(request) - {"prompt"}
            if unknown:
                raise AdapterValidationError("unsupported_parameter", "unsupported Cloudflare image request parameter")


class PexelsAdapter(ProviderAdapter):
    def __init__(self):
        super().__init__("pexels", {"stock_media", "connection_test"})

    def validate_request(self, capability: str, request: Mapping[str, object]) -> None:
        super().validate_request(capability, request)
        if capability != "stock_media":
            return
        if request.get("media_type") not in {None, "photo", "video"}:
            raise AdapterValidationError("unsupported_media_type", "unsupported media type")
        if request.get("orientation") not in {None, "landscape", "portrait", "square"}:
            raise AdapterValidationError("unsupported_orientation", "unsupported orientation")


class NVIDIAAdapter(ProviderAdapter):
    def __init__(self):
        super().__init__("nvidia", {"text_generation", "connection_test"})

    def validate_request(self, capability: str, request: Mapping[str, object]) -> None:
        super().validate_request(capability, request)
        unknown = set(request) - {"prompt", "system_prompt", "temperature", "max_tokens"}
        if unknown:
            raise AdapterValidationError("unsupported_parameter", "unsupported NVIDIA request parameter")
        if "system_prompt" in request and not isinstance(request["system_prompt"], str):
            raise AdapterValidationError("invalid_system_prompt", "system_prompt must be text")
        if "temperature" in request and (not isinstance(request["temperature"], (int, float)) or not 0 <= request["temperature"] <= 2):
            raise AdapterValidationError("invalid_temperature", "temperature is invalid")
        if "max_tokens" in request and (not isinstance(request["max_tokens"], int) or request["max_tokens"] <= 0):
            raise AdapterValidationError("invalid_max_tokens", "max_tokens is invalid")


class AdapterRegistry:
    def __init__(self):
        self._adapters: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> None:
        if adapter.provider_id in self._adapters:
            raise AdapterValidationError("adapter_already_registered", "provider adapter is already registered")
        self._adapters[adapter.provider_id] = adapter

    def get(self, provider_id: str) -> ProviderAdapter:
        try:
            return self._adapters[provider_id]
        except KeyError as exc:
            raise AdapterValidationError("adapter_not_found", "provider adapter is not registered") from None

    def provider_ids(self) -> set[str]:
        return set(self._adapters)


def default_adapter_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    for adapter in (GeminiAdapter(), CloudflareAdapter(), PexelsAdapter(), NVIDIAAdapter()):
        registry.register(adapter)
    return registry
