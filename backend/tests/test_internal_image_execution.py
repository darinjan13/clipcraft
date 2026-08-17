import base64
import hashlib
import hmac
import json
import os
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ai.cloudflare_execution import HttpxCloudflareTransport
from app.services.credential_crypto import CredentialEncryption

SECRET = "internal-signing-secret"
PNG_PAYLOAD = b"\x89PNG\r\n\x1a\n" + bytes(range(16))


def make_request(**overrides):
    request = {
        "job_id": str(uuid4()),
        "provider_id": "cloudflare",
        "model_id": "@cf/black-forest-labs/flux-1-schnell",
        "credential_source": "environment",
        "operation": "image_generation",
        "input": {
            "prompt": "A cat on a chair",
            "scene_id": "scene-1",
            "scene_index": 0,
            "width": 512,
            "height": 512,
        },
        "routing_version": "1",
        "request_id": str(uuid4()),
    }
    request.update(overrides)
    return request


def signed_request(payload, *, nonce=None, secret=SECRET):
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    nonce = nonce or str(uuid4())
    message = f"{timestamp}\n{nonce}\n".encode() + body
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return body, {
        "X-ClipCraft-Timestamp": timestamp,
        "X-ClipCraft-Nonce": nonce,
        "X-ClipCraft-Signature": signature,
    }


def image_response(body=None, *, status_code=200):
    return type("Response", (), {"status_code": status_code, "body": body, "headers": {}})()


def install_fake_transport(monkeypatch, *, image=None, body=None, status_code=200):
    fake_body = body if body is not None else {"success": True, "result": {"image": image}}
    calls = []

    async def fake_run(self, **kwargs):
        calls.append(kwargs)
        return image_response(fake_body, status_code=status_code)

    monkeypatch.setattr(HttpxCloudflareTransport, "run", fake_run)
    return calls


def test_internal_image_route_is_hidden_and_rejects_missing_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))

    response = client.post("/internal/ai/image/execute", content=b"{}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INTERNAL_AUTH_REQUIRED"
    assert "/internal/ai/image/execute" not in client.get("/openapi.json").text
    assert "/api/ai/models" in client.get("/openapi.json").text


def test_internal_image_route_rejects_oversized_body_before_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))

    response = client.post("/internal/ai/image/execute", content=b"x" * (1024 * 1024 + 1))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "AI_EXECUTION_FAILED"


def test_valid_cloudflare_request_returns_normalized_result(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    image = base64.b64encode(PNG_PAYLOAD).decode()
    install_fake_transport(monkeypatch, image=image)

    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request())

    response = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["capability"] == "image_generation"
    assert result["provider_id"] == "cloudflare"
    assert result["model_id"] == "@cf/black-forest-labs/flux-1-schnell"
    assert result["image_base64"] == image
    assert result["format"] == "png"
    assert result["scene_id"] == "scene-1"
    assert result["scene_index"] == 0
    assert result["width"] == 512
    assert result["height"] == 512
    assert "test-cf-token" not in response.text
    assert "prompt" not in result


def test_prompt_alias_is_resolved_with_documented_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    calls = install_fake_transport(monkeypatch, image=base64.b64encode(PNG_PAYLOAD).decode())

    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    payload = make_request(
        input={
            "visualPrompt": "visual alias",
            "image_prompt": "snake alias",
        }
    )
    body, headers = signed_request(payload)
    client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert calls[0]["body"]["prompt"] == "snake alias"


def test_prompt_alias_falls_back_to_visual_alias(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    calls = install_fake_transport(monkeypatch, image=base64.b64encode(PNG_PAYLOAD).decode())

    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    payload = make_request(input={"visual_prompt": "visual snake alias"})
    body, headers = signed_request(payload)
    client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert calls[0]["body"]["prompt"] == "visual snake alias"


def test_missing_prompt_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    payload = make_request(input={"scene_id": "scene-1"})
    body, headers = signed_request(payload)

    response = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AI_EXECUTION_FAILED"


def test_stored_cloudflare_credential_is_used_without_environment_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY", key)
    encryption = CredentialEncryption.from_environment()
    database = _FakeDatabase({
        "encrypted_secret": encryption.encrypt("stored-cf-key", "cloudflare"),
        "encrypted_metadata": encryption.encrypt(json.dumps({"account_id": "stored-cf-account"}), "cloudflare"),
        "enabled": True,
        "status": "configured",
    })
    image = base64.b64encode(PNG_PAYLOAD).decode()
    calls = install_fake_transport(monkeypatch, image=image)

    client = TestClient(create_app(database_client=database, data_dir=tmp_path))
    payload = make_request(credential_source="stored")
    body, headers = signed_request(payload)

    response = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["image_base64"] == image
    assert calls[0]["api_key"] == "stored-cf-key"
    assert calls[0]["account_id"] == "stored-cf-account"
    assert "stored-cf-key" not in response.text


def test_stored_credential_does_not_fallback_to_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "environment-key")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "environment-account")
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request(credential_source="stored"))

    response = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_CREDENTIAL_MISSING"
    assert "environment-key" not in response.text


