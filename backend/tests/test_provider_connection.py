import base64
import json
import os
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.credential_crypto import CredentialEncryption
from app.services.ai import provider_registry


class FakeConnectionDatabase:
    url = "http://database.test"

    def __init__(self):
        self.rows = {}
        self.reject_test_update = False
        self.delete_during_update = False
        self.replace_during_update = False

    def list_credentials(self):
        return list(self.rows.values())

    def get_credential(self, provider_id):
        return self.rows.get(provider_id)

    def get_credential_for_test(self, provider_id):
        return self.rows.get(provider_id)

    def upsert_credential(self, data):
        existing = self.rows.get(data["provider_id"])
        row = {"id": existing.get("id", str(uuid4())) if existing else str(uuid4()), **data}
        row.setdefault("updated_at", "2026-07-30T12:00:00+00:00")
        self.rows[data["provider_id"]] = row
        return row

    def delete_credential(self, provider_id):
        self.rows.pop(provider_id, None)

    def update_credential_test(self, provider_id, expected_updated_at, expected_ciphertext, data):
        row = self.rows.get(provider_id)
        if self.delete_during_update:
            self.rows.pop(provider_id, None)
            return False
        if self.replace_during_update:
            row["encrypted_secret"] = "replacement-ciphertext"
            row["updated_at"] = "2026-07-30T12:01:00+00:00"
            row["last_test_status"] = "newer-result"
            return False
        if self.reject_test_update or not row:
            return False
        if row.get("updated_at") != expected_updated_at or row.get("encrypted_secret") != expected_ciphertext:
            return False
        row.update(data)
        return True


class Response:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}
        self.headers = {}
        self.content = json.dumps(self._body).encode()

    def json(self):
        return self._body


def make_client(tmp_path, database, monkeypatch, key=True):
    if key:
        monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    else:
        monkeypatch.delenv("AI_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    return TestClient(create_app(database_client=database, data_dir=tmp_path))


def put_credential(client, provider_id, secret="provider-secret", metadata=None):
    body = {"secret": secret}
    if metadata is not None:
        body["metadata"] = metadata
    assert client.put(f"/api/ai/credentials/{provider_id}", json=body).status_code == 200


def test_gemini_connection_test_succeeds_without_generation(monkeypatch, tmp_path):
    database = FakeConnectionDatabase()
    client = make_client(tmp_path, database, monkeypatch)
    put_credential(client, "gemini", "gemini-secret")
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response(200)

    monkeypatch.setattr("httpx.request", fake_request)
    response = client.post("/api/ai/credentials/gemini/test")

    assert response.json()["status"] == "connected"
    assert response.json()["persisted"] is True
    assert calls[0][0:2] == ("GET", "https://generativelanguage.googleapis.com/v1beta/models")
    assert database.rows["gemini"]["last_test_status"] == "connected"


def test_cloudflare_connection_test_uses_encrypted_account_metadata(monkeypatch, tmp_path):
    database = FakeConnectionDatabase()
    client = make_client(tmp_path, database, monkeypatch)
    put_credential(client, "cloudflare", "cloudflare-secret", {"account_id": "account-123"})
    calls = []
    monkeypatch.setattr("httpx.request", lambda method, url, **kwargs: calls.append((method, url, kwargs)) or Response(200))

    response = client.post("/api/ai/credentials/cloudflare/test")

    assert response.json()["status"] == "connected"
    assert "account-123" in calls[0][1]
    assert calls[0][2]["headers"]["Authorization"] == "Bearer cloudflare-secret"


def test_pexels_connection_test_uses_one_item_request(monkeypatch, tmp_path):
    database = FakeConnectionDatabase()
    client = make_client(tmp_path, database, monkeypatch)
    put_credential(client, "pexels", "pexels-secret")
    calls = []
    monkeypatch.setattr("httpx.request", lambda method, url, **kwargs: calls.append((method, url, kwargs)) or Response(200))

    response = client.post("/api/ai/credentials/pexels/test")

    assert response.json()["status"] == "connected"
    assert calls[0][1] == "https://api.pexels.com/v1/curated?per_page=1"


def test_unknown_disabled_and_unimplemented_providers_are_safe(monkeypatch, tmp_path):
    database = FakeConnectionDatabase()
    client = make_client(tmp_path, database, monkeypatch)
    unknown = client.post("/api/ai/credentials/not-a-provider/test")
    nvidia = client.post("/api/ai/credentials/nvidia/test")
    original_registry = provider_registry.PROVIDER_REGISTRY
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
        for provider in original_registry
    )
    try:
        disabled = client.post("/api/ai/credentials/gemini/test")
    finally:
        provider_registry.PROVIDER_REGISTRY = original_registry

    assert unknown.status_code == 404
    assert nvidia.json()["status"] == "not_implemented"
    assert disabled.status_code == 422
    assert disabled.json()["detail"]["code"] == "disabled_provider"


