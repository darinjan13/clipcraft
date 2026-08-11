from dataclasses import dataclass
from typing import Literal, Protocol

from ...config import Settings
from .provider_registry import (
    PROVIDER_CONFIGURATION_VERSION,
    RegistryValidationError,
    SUPPORTED_VISUAL_SOURCES,
    get_provider,
    validate_model_selection,
    validate_visual_source,
)


class RoutingValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class RoutingConfiguration:
    text_provider: str | None = None
    text_model: str | None = None
    visual_source: str | None = None
    image_provider: str | None = None
    image_model: str | None = None
    credential_source: str | None = None
    provider_configuration_version: str | None = None


@dataclass(frozen=True)
class RoutingDecision:
    text_provider: str
    text_model: str
    visual_source: str
    image_provider: str | None
    image_model: str | None
    credential_strategy: Literal["environment", "stored"]
    routing_version: int


class ProviderRouter(Protocol):
    def resolve(self, configuration: RoutingConfiguration) -> RoutingDecision:
        """Validate and normalize a provider routing decision without executing it."""


class DryRunProviderRouter:
    """Resolve registry selections for future routing without side effects."""

    def __init__(self, settings: Settings):
        self._settings = settings

    def resolve(self, configuration: RoutingConfiguration) -> RoutingDecision:
        self._validate_pair(configuration.text_provider, configuration.text_model, "text")
        visual_source = configuration.visual_source or "ai"
        if visual_source not in SUPPORTED_VISUAL_SOURCES:
            raise RoutingValidationError("unsupported_visual_source", "unsupported visual source")
        try:
            validate_visual_source(visual_source)
        except RegistryValidationError as exc:
            raise RoutingValidationError(exc.code, exc.message) from exc
        credential_source = configuration.credential_source or "environment"
        if credential_source != "environment":
            raise RoutingValidationError("unsupported_credential_source", "only environment credentials are supported")
        version = configuration.provider_configuration_version or PROVIDER_CONFIGURATION_VERSION
        if version != PROVIDER_CONFIGURATION_VERSION:
            raise RoutingValidationError("unsupported_provider_configuration_version", "unsupported provider configuration version")

        self._validate_available(configuration.text_provider, configuration.text_model, "text")
        if visual_source == "ai":
            self._validate_pair(configuration.image_provider, configuration.image_model, "image")
            self._validate_available(configuration.image_provider, configuration.image_model, "image")
            image_provider = configuration.image_provider
            image_model = configuration.image_model
        else:
            image_provider = None
            image_model = None

        return RoutingDecision(
            text_provider=configuration.text_provider,
            text_model=configuration.text_model,
            visual_source=visual_source,
            image_provider=image_provider,
            image_model=image_model,
            credential_strategy="environment",
            routing_version=int(PROVIDER_CONFIGURATION_VERSION),
        )

    @staticmethod
    def _validate_pair(provider_id: str | None, model_id: str | None, capability: str) -> None:
        if (provider_id is None) != (model_id is None) or provider_id is None or model_id is None:
            raise RoutingValidationError("incomplete_provider_model", f"{capability} provider and model are required together")

    def _validate_available(self, provider_id: str | None, model_id: str | None, capability: str) -> None:
        assert provider_id is not None and model_id is not None
        try:
            validate_model_selection(provider_id, model_id, capability)
            provider = get_provider(provider_id, self._settings)
        except RegistryValidationError as exc:
            raise RoutingValidationError(exc.code, exc.message) from exc
        if not provider["available"]:
            raise RoutingValidationError("unavailable_provider", "provider is unavailable")
        model = next(item for item in provider["models"] if item["model_id"] == model_id)
        if not model["available"]:
            raise RoutingValidationError("unavailable_model", "model is unavailable")