def test_unknown_provider_and_model_are_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))

    for changes, expected in [
        ({"provider_id": "unknown"}, "AI_PROVIDER_UNKNOWN"),
        ({"model_id": "unknown"}, "AI_MODEL_UNKNOWN"),
    ]:
        payload = make_request(**changes)
        body, headers = signed_request(payload)
        response = client.post("/internal/ai/image/execute", content=body, headers=headers)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == expected


def test_duplicate_request_nonce_is_rejected_before_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    install_fake_transport(monkeypatch, image=base64.b64encode(PNG_PAYLOAD).decode())
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request(), nonce="same-nonce")

    first = client.post("/internal/ai/image/execute", content=body, headers=headers)
    second = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "INTERNAL_REQUEST_REPLAYED"


def test_arbitrary_headers_and_urls_are_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    payload = make_request(input={"prompt": "cat", "headers": {"Authorization": "Bearer secret"}})
    body, headers = signed_request(payload)

    response = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AI_EXECUTION_FAILED"
    assert "secret" not in response.text


def test_invalid_base64_from_provider_is_normalized(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    install_fake_transport(monkeypatch, image="not-base64!!!")
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request())

    response = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_RESPONSE_INVALID"
    assert "not-base64" not in response.text


def test_empty_image_from_provider_is_normalized(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    install_fake_transport(monkeypatch, image="")
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request())

    response = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_RESPONSE_EMPTY"


def test_provider_output_and_raw_errors_are_normalized(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    install_fake_transport(monkeypatch, status_code=401, body={"success": False, "errors": [{"message": "provider secret body"}]})
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request())

    response = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AI_CREDENTIAL_INVALID"
    assert "provider secret body" not in response.text
    assert "test-cf-token" not in response.text


def test_only_two_internal_execution_routes_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    routes = [route.path for route in client.app.routes if getattr(route, "path", "").startswith("/internal/ai/")]

    assert sorted(routes) == ["/internal/ai/image/execute", "/internal/ai/text/execute"]
    openapi = client.get("/openapi.json").text
    assert "/internal/ai/image/execute" not in openapi
    assert "/internal/ai/text/execute" not in openapi


def test_image_route_shares_the_signing_nonce_store(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    install_fake_transport(monkeypatch, image=base64.b64encode(PNG_PAYLOAD).decode())

    async def fake_generate(self, **kwargs):
        from app.services.ai.gemini_execution import GeminiResponse
        return GeminiResponse(200, {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    monkeypatch.setattr("app.services.ai.gemini_execution.HttpxGeminiTransport.generate", fake_generate)
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    shared_nonce = str(uuid4())
    text_body, text_headers = signed_request(_text_request(), nonce=shared_nonce)
    image_body, image_headers = signed_request(make_request(), nonce=shared_nonce)

    text_response = client.post("/internal/ai/text/execute", content=text_body, headers=text_headers)
    image_response = client.post("/internal/ai/image/execute", content=image_body, headers=image_headers)

    assert text_response.status_code == 200
    assert image_response.status_code == 401
    assert image_response.json()["error"]["code"] == "INTERNAL_REQUEST_REPLAYED"


def test_prompt_beats_aliases(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    calls = install_fake_transport(monkeypatch, image=base64.b64encode(PNG_PAYLOAD).decode())

    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    payload = make_request(input={"prompt": "primary", "image_prompt": "alias", "visualPrompt": "visual"})
    body, headers = signed_request(payload)
    client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert calls[0]["body"]["prompt"] == "primary"


def test_whitespace_only_prompt_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    payload = make_request(input={"prompt": "   \n  "})
    body, headers = signed_request(payload)

    response = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AI_EXECUTION_FAILED"


def test_top_level_extra_fields_are_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    payload = make_request(url="https://provider.invalid")
    body, headers = signed_request(payload)

    response = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AI_EXECUTION_FAILED"
    assert "provider.invalid" not in response.text


def test_invalid_signature_returns_403(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")
    client = TestClient(create_app(database_client=_FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request())
    headers["X-ClipCraft-Signature"] = "0" * 64

    response = client.post("/internal/ai/image/execute", content=body, headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INTERNAL_SIGNATURE_INVALID"


class _FakeDatabase:
    def __init__(self, credential=None):
        self.credential = credential

    def get_credential_for_test(self, provider_id):
        return self.credential


def _text_request():
    return {
        "job_id": str(uuid4()),
        "provider_id": "gemini",
        "model_id": "gemini-2.5-flash",
        "credential_source": "environment",
        "operation": "text_generation",
        "input": {
            "prompt": "Write one sentence.",
            "temperature": 0.2,
            "max_output_tokens": 128,
            "response_format": "text",
        },
        "routing_version": "1",
        "request_id": str(uuid4()),
    }