def test_no_stored_credential_does_not_fall_back_to_environment(monkeypatch, tmp_path):
    database = FakeConnectionDatabase()
    client = make_client(tmp_path, database, monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "environment-secret")

    response = client.post("/api/ai/credentials/gemini/test")

    assert response.json()["status"] == "configuration_error"
    assert "environment-secret" not in response.text


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(401, "invalid_credentials"), (402, "quota_exceeded"), (429, "rate_limited"), (500, "provider_error")],
)
def test_provider_http_errors_are_normalized(monkeypatch, tmp_path, status_code, expected):
    database = FakeConnectionDatabase()
    client = make_client(tmp_path, database, monkeypatch)
    put_credential(client, "gemini")
    monkeypatch.setattr("httpx.request", lambda *args, **kwargs: Response(status_code, {"secret": "raw-provider-body"}))

    response = client.post("/api/ai/credentials/gemini/test")

    assert response.json()["status"] == expected
    assert "raw-provider-body" not in response.text
    assert database.rows["gemini"]["last_test_status"] == expected


def test_timeout_malformed_ciphertext_and_missing_key_are_safe(monkeypatch, tmp_path):
    database = FakeConnectionDatabase()
    client = make_client(tmp_path, database, monkeypatch)
    put_credential(client, "gemini")
    database.rows["gemini"]["encrypted_secret"] = "malformed"
    malformed = client.post("/api/ai/credentials/gemini/test")
    assert malformed.json()["status"] == "configuration_error"

    database = FakeConnectionDatabase()
    client = make_client(tmp_path, database, monkeypatch, key=True)
    put_credential(client, "gemini")
    monkeypatch.setattr("httpx.request", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.TimeoutException("timeout")))
    timeout = client.post("/api/ai/credentials/gemini/test")
    assert timeout.json()["status"] == "timeout"

    database = FakeConnectionDatabase()
    client = make_client(tmp_path, database, monkeypatch, key=False)
    missing_key = client.post("/api/ai/credentials/gemini/test")
    assert missing_key.json()["status"] == "configuration_error"


def test_stale_test_cannot_overwrite_replacement_or_deletion(monkeypatch, tmp_path):
    database = FakeConnectionDatabase()
    client = make_client(tmp_path, database, monkeypatch)
    put_credential(client, "gemini")
    monkeypatch.setattr("httpx.request", lambda *args, **kwargs: Response(200))

    database.replace_during_update = True
    replaced = client.post("/api/ai/credentials/gemini/test")
    assert replaced.json()["status"] == "connected"
    assert replaced.json()["persisted"] is False
    assert database.rows["gemini"]["last_test_status"] == "newer-result"

    database.replace_during_update = False
    database.delete_during_update = True
    deleted = client.post("/api/ai/credentials/gemini/test")
    assert deleted.json()["persisted"] is False
    assert "gemini" not in database.rows


def test_authorization_headers_and_secrets_are_not_logged_or_returned(monkeypatch, tmp_path, caplog):
    database = FakeConnectionDatabase()
    client = make_client(tmp_path, database, monkeypatch)
    put_credential(client, "gemini", "log-secret")
    monkeypatch.setattr("httpx.request", lambda *args, **kwargs: Response(401, {"Authorization": "log-secret"}))

    response = client.post("/api/ai/credentials/gemini/test")

    assert "log-secret" not in response.text
    assert "Authorization" not in caplog.text
    assert "log-secret" not in caplog.text
