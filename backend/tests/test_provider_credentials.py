import base64
import os
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app


class CredentialDatabase:
    url = "http://database.test"

    def __init__(self):
        self.rows = {}

    def list_credentials(self):
        return list(self.rows.values())

    def get_credential(self, provider_id):
        return self.rows.get(provider_id)

    def upsert_credential(self, data):
        existing = self.rows.get(data["provider_id"])
        row = {"id": existing.get("id", str(uuid4())) if existing else str(uuid4()), **data}
        self.rows[data["provider_id"]] = row
        return row

    def delete_credential(self, provider_id):
        self.rows.pop(provider_id, None)


def make_client(tmp_path, database, monkeypatch, key=True):
    if key:
        monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode())
    else:
        monkeypatch.delenv("AI_CREDENTIAL_ENCRYPTION_KEY", raising=False)
    return TestClient(create_app(database_client=database, data_dir=tmp_path))


def test_put_credential_encrypts_secret_and_returns_masked_metadata(tmp_path, monkeypatch):
    database = CredentialDatabase()
    client = make_client(tmp_path, database, monkeypatch)

    response = client.put(
        "/api/ai/credentials/gemini",
        json={"secret": "gemini-secret-value", "metadata": {"label": "primary"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "provider_id": "gemini",
        "configured": True,
        "enabled": True,
        "status": "configured",
        "secret_last_four": "alue",
        "last_tested_at": None,
        "last_test_status": None,
        "last_test_error_safe": None,
    }
    stored = database.rows["gemini"]
    assert stored["encrypted_secret"] != "gemini-secret-value"
    assert stored["encrypted_metadata"] != '{"label": "primary"}'
    assert "gemini-secret-value" not in response.text
    assert "encrypted_secret" not in response.text


def test_list_masks_credentials_and_replacement_is_atomic_metadata_reset(tmp_path, monkeypatch):
    database = CredentialDatabase()
    client = make_client(tmp_path, database, monkeypatch)
    client.put(
        "/api/ai/credentials/cloudflare",
        json={"secret": "first-secret", "enabled": True},
    )
    database.rows["cloudflare"].update({
        "last_tested_at": "2026-07-30T12:00:00Z",
        "last_test_status": "success",
        "last_test_error_safe": None,
    })
    first_ciphertext = database.rows["cloudflare"]["encrypted_secret"]

    replacement = client.put(
        "/api/ai/credentials/cloudflare",
        json={"secret": "second-secret", "enabled": False},
    )
    listed = client.get("/api/ai/credentials")

    assert replacement.status_code == 200
    assert replacement.json()["enabled"] is False
    assert replacement.json()["status"] == "disabled"
    assert replacement.json()["last_test_status"] is None
    assert database.rows["cloudflare"]["encrypted_secret"] != first_ciphertext
    assert listed.status_code == 200
    assert listed.json()["credentials"][0]["secret_last_four"] == "cret"
    assert "second-secret" not in listed.text


def test_delete_credential_is_idempotent(tmp_path, monkeypatch):
    database = CredentialDatabase()
    client = make_client(tmp_path, database, monkeypatch)
    client.put("/api/ai/credentials/gemini", json={"secret": "delete-me"})

    first = client.delete("/api/ai/credentials/gemini")
    second = client.delete("/api/ai/credentials/gemini")

    assert first.status_code == 204
    assert second.status_code == 204
    assert "gemini" not in database.rows


def test_credential_operations_fail_closed_without_encryption_key(tmp_path, monkeypatch):
    database = CredentialDatabase()
    client = make_client(tmp_path, database, monkeypatch, key=False)

    response = client.put("/api/ai/credentials/gemini", json={"secret": "must-not-store"})

    assert response.status_code == 503
    assert response.json()["detail"] == "credential encryption is not configured"
    assert database.rows == {}
    assert "must-not-store" not in response.text


def test_credential_provider_must_exist_in_canonical_registry(tmp_path, monkeypatch):
    database = CredentialDatabase()
    client = make_client(tmp_path, database, monkeypatch)

    response = client.put("/api/ai/credentials/not-a-provider", json={"secret": "secret"})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "unknown_provider"
    assert database.rows == {}
