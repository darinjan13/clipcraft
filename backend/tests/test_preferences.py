from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ai import provider_registry


class FakePreferencesDatabase:
    url = "http://database.test"

    def __init__(self, row=None):
        self.row = row
        self.upsert_count = 0

    def get_preferences(self):
        return self.row

    def upsert_preferences(self, data):
        self.upsert_count += 1
        self.row = {"id": True, **data}
        return self.row


class FakeJobDatabase(FakePreferencesDatabase):
    def __init__(self):
        super().__init__()
        self.rows = []

    def insert_job(self, data):
        row = {"id": str(uuid4()), **data}
        self.rows.append(row)
        return row


class FakeWorkflow:
    def get_status(self, job_id):
        return {"found": True, "status": "queued", "progress": 0}


def make_client(tmp_path, database):
    return TestClient(create_app(database_client=database, workflow_client=FakeWorkflow(), data_dir=tmp_path))


def test_get_preferences_returns_canonical_defaults_when_singleton_is_absent(tmp_path):
    client = make_client(tmp_path, FakePreferencesDatabase())

    response = client.get("/api/settings/preferences")

    assert response.status_code == 200
    assert response.json() == {
        "default_text_provider": "gemini",
        "default_text_model": "gemini-2.5-flash",
        "default_visual_source": "ai",
        "default_image_provider": "cloudflare",
        "default_image_model": "@cf/black-forest-labs/flux-1-schnell",
        "default_pexels_media_type": None,
        "default_pexels_orientation": None,
        "updated_at": None,
    }


def test_put_and_get_preferences_use_one_persisted_singleton(tmp_path):
    database = FakePreferencesDatabase()
    client = make_client(tmp_path, database)
    body = {
        "default_text_provider": "cloudflare",
        "default_text_model": "@cf/meta/llama-3.1-8b-instruct",
        "default_visual_source": "ai",
        "default_image_provider": "cloudflare",
        "default_image_model": "@cf/black-forest-labs/flux-1-schnell",
        "default_pexels_media_type": "photo",
        "default_pexels_orientation": "landscape",
    }

    first = client.put("/api/settings/preferences", json=body)
    second = client.put(
        "/api/settings/preferences",
        json={**body, "default_text_provider": "gemini", "default_text_model": "gemini-2.5-flash"},
    )
    fetched = client.get("/api/settings/preferences")

    assert first.status_code == 200
    assert second.status_code == 200
    assert fetched.status_code == 200
    assert fetched.json()["default_text_provider"] == "gemini"
    assert database.upsert_count == 2
    assert database.row["id"] is True


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("default_text_provider", "unknown", "unknown_provider"),
        ("default_text_model", "not-a-model", "unknown_model"),
        ("default_text_model", "@cf/black-forest-labs/flux-1-schnell", "provider_model_mismatch"),
        ("default_text_provider", "nvidia", "provider_unimplemented"),
        ("default_visual_source", "not-a-source", "unsupported_visual_source"),
        ("default_pexels_media_type", "audio", "unsupported_pexels_media_type"),
        ("default_pexels_orientation", "diagonal", "unsupported_pexels_orientation"),
    ],
)
def test_invalid_preferences_return_explicit_validation_errors(tmp_path, field, value, code):
    client = make_client(tmp_path, FakePreferencesDatabase())

    response = client.put("/api/settings/preferences", json={field: value})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


def test_disabled_provider_is_rejected(tmp_path, monkeypatch):
    original = provider_registry.PROVIDER_REGISTRY
    provider_registry.PROVIDER_REGISTRY = tuple(
        provider_registry.ProviderDefinition(
            provider_id=provider.provider_id,
            display_name=provider.display_name,
            provider_type=provider.provider_type,
            capabilities=provider.capabilities,
            requires_credential=provider.requires_credential,
            credential_type=provider.credential_type,
            enabled=False if provider.provider_id == "gemini" else provider.enabled,
            implemented=provider.implemented,
            models=provider.models,
            default_model=provider.default_model,
        )
        for provider in original
    )
    try:
        response = make_client(tmp_path, FakePreferencesDatabase()).put(
            "/api/settings/preferences",
            json={"default_text_provider": "gemini"},
        )
    finally:
        provider_registry.PROVIDER_REGISTRY = original

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "disabled_provider"


def test_preferences_do_not_change_generation_defaults(tmp_path):
    database = FakeJobDatabase()
    client = make_client(tmp_path, database)
    preferences = client.put(
        "/api/settings/preferences",
        json={
            "default_text_provider": "cloudflare",
            "default_text_model": "@cf/meta/llama-3.1-8b-instruct",
            "default_image_provider": "cloudflare",
            "default_image_model": "@cf/black-forest-labs/flux-1-schnell",
        },
    )
    response = client.post(
        "/api/videos",
        json={
            "prompt": "Preferences must not route generation",
            "duration": 30,
            "style": "Educational",
            "voice": "Neutral",
            "captions": "Clean",
        },
    )

    assert preferences.status_code == 200
    assert response.status_code == 202
    assert "text_provider" not in database.rows[0]
    assert "text_model" not in database.rows[0]


def test_preference_responses_never_include_secrets_or_environment_values(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "environment-secret")
    database = FakePreferencesDatabase()
    client = make_client(tmp_path, database)

    response = client.put(
        "/api/settings/preferences",
        json={"default_text_provider": "gemini", "default_text_model": "gemini-2.5-flash"},
    )

    assert response.status_code == 200
    assert "environment-secret" not in response.text
    assert "encrypted_secret" not in response.text


def test_get_rejects_corrupt_persisted_preferences_without_leaking_values(tmp_path):
    database = FakePreferencesDatabase({
        "id": True,
        "default_text_provider": "not-a-provider",
        "default_text_model": "secret-model",
    })
    client = make_client(tmp_path, database)

    response = client.get("/api/settings/preferences")

    assert response.status_code == 500
    assert response.json()["detail"] == "stored application preferences are invalid"
    assert "secret-model" not in response.text
