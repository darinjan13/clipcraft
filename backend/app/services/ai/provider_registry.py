from dataclasses import dataclass
from typing import Any

from ...config import Settings


CAPABILITIES = {"text", "image", "stock_media"}
SUPPORTED_VISUAL_SOURCES = {"ai", "pexels"}
SUPPORTED_PEXELS_MEDIA_TYPES = {"photo", "video"}
SUPPORTED_PEXELS_ORIENTATIONS = {"landscape", "portrait", "square"}


@dataclass(frozen=True)
class ModelDefinition:
    model_id: str
    display_name: str
    capability: str
    implemented: bool
    enabled: bool
    deprecated: bool
    description: str | None = None
    context_limit: int | None = None


@dataclass(frozen=True)
class ProviderDefinition:
    provider_id: str
    display_name: str
    provider_type: str
    capabilities: tuple[str, ...]
    requires_credential: bool
    credential_type: str | None
    enabled: bool
    implemented: bool
    models: tuple[ModelDefinition, ...]
    default_model: str | None
    credential_configuration_supported: bool = False
    connection_test_supported: bool = False


class RegistryValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


NVIDIA_TEXT_MODELS = (
    "nvidia/llama-3.3-nemotron-super-49b-v1",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "nvidia/llama-3.1-nemotron-51b-instruct",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3-super-120b-a12b",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/nemotron-4-340b-instruct",
)

NVIDIA_DEPRECATED_MODELS = {
    "nvidia/llama-3.1-nemotron-ultra-253b-v1",
}

NVIDIA_MODEL_DISPLAY_NAMES = {
    "nvidia/llama-3.3-nemotron-super-49b-v1": "Llama 3.3 Nemotron Super 49B",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": "Llama 3.3 Nemotron Super 49B v1.5",
    "nvidia/llama-3.1-nemotron-70b-instruct": "Llama 3.1 Nemotron 70B Instruct",
    "nvidia/llama-3.1-nemotron-51b-instruct": "Llama 3.1 Nemotron 51B Instruct",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1": "Llama 3.1 Nemotron Ultra 253B",
    "nvidia/nemotron-3-ultra-550b-a55b": "Nemotron 3 Ultra 550B",
    "nvidia/nemotron-3-super-120b-a12b": "Nemotron 3 Super 120B",
    "nvidia/nemotron-3.5-lightning-30b-a3b": "Nemotron 3.5 Lightning 30B",
    "nvidia/nemotron-4-340b-instruct": "Nemotron 4 340B Instruct",
}

NVIDIA_MODEL_DESCRIPTIONS = {
    "nvidia/llama-3.3-nemotron-super-49b-v1": "NVIDIA-hosted text generation, strong at instruction following.",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": "NVIDIA-hosted text generation, improved Nemotron Super 49B.",
    "nvidia/llama-3.1-nemotron-70b-instruct": "NVIDIA-hosted 70B parameter model, optimized for instruction following.",
    "nvidia/llama-3.1-nemotron-51b-instruct": "NVIDIA-hosted 51B parameter model, optimized for instruction following.",
    "nvidia/llama-3.1-nemotron-ultra-253b-v1": "NVIDIA Nemotron Ultra 253B, high-quality text generation.",
    "nvidia/nemotron-3-ultra-550b-a55b": "NVIDIA Nemotron 3 Ultra 550B, high-quality structured text generation.",
    "nvidia/nemotron-3-super-120b-a12b": "Nemotron 3 Super 120B, high-quality text generation.",
    "nvidia/nemotron-3.5-lightning-30b-a3b": "Nemotron 3.5 Lightning 30B, fast text generation.",
    "nvidia/nemotron-4-340b-instruct": "Nemotron 4 340B Instruct, large-scale text generation.",
}


def _nvidia_models():
    return tuple(
        ModelDefinition(
            model_id=model_id,
            display_name=NVIDIA_MODEL_DISPLAY_NAMES.get(model_id, model_id),
            capability="text",
            implemented=True,
            enabled=True,
            deprecated=model_id in NVIDIA_DEPRECATED_MODELS,
            description=NVIDIA_MODEL_DESCRIPTIONS.get(model_id),
        )
        for model_id in NVIDIA_TEXT_MODELS
    )


