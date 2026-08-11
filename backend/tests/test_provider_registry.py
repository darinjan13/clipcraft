import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ai.provider_registry import (
    RegistryValidationError,
    resolve_provider_selection,
    validate_model_selection,
)


def make_client(tmp_path):
    return TestClient(create_app(data_dir=tmp_path))


def test_provider_listing_exposes_one_canonical_registry_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "do-not-return-this-secret")
    response = make_client(tmp_path).get("/api/ai/providers")

    assert response.status_code == 200
    providers = response.json()["providers"]
    provider_ids = {provider["provider_id"] for provider in providers}
    assert {"gemini", "cloudflare", "nvidia", "pexels"} <= provider_ids
    assert "do-not-return-this-secret" not in response.text
    for provider in providers:
        assert {
            "provider_id",
            "display_name",
            "provider_type",
            "capabilities",
            "requires_credential",
            "credential_type",
            "enabled",
            "implemented",
            "models",
            "default_model",
        } <= provider.keys()


def test_model_endpoint_filters_by_capability_and_preserves_raw_ids(tmp_path):
    client = make_client(tmp_path)

    response = client.get("/api/ai/models", params={"capability": "text"})

    assert response.status_code == 200
    models = response.json()["models"]
    assert models
    assert {model["capability"] for model in models} == {"text"}
    assert all("provider_id" in model and "model_id" in model for model in models)

    gemini_models = client.get("/api/ai/models", params={"provider_id": "gemini"}).json()["models"]
    assert any(model["model_id"] == "gemini-2.5-flash:image-preview" for model in gemini_models)


def test_provider_detail_and_unknown_provider(tmp_path):
    client = make_client(tmp_path)

    detail = client.get("/api/ai/providers/cloudflare")
    missing = client.get("/api/ai/providers/not-a-provider")

    assert detail.status_code == 200
    assert detail.json()["provider_id"] == "cloudflare"
    assert missing.status_code == 404


@pytest.mark.parametrize(
    ("provider_id", "model_id", "capability", "error_code"),
    [
        ("not-a-provider", "model", "text", "unknown_provider"),
        ("gemini", "not-a-model", "text", "unknown_model"),
        ("gemini", "@cf/meta/llama-3.1-8b-instruct", "text", "provider_model_mismatch"),
        ("nvidia", "nvidia/llama-3.1-nemotron-ultra-253b-v1", "text", "provider_unimplemented"),
        ("gemini", "gemini-2.5-flash:image-preview", "image", "model_unimplemented"),
    ],
)
def test_validation_rejects_invalid_provider_model_combinations(
    provider_id, model_id, capability, error_code
):
    with pytest.raises(RegistryValidationError) as error:
        validate_model_selection(provider_id, model_id, capability)

    assert error.value.code == error_code


def test_model_endpoint_rejects_unsupported_capability(tmp_path):
    response = make_client(tmp_path).get("/api/ai/models", params={"capability": "audio"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unsupported_capability"


def test_default_model_resolution_is_stable():
    assert resolve_provider_selection() == {
        "text_provider": "gemini",
        "text_model": "gemini-2.5-flash",
        "image_provider": "cloudflare",
        "image_model": "@cf/black-forest-labs/flux-1-schnell",
    }


def test_registry_does_not_copy_environment_values_into_responses(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-key")
    monkeypatch.setenv("GEMINI_TEXT_MODEL", "secret-model-name")

    response = make_client(tmp_path).get("/api/ai/models")

    assert response.status_code == 200
    assert "super-secret-key" not in response.text
    assert "secret-model-name" not in response.text
