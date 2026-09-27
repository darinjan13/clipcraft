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
from app.services.ai.pixabay_stock import HttpxPixabayTransport
from app.services.credential_crypto import CredentialEncryption

SECRET = "internal-signing-secret"
JPEG_PAYLOAD = b"\xff\xd8\xff" + bytes(range(32))


class _FakeDatabase:
    def __init__(self, credential=None):
        self.credential = credential

    def get_credential_for_test(self, provider_id):
        return self.credential


def make_pixabay_request(**overrides):
    request = {
        "job_id": str(uuid4()),
        "provider_id": "pixabay",
        "credential_source": "stored",
        "operation": "stock_media",
        "input": {
            "query": "morning forest",
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


def signed_pixabay_request(payload, *, secret=SECRET):
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


def _stored_client(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY", key)
    encryption = CredentialEncryption.from_environment()
    database = _FakeDatabase({
        "encrypted_secret": encryption.encrypt("pixabay-secret", "pixabay"),
        "enabled": True,
        "status": "configured",
    })
    return TestClient(create_app(database_client=database, data_dir=tmp_path))


def test_valid_pixabay_photo_request_saves_file(monkeypatch, tmp_path):
    async def fake_search(self, **kwargs):
        return {"hits": [{"largeImageURL": "https://example.com/a.jpg"}]}

    async def fake_download(self, **kwargs):
        return JPEG_PAYLOAD

    monkeypatch.setattr(HttpxPixabayTransport, "search", fake_search)
    monkeypatch.setattr(HttpxPixabayTransport, "download", fake_download)

    client = _stored_client(monkeypatch, tmp_path)
    payload = make_pixabay_request()
    body, headers = signed_pixabay_request(payload)
    response = client.post("/internal/ai/stock/execute", content=body, headers=headers)

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["provider_id"] == "pixabay"
    assert result["media_type"] == "photo"
    assert result["local_path"].endswith("scene-00.jpg")
    assert "pixabay-secret" not in response.text
    saved = Path(result["local_path"])
    assert saved.is_file()
    assert saved.read_bytes() == JPEG_PAYLOAD


def test_unresolved_both_media_type_is_rejected(monkeypatch, tmp_path):
    client = _stored_client(monkeypatch, tmp_path)
    payload = make_pixabay_request(input={
        "query": "morning forest",
        "media_type": "both",
        "orientation": "portrait",
        "scene_id": "scene-1",
        "scene_index": 0,
    })
    body, headers = signed_pixabay_request(payload)

    response = client.post("/internal/ai/stock/execute", content=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AI_EXECUTION_FAILED"


def test_unknown_stock_provider_is_rejected(monkeypatch, tmp_path):
    client = _stored_client(monkeypatch, tmp_path)
    payload = make_pixabay_request(provider_id="acme")
    body, headers = signed_pixabay_request(payload)

    response = client.post("/internal/ai/stock/execute", content=body, headers=headers)

    assert response.status_code == 422