NVIDIA_TEXT_MODEL = "nvidia/llama-3.3-nemotron-super-49b-v1"
NVIDIA_DEFAULT_MODEL = NVIDIA_TEXT_MODEL


@dataclass(frozen=True)
class ProviderDefinition:
    provider_id: str
    display_name: str
    provider_type: str
    capabilities: tuple[str, ...]
    requires_credential: bool
    credential_type: str | None
    enabled: bool
    implemented: bool
    models: tuple[ModelDefinition, ...]
    default_model: str | None
    credential_configuration_supported: bool = False
    connection_test_supported: bool = False


class RegistryValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


PROVIDER_REGISTRY: tuple[ProviderDefinition, ...] = (
    ProviderDefinition(
        provider_id="gemini",
        display_name="Google Gemini",
        provider_type="text",
        capabilities=("text", "image"),
        requires_credential=True,
        credential_type="api_key",
        enabled=True,
        implemented=True,
        credential_configuration_supported=True,
        connection_test_supported=True,
        default_model="gemini-2.5-flash",
        models=(
            ModelDefinition(
                model_id="gemini-2.5-flash",
                display_name="Gemini 2.5 Flash",
                capability="text",
                implemented=True,
                enabled=True,
                deprecated=False,
                description="Fast, structured script and scene generation.",
            ),
            ModelDefinition(
                model_id="gemini-2.5-flash:image-preview",
                display_name="Gemini Image Preview",
                capability="image",
                implemented=False,
                enabled=True,
                deprecated=False,
                description="Reserved for future Gemini image generation support.",
            ),
        ),
    ),
    ProviderDefinition(
        provider_id="cloudflare",
        display_name="Cloudflare Workers AI",
        provider_type="text",
        capabilities=("text", "image"),
        requires_credential=True,
        credential_type="api_token",
        enabled=True,
        implemented=True,
        credential_configuration_supported=True,
        connection_test_supported=True,
        default_model="@cf/black-forest-labs/flux-1-schnell",
        models=(
            ModelDefinition(
                model_id="@cf/meta/llama-3.1-8b-instruct",
                display_name="Llama 3.1 8B Instruct",
                capability="text",
                implemented=True,
                enabled=True,
                deprecated=False,
                description="Cloudflare-hosted text generation.",
            ),
            ModelDefinition(
                model_id="@cf/black-forest-labs/flux-1-schnell",
                display_name="FLUX.1 Schnell",
                capability="image",
                implemented=True,
                enabled=True,
                deprecated=False,
                description="Fast Cloudflare-hosted scene image generation.",
            ),
        ),
    ),
    ProviderDefinition(
        provider_id="nvidia",
        display_name="NVIDIA",
        provider_type="text",
        capabilities=("text",),
        requires_credential=True,
        credential_type="api_key",
        enabled=True,
        implemented=True,
        credential_configuration_supported=True,
        connection_test_supported=True,
        default_model="nvidia/llama-3.3-nemotron-super-49b-v1",
        models=_nvidia_models(),
    ),
    ProviderDefinition(
        provider_id="pexels",
        display_name="Pexels",
        provider_type="stock_media",
        capabilities=("stock_media",),
        requires_credential=True,
        credential_type="api_key",
        enabled=True,
        implemented=False,
        credential_configuration_supported=True,
        connection_test_supported=True,
        default_model=None,
        models=(),
    ),
)


DEFAULT_TEXT_PROVIDER = "gemini"
DEFAULT_TEXT_MODEL = "gemini-2.5-flash"
DEFAULT_IMAGE_PROVIDER = "cloudflare"
DEFAULT_IMAGE_MODEL = "@cf/black-forest-labs/flux-1-schnell"
DEFAULT_VISUAL_SOURCE = "ai"
DEFAULT_CREDENTIAL_SOURCE = "environment"
PROVIDER_CONFIGURATION_VERSION = "1"


