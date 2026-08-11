import json
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import SecretStr

from ...clients import BackendDependencyError
from ...config import Settings
from ..credential_crypto import CredentialCryptoError, CredentialEncryption
from .provider_registry import RegistryValidationError, get_provider
from .provider_registry import SUPPORTED_VISUAL_SOURCES, validate_model_selection
from .routing import RoutingDecision


class CredentialResolutionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class CredentialDatabase(Protocol):
    def get_credential_for_test(self, provider_id: str) -> dict[str, object] | None:
        """Load only the encrypted credential row needed for resolution."""


@dataclass(frozen=True)
class ResolvedProviderCredential:
    provider_id: str
    credential_strategy: str
    secret: SecretStr = field(repr=False)
    account_id: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True)
class ExecutionContext:
    routing_decision: RoutingDecision
    credentials: tuple[ResolvedProviderCredential, ...]
    job_id: str | None = None
    timeout_seconds: float = 30.0


class CredentialResolver:
    """Resolve one validated provider credential without caching or side effects."""

    def __init__(self, settings: Settings, database: CredentialDatabase, encryption: CredentialEncryption | None = None):
        self._settings = settings
        self._database = database
        self._encryption = encryption

    def resolve(
        self,
        routing_decision: RoutingDecision,
        credential_strategy: str | None = None,
        provider_id: str | None = None,
    ) -> ResolvedProviderCredential:
        provider_id = provider_id or routing_decision.text_provider
        strategy = routing_decision.credential_strategy if credential_strategy is None else credential_strategy
        if strategy not in {"environment", "stored"}:
            raise CredentialResolutionError("credential_source_invalid", "unsupported credential source")
        allowed_providers = {routing_decision.text_provider}
        if routing_decision.visual_source == "ai" and routing_decision.image_provider:
            allowed_providers.add(routing_decision.image_provider)
        if routing_decision.visual_source == "pexels":
            allowed_providers.add("pexels")
        if provider_id not in allowed_providers:
            raise CredentialResolutionError("provider_mismatch", "provider is not part of the routing decision")
        if provider_id == "nvidia":
            raise CredentialResolutionError("not_implemented", "credential resolution is not implemented for this provider")
        self._validate_routing_decision(routing_decision)
        try:
            provider = get_provider(provider_id, self._settings)
        except RegistryValidationError as exc:
            raise CredentialResolutionError("unknown_provider", "unknown provider") from None
        if not provider["enabled"]:
            raise CredentialResolutionError("unsupported_provider", "provider is disabled")
        if strategy == "environment":
            return self._resolve_environment(provider_id)
        return self._resolve_stored(provider_id)

    def _validate_routing_decision(self, decision: RoutingDecision) -> None:
        if decision.visual_source not in SUPPORTED_VISUAL_SOURCES:
            raise CredentialResolutionError("unsupported_visual_source", "unsupported visual source")
        self._validate_decision_provider(decision.text_provider, decision.text_model, "text")
        if decision.visual_source == "ai":
            if decision.image_provider is None or decision.image_model is None:
                raise CredentialResolutionError("incomplete_provider_model", "image provider and model are required")
            self._validate_decision_provider(decision.image_provider, decision.image_model, "image")

    def _validate_decision_provider(self, provider_id: str, model_id: str, capability: str) -> None:
        try:
            validate_model_selection(provider_id, model_id, capability)
            get_provider(provider_id, self._settings)
        except RegistryValidationError as exc:
            raise CredentialResolutionError(exc.code, exc.message) from None

    def _resolve_environment(self, provider_id: str) -> ResolvedProviderCredential:
        if provider_id == "gemini":
            if not self._settings.gemini_api_key or not self._settings.gemini_api_key.strip():
                raise CredentialResolutionError("credential_missing", "provider credential is not configured")
            return ResolvedProviderCredential(provider_id, "environment", SecretStr(self._settings.gemini_api_key))
        if provider_id == "cloudflare":
            if not self._settings.cloudflare_ai_token or not self._settings.cloudflare_ai_token.strip():
                raise CredentialResolutionError("credential_missing", "provider credential is not configured")
            if not self._settings.cloudflare_account_id or not self._settings.cloudflare_account_id.strip():
                raise CredentialResolutionError("credential_configuration_error", "provider credential metadata is incomplete")
            return ResolvedProviderCredential(
                provider_id,
                "environment",
                SecretStr(self._settings.cloudflare_ai_token),
                account_id=self._settings.cloudflare_account_id,
            )
        if provider_id == "pexels":
            raise CredentialResolutionError("credential_configuration_error", "environment credential configuration is unavailable")
        raise CredentialResolutionError("not_implemented", "credential resolution is not implemented for this provider")

    def _resolve_stored(self, provider_id: str) -> ResolvedProviderCredential:
        if self._encryption is None:
            raise CredentialResolutionError("encryption_key_missing", "credential encryption is not configured")
        try:
            row = self._database.get_credential_for_test(provider_id)
        except BackendDependencyError as exc:
            raise CredentialResolutionError("credential_configuration_error", "credential store is unavailable") from None
        except Exception as exc:
            raise CredentialResolutionError("credential_configuration_error", "credential store could not be read") from None
        if not row or not row.get("encrypted_secret") or not row.get("enabled") or row.get("status") != "configured":
            raise CredentialResolutionError("credential_missing", "provider credential is not configured")
        try:
            secret = self._encryption.decrypt(str(row["encrypted_secret"]), provider_id)
            metadata = self._decrypt_metadata(row.get("encrypted_metadata"), provider_id)
        except (CredentialCryptoError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CredentialResolutionError("credential_decryption_error", "stored provider credential could not be decrypted") from None
        if not secret.strip():
            raise CredentialResolutionError("credential_configuration_error", "stored provider credential is empty")
        account_id = None
        if provider_id == "cloudflare":
            account_id = metadata.get("account_id") if metadata else None
            if not isinstance(account_id, str) or not account_id.strip():
                raise CredentialResolutionError("provider_metadata_missing", "provider credential metadata is incomplete")
        return ResolvedProviderCredential(
            provider_id,
            "stored",
            SecretStr(secret),
            account_id=account_id,
            updated_at=str(row.get("updated_at")) if row.get("updated_at") is not None else None,
        )

    def _decrypt_metadata(self, ciphertext: object, provider_id: str) -> dict[str, object] | None:
        if ciphertext is None:
            return None
        metadata = json.loads(self._encryption.decrypt(str(ciphertext), provider_id))
        if not isinstance(metadata, dict):
            raise CredentialResolutionError("provider_metadata_missing", "provider credential metadata is invalid")
        return metadata


def build_execution_context(
    routing_decision: RoutingDecision,
    resolver: CredentialResolver,
    credential_strategy: str | None = None,
    job_id: str | None = None,
) -> ExecutionContext:
    strategy = credential_strategy or routing_decision.credential_strategy
    provider_ids = [routing_decision.text_provider]
    if routing_decision.visual_source == "ai" and routing_decision.image_provider:
        provider_ids.append(routing_decision.image_provider)
    if routing_decision.visual_source == "pexels":
        provider_ids.append("pexels")
    credentials: list[ResolvedProviderCredential] = []
    for provider_id in provider_ids:
        if any(item.provider_id == provider_id for item in credentials):
            continue
        credentials.append(resolver.resolve(routing_decision, strategy, provider_id))
    return ExecutionContext(routing_decision, tuple(credentials), job_id=job_id)
