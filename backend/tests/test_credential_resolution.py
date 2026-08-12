import base64
import json
import os

import pytest

from app.config import Settings
from app.services.ai.credential_resolution import (
    CredentialResolutionError,
    CredentialResolver,
    ExecutionContext,
    build_execution_context,
)
from app.services.credential_crypto import CredentialEncryption
from app.services.ai.routing import RoutingDecision


class CredentialDatabase:
    def __init__(self, row=None):
        self.rows = row if isinstance(row, list) else [row] if row else []
        self.calls = 0

    def get_credential_for_test(self, provider_id):
        self.calls += 1
        return next((row for row in self.rows if row.get("provider_id") == provider_id), None)


def make_settings(monkeypatch, **values):
    for name in ("GEMINI_API_KEY", "CLOUDFLARE_AI_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    return Settings.from_env()


def make_decision(provider="gemini", strategy="environment", visual_source="ai", image_provider=None, image_model=None):
    image_provider = image_provider or ("cloudflare" if visual_source == "ai" else None)
    image_model = image_model or ("@cf/black-forest-labs/flux-1-schnell" if visual_source == "ai" else None)
    return RoutingDecision(
        text_provider=provider,
        text_model=(
            "gemini-2.5-flash" if provider == "gemini"
            else "nvidia/llama-3.3-nemotron-super-49b-v1" if provider == "nvidia"
            else "@cf/meta/llama-3.1-8b-instruct"
        ),
        visual_source=visual_source,
        image_provider=image_provider,
        image_model=image_model,
        credential_strategy=strategy,
        routing_version=1,
    )


def encryption():
    return CredentialEncryption(os.urandom(32))


def stored_row(crypto, provider, secret, metadata=None, **overrides):
    return {
        "provider_id": provider,
        "encrypted_secret": crypto.encrypt(secret, provider),
        "encrypted_metadata": crypto.encrypt(json.dumps(metadata), provider) if metadata is not None else None,
        "enabled": True,
        "status": "configured",
        "updated_at": "2026-07-30T12:00:00Z",
        **overrides,
    }


def test_environment_gemini_resolution_is_redacted(monkeypatch):
    secret = "gemini-secret-value"
    resolver = CredentialResolver(make_settings(monkeypatch, GEMINI_API_KEY=secret), CredentialDatabase())

    credential = resolver.resolve(make_decision())

    assert credential.provider_id == "gemini"
    assert credential.secret.get_secret_value() == secret
    assert secret not in repr(credential)
    assert secret not in str(credential)
    assert secret not in json.dumps(credential, default=str)
    assert "to_dict" not in dir(credential)


def test_settings_repr_redacts_environment_secrets(monkeypatch):
    settings = make_settings(monkeypatch, GEMINI_API_KEY="gemini-secret", CLOUDFLARE_AI_TOKEN="cloudflare-secret")

    assert "gemini-secret" not in repr(settings)
    assert "cloudflare-secret" not in repr(settings)


def test_missing_environment_gemini_key_is_safe(monkeypatch):
    resolver = CredentialResolver(make_settings(monkeypatch), CredentialDatabase())

    with pytest.raises(CredentialResolutionError) as error:
        resolver.resolve(make_decision())

    assert error.value.code == "credential_missing"
    assert "GEMINI" not in str(error.value)


def test_environment_cloudflare_requires_token_and_account_id(monkeypatch):
    resolver = CredentialResolver(make_settings(monkeypatch, CLOUDFLARE_AI_TOKEN="cf-secret", CLOUDFLARE_ACCOUNT_ID="account-123"), CredentialDatabase())

    credential = resolver.resolve(make_decision(provider="cloudflare"))

    assert credential.secret.get_secret_value() == "cf-secret"
    assert credential.account_id == "account-123"
    assert "cf-secret" not in repr(credential)

    missing_account = CredentialResolver(make_settings(monkeypatch, CLOUDFLARE_AI_TOKEN="cf-secret"), CredentialDatabase())
    with pytest.raises(CredentialResolutionError) as error:
        missing_account.resolve(make_decision(provider="cloudflare"))
    assert error.value.code == "credential_configuration_error"
    assert "cf-secret" not in str(error.value)


def test_environment_pexels_resolution_fails_safely_without_an_existing_variable(monkeypatch):
    resolver = CredentialResolver(make_settings(monkeypatch), CredentialDatabase())

    with pytest.raises(CredentialResolutionError) as error:
        resolver.resolve(make_decision(provider="cloudflare", visual_source="pexels"), provider_id="pexels")

    assert error.value.code == "credential_configuration_error"


def test_nvidia_resolves_only_the_stored_encrypted_credential(monkeypatch):
    crypto = encryption()
    database = CredentialDatabase(stored_row(crypto, "nvidia", "stored-nvidia-secret"))
    resolver = CredentialResolver(make_settings(monkeypatch), database, crypto)

    credential = resolver.resolve(
        make_decision(provider="nvidia", strategy="stored"),
        credential_strategy="stored",
        provider_id="nvidia",
    )

    assert credential.provider_id == "nvidia"
    assert credential.credential_strategy == "stored"
    assert credential.secret.get_secret_value() == "stored-nvidia-secret"
    assert "stored-nvidia-secret" not in repr(credential)


def test_nvidia_environment_resolution_does_not_fallback_to_stored(monkeypatch):
    crypto = encryption()
    database = CredentialDatabase(stored_row(crypto, "nvidia", "stored-nvidia-secret"))
    resolver = CredentialResolver(make_settings(monkeypatch), database, crypto)

    with pytest.raises(CredentialResolutionError) as error:
        resolver.resolve(
            make_decision(provider="nvidia", strategy="environment"),
            credential_strategy="environment",
            provider_id="nvidia",
        )

    assert error.value.code == "credential_configuration_error"
    assert database.calls == 0


def test_stored_gemini_credential_is_decrypted_only_in_memory(monkeypatch):
    crypto = encryption()
    database = CredentialDatabase(stored_row(crypto, "gemini", "stored-gemini-secret"))
    resolver = CredentialResolver(make_settings(monkeypatch, GEMINI_API_KEY="env-secret"), database, crypto)

    credential = resolver.resolve(make_decision(strategy="stored"), credential_strategy="stored")

    assert credential.secret.get_secret_value() == "stored-gemini-secret"
    assert credential.updated_at == "2026-07-30T12:00:00Z"
    assert "stored-gemini-secret" not in repr(credential)
    assert "cc-aes-gcm" not in repr(credential)


def test_stored_cloudflare_requires_encrypted_account_metadata(monkeypatch):
    crypto = encryption()
    database = CredentialDatabase(stored_row(crypto, "cloudflare", "stored-cf-secret", {"account_id": "stored-account"}))
    resolver = CredentialResolver(make_settings(monkeypatch, CLOUDFLARE_AI_TOKEN="env-secret", CLOUDFLARE_ACCOUNT_ID="env-account"), database, crypto)

    credential = resolver.resolve(make_decision(provider="cloudflare", strategy="stored"), credential_strategy="stored")

    assert credential.secret.get_secret_value() == "stored-cf-secret"
    assert credential.account_id == "stored-account"


def test_stored_strategy_never_falls_back_to_environment(monkeypatch):
    resolver = CredentialResolver(make_settings(monkeypatch, GEMINI_API_KEY="env-secret"), CredentialDatabase(), encryption())

    with pytest.raises(CredentialResolutionError) as error:
        resolver.resolve(make_decision(strategy="stored"), credential_strategy="stored")

    assert error.value.code == "credential_missing"
    assert "env-secret" not in str(error.value)


def test_environment_strategy_never_falls_back_to_stored(monkeypatch):
    crypto = encryption()
    database = CredentialDatabase(stored_row(crypto, "gemini", "stored-secret"))
    resolver = CredentialResolver(make_settings(monkeypatch), database, crypto)

    with pytest.raises(CredentialResolutionError) as error:
        resolver.resolve(make_decision(strategy="environment"), credential_strategy="environment")

    assert error.value.code == "credential_missing"
    assert database.calls == 0


def test_malformed_stored_credential_and_missing_key_are_safe(monkeypatch):
    database = CredentialDatabase({"provider_id": "gemini", "encrypted_secret": "not-ciphertext", "enabled": True, "status": "configured"})
    resolver = CredentialResolver(make_settings(monkeypatch), database, encryption())

    with pytest.raises(CredentialResolutionError) as malformed:
        resolver.resolve(make_decision(strategy="stored"), credential_strategy="stored")
    assert malformed.value.code == "credential_decryption_error"
    assert "not-ciphertext" not in str(malformed.value)

    missing_key = CredentialResolver(make_settings(monkeypatch), database)
    with pytest.raises(CredentialResolutionError) as missing:
        missing_key.resolve(make_decision(strategy="stored"), credential_strategy="stored")
    assert missing.value.code == "encryption_key_missing"


def test_invalid_strategy_is_rejected_without_loading_database(monkeypatch):
    database = CredentialDatabase()
    resolver = CredentialResolver(make_settings(monkeypatch), database)

    with pytest.raises(CredentialResolutionError) as error:
        resolver.resolve(make_decision(), credential_strategy="unknown")

    assert error.value.code == "credential_source_invalid"
    assert database.calls == 0


def test_mismatched_provider_cannot_resolve_another_provider_credential(monkeypatch):
    resolver = CredentialResolver(make_settings(monkeypatch, GEMINI_API_KEY="gemini-secret"), CredentialDatabase())

    with pytest.raises(CredentialResolutionError) as error:
        resolver.resolve(make_decision(provider="gemini"), provider_id="pexels")

    assert error.value.code == "provider_mismatch"


def test_execution_context_resolves_only_required_credentials(monkeypatch):
    crypto = encryption()
    database = CredentialDatabase(stored_row(crypto, "cloudflare", "stored-secret", {"account_id": "account"}))
    resolver = CredentialResolver(make_settings(monkeypatch), database, crypto)
    decision = make_decision(
        provider="cloudflare",
        strategy="stored",
        image_provider="cloudflare",
        image_model="@cf/black-forest-labs/flux-1-schnell",
    )

    context = build_execution_context(decision, resolver, credential_strategy="stored", job_id="job-1")

    assert isinstance(context, ExecutionContext)
    assert context.job_id == "job-1"
    assert len(context.credentials) == 1
    assert context.credentials[0].secret.get_secret_value() == "stored-secret"
    assert "stored-secret" not in repr(context)


def test_execution_context_preserves_colon_model_id_and_does_not_resolve_ai_for_pexels(monkeypatch):
    crypto = encryption()
    database = CredentialDatabase([
        stored_row(crypto, "cloudflare", "cloudflare-secret", {"account_id": "account"}),
        stored_row(crypto, "pexels", "pexels-secret"),
    ])
    resolver = CredentialResolver(make_settings(monkeypatch), database, crypto)
    decision = RoutingDecision(
        text_provider="cloudflare",
        text_model="@cf/meta/llama-3.1-8b-instruct",
        visual_source="pexels",
        image_provider=None,
        image_model=None,
        credential_strategy="stored",
        routing_version=1,
    )

    context = build_execution_context(decision, resolver, credential_strategy="stored")

    assert context.routing_decision.text_model == "@cf/meta/llama-3.1-8b-instruct"
    assert [item.provider_id for item in context.credentials] == ["cloudflare", "pexels"]