def _provider(provider_id: str) -> ProviderDefinition:
    for provider in PROVIDER_REGISTRY:
        if provider.provider_id == provider_id:
            return provider
    raise RegistryValidationError("unknown_provider", f"unknown provider: {provider_id}")


def _provider_available(provider: ProviderDefinition, settings: Settings) -> bool:
    if not provider.enabled or not provider.implemented:
        return False
    if provider.provider_id == "gemini":
        return bool(settings.gemini_api_key)
    return True


def _model_available(provider: ProviderDefinition, model: ModelDefinition, settings: Settings) -> bool:
    return _provider_available(provider, settings) and model.enabled and model.implemented and not model.deprecated


def _model_payload(provider: ProviderDefinition, model: ModelDefinition, settings: Settings) -> dict[str, Any]:
    return {
        "provider_id": provider.provider_id,
        "model_id": model.model_id,
        "display_name": model.display_name,
        "capability": model.capability,
        "implemented": model.implemented,
        "enabled": model.enabled,
        "deprecated": model.deprecated,
        "available": _model_available(provider, model, settings),
        "description": model.description,
        "context_limit": model.context_limit,
    }


def _provider_payload(provider: ProviderDefinition, settings: Settings) -> dict[str, Any]:
    return {
        "provider_id": provider.provider_id,
        "display_name": provider.display_name,
        "provider_type": provider.provider_type,
        "capabilities": list(provider.capabilities),
        "requires_credential": provider.requires_credential,
        "credential_type": provider.credential_type,
        "enabled": provider.enabled,
        "implemented": provider.implemented,
        "credential_configuration_supported": provider.credential_configuration_supported,
        "connection_test_supported": provider.connection_test_supported,
        "available": _provider_available(provider, settings),
        "models": [_model_payload(provider, model, settings) for model in provider.models],
        "default_model": provider.default_model,
    }


def list_providers(settings: Settings) -> list[dict[str, Any]]:
    return [_provider_payload(provider, settings) for provider in PROVIDER_REGISTRY]


def get_provider(provider_id: str, settings: Settings) -> dict[str, Any]:
    return _provider_payload(_provider(provider_id), settings)


def list_models(
    settings: Settings,
    *,
    capability: str | None = None,
    provider_id: str | None = None,
) -> list[dict[str, Any]]:
    if capability is not None and capability not in CAPABILITIES:
        raise RegistryValidationError("unsupported_capability", f"unsupported capability: {capability}")
    providers = [_provider(provider_id)] if provider_id is not None else PROVIDER_REGISTRY
    return [
        _model_payload(provider, model, settings)
        for provider in providers
        for model in provider.models
        if capability is None or model.capability == capability
    ]


def validate_model_selection(provider_id: str, model_id: str, capability: str) -> None:
    if capability not in CAPABILITIES:
        raise RegistryValidationError("unsupported_capability", f"unsupported capability: {capability}")
    provider = _provider(provider_id)
    if capability not in provider.capabilities:
        raise RegistryValidationError(
            "provider_capability_mismatch",
            f"provider {provider_id} does not support capability {capability}",
        )
    if not provider.enabled:
        raise RegistryValidationError("disabled_provider", f"provider is disabled: {provider_id}")
    if not provider.implemented:
        raise RegistryValidationError("provider_unimplemented", f"provider is not implemented: {provider_id}")
    model = next((item for item in provider.models if item.model_id == model_id), None)
    if model is None:
        if any(item.model_id == model_id for other in PROVIDER_REGISTRY for item in other.models):
            raise RegistryValidationError(
                "provider_model_mismatch",
                f"model {model_id} does not belong to provider {provider_id}",
            )
        raise RegistryValidationError("unknown_model", f"unknown model {model_id} for provider {provider_id}")
    if model.capability != capability:
        raise RegistryValidationError(
            "provider_model_mismatch",
            f"model {model_id} does not support capability {capability}",
        )
    if not model.enabled or model.deprecated:
        raise RegistryValidationError("disabled_model", f"model is disabled: {model_id}")
    if not model.implemented:
        raise RegistryValidationError("model_unimplemented", f"model is not implemented: {model_id}")


