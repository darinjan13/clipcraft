import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ai.pexels_stock import HttpxPexelsTransport
from app.services.credential_crypto import CredentialEncryption

SECRET = "internal-signing-secret"
JPEG_PAYLOAD = b"\xff\xd8\xff" + bytes(range(32))


class _FakeDatabase:
    def __init__(self, credential=None):
        self.credential = credential

    def get_credential_for_test(self, provider_id):
        return self.credential


def make_stock_request(**overrides):
    request = {
        "job_id": str(uuid4()),
        "provider_id": "pexels",
        "credential_source": "stored",
        "operation": "stock_media",
        "input": {
            "query": "rainy window",
            "media_type": "photo",
            "orientation": "portrait",
            "scene_id": "scene-1",
            "scene_index": 0,
        },
        "routing_version": "1",
        "request_id": str(uuid4()),
    }
    request.update(overrides)
    return request


def signed_stock_request(payload, *, secret=SECRET):
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    nonce = str(uuid4())
    message = f"{timestamp}\n{nonce}\n".encode() + body
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return body, {
        "X-ClipCraft-Timestamp": timestamp,
        "X-ClipCraft-Nonce": nonce,
        "X-ClipCraft-Signature": signature,
    }


def test_stock_route_is_hidden_and_rejects_missing_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))

    response = client.post("/internal/ai/stock/execute", content=b"{}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INTERNAL_AUTH_REQUIRED"
    assert "/internal/ai/stock/execute" not in client.get("/openapi.json").text


def test_valid_pexels_photo_request_saves_file(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY", key)
    encryption = CredentialEncryption.from_environment()
    database = _FakeDatabase({
        "encrypted_secret": encryption.encrypt("pexels-secret", "pexels"),
        "enabled": True,
        "status": "configured",
    })

    async def fake_search(self, **kwargs):
        return {"photos": [{"id": 1, "src": {"original": "https://example.com/a.jpg"}}]}

    async def fake_download(self, **kwargs):
        return JPEG_PAYLOAD

    monkeypatch.setattr(HttpxPexelsTransport, "search", fake_search)
    monkeypatch.setattr(HttpxPexelsTransport, "download", fake_download)

    client = TestClient(create_app(database_client=database, data_dir=tmp_path))
    payload = make_stock_request()
    body, headers = signed_stock_request(payload)
    response = client.post("/internal/ai/stock/execute", content=body, headers=headers)

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["media_type"] == "photo"
    assert result["mime_type"] == "image/jpeg"
    assert result["local_path"].endswith("scene-00.jpg")
    assert "pexels-secret" not in response.text
    saved = Path(result["local_path"])
    assert saved.is_file()
    assert saved.read_bytes() == JPEG_PAYLOAD


def test_unresolved_both_media_type_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY", key)
    encryption = CredentialEncryption.from_environment()
    database = _FakeDatabase({
        "encrypted_secret": encryption.encrypt("pexels-secret", "pexels"),
        "enabled": True,
        "status": "configured",
    })
    client = TestClient(create_app(database_client=database, data_dir=tmp_path))
    payload = make_stock_request(input={
        "query": "rainy window",
        "media_type": "both",
        "orientation": "portrait",
        "scene_id": "scene-1",
        "scene_index": 0,
    })
    body, headers = signed_stock_request(payload)

    response = client.post("/internal/ai/stock/execute", content=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AI_EXECUTION_FAILED"