def default_model_for_provider(provider_id: str, capability: str) -> str:
    provider = _provider(provider_id)
    if capability not in provider.capabilities:
        raise RegistryValidationError(
            "provider_capability_mismatch",
            f"provider {provider_id} does not support capability {capability}",
        )
    for model in provider.models:
        if model.capability == capability and model.enabled and model.implemented and not model.deprecated:
            return model.model_id
    raise RegistryValidationError("provider_unimplemented", f"provider has no implemented {capability} model: {provider_id}")


def validate_visual_source(value: str) -> None:
    if value not in SUPPORTED_VISUAL_SOURCES:
        raise RegistryValidationError("unsupported_visual_source", f"unsupported visual source: {value}")
    if value == "pexels":
        provider = _provider("pexels")
        if not provider.enabled:
            raise RegistryValidationError("disabled_provider", "provider is disabled: pexels")
        if not provider.implemented:
            raise RegistryValidationError("provider_unimplemented", "provider is not implemented: pexels")


def validate_pexels_media_type(value: str) -> None:
    if value not in SUPPORTED_PEXELS_MEDIA_TYPES:
        raise RegistryValidationError("unsupported_pexels_media_type", f"unsupported Pexels media type: {value}")


def validate_pexels_orientation(value: str) -> None:
    if value not in SUPPORTED_PEXELS_ORIENTATIONS:
        raise RegistryValidationError("unsupported_pexels_orientation", f"unsupported Pexels orientation: {value}")


def validate_provider_selection(
    *,
    text_provider: str = "",
    text_model: str = "",
    image_provider: str = "",
    image_model: str = "",
) -> None:
    selections = (
        (text_provider or DEFAULT_TEXT_PROVIDER, text_model or DEFAULT_TEXT_MODEL, "text"),
        (image_provider or DEFAULT_IMAGE_PROVIDER, image_model or DEFAULT_IMAGE_MODEL, "image"),
    )
    for provider_id, model_id, capability in selections:
        validate_model_selection(provider_id, model_id, capability)


def resolve_provider_selection(
    *,
    text_provider: str | None = None,
    text_model: str | None = None,
    image_provider: str | None = None,
    image_model: str | None = None,
) -> dict[str, str]:
    validate_provider_selection(
        text_provider=text_provider or "",
        text_model=text_model or "",
        image_provider=image_provider or "",
        image_model=image_model or "",
    )
    return {
        "text_provider": text_provider or DEFAULT_TEXT_PROVIDER,
        "text_model": text_model or DEFAULT_TEXT_MODEL,
        "image_provider": image_provider or DEFAULT_IMAGE_PROVIDER,
        "image_model": image_model or DEFAULT_IMAGE_MODEL,
    }


def _legacy_model_payload(model: dict[str, Any], defaults: dict[str, str]) -> dict[str, Any]:
    capability = model["capability"]
    is_default = (
        model["provider_id"] == defaults[f"{capability}_provider"]
        and model["model_id"] == defaults[f"{capability}_model"]
    )
    return {
        "provider": model["provider_id"],
        "model": model["model_id"],
        "display_name": model["display_name"],
        "description": model["description"] or "",
        "available": model["available"],
        "is_default": is_default,
    }


def get_model_capabilities(
    settings: Settings,
    *,
    capability: str | None = None,
    provider_id: str | None = None,
) -> dict[str, Any]:
    defaults = {
        "text_provider": DEFAULT_TEXT_PROVIDER,
        "text_model": DEFAULT_TEXT_MODEL,
        "image_provider": DEFAULT_IMAGE_PROVIDER,
        "image_model": DEFAULT_IMAGE_MODEL,
    }
    models = list_models(settings, capability=capability, provider_id=provider_id)
    return {
        "defaults": defaults,
        "providers": list_providers(settings),
        "models": models,
        "text_models": [_legacy_model_payload(model, defaults) for model in models if model["capability"] == "text"],
        "image_models": [_legacy_model_payload(model, defaults) for model in models if model["capability"] == "image"],
    }