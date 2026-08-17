import hashlib
import hmac
import json
import base64
import os
import time
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.ai.gemini_execution import GeminiResponse
from app.services.credential_crypto import CredentialEncryption


SECRET = "internal-signing-secret"


class FakeDatabase:
    def __init__(self, credential=None):
        self.credential = credential

    def get_credential_for_test(self, provider_id):
        return self.credential


def make_request(**overrides):
    request = {
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


def test_internal_route_is_hidden_and_rejects_missing_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))

    response = client.post("/internal/ai/text/execute", content=b"{}")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INTERNAL_AUTH_REQUIRED"
    assert "/internal/ai/text/execute" not in client.get("/openapi.json").text


def test_internal_route_rejects_oversized_body_before_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))

    response = client.post("/internal/ai/text/execute", content=b"x" * (1024 * 1024 + 1))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "AI_EXECUTION_FAILED"


def test_valid_gemini_request_returns_normalized_result(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    async def fake_generate(self, **kwargs):
        return GeminiResponse(200, {
            "candidates": [{"content": {"parts": [{"text": "Generated text"}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 4},
        })

    monkeypatch.setattr("app.services.ai.gemini_execution.HttpxGeminiTransport.generate", fake_generate)
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))
    payload = make_request()
    body, headers = signed_request(payload)

    response = client.post("/internal/ai/text/execute", content=body, headers=headers)

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["text"] == "Generated text"
    assert result["provider_id"] == "gemini"
    assert result["model_id"] == "gemini-2.5-flash"
    assert result["finish_reason"] == "STOP"
    assert result["usage"] == {"promptTokenCount": 3, "candidatesTokenCount": 4}
    assert "test-gemini-key" not in response.text
    assert "Generated text" in response.text
    assert "prompt" not in result


def test_cloudflare_request_preserves_opaque_model_and_uses_stored_strategy(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")

    async def fake_run(self, **kwargs):
        return type("Response", (), {"status_code": 200, "body": {"success": True, "result": {"response": "Cloudflare text"}}, "headers": {}})()

    monkeypatch.setattr("app.services.ai.cloudflare_execution.HttpxCloudflareTransport.run", fake_run)
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))
    payload = make_request(
        provider_id="cloudflare",
        model_id="@cf/meta/llama-3.1-8b-instruct:variant",
        credential_source="stored",
    )
    payload["model_id"] = "@cf/meta/llama-3.1-8b-instruct"
    body, headers = signed_request(payload)

    response = client.post("/internal/ai/text/execute", content=body, headers=headers)

    assert response.status_code in {401, 422, 503}
    assert "test-cf-token" not in response.text


def test_cloudflare_environment_request_returns_normalized_result(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("CLOUDFLARE_AI_TOKEN", "test-cf-token")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-cf-account")

    async def fake_run(self, **kwargs):
        return type("Response", (), {"status_code": 200, "body": {"success": True, "result": {"response": "Cloudflare text"}}, "headers": {}})()

    monkeypatch.setattr("app.services.ai.cloudflare_execution.HttpxCloudflareTransport.run", fake_run)
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))
    payload = make_request(
        provider_id="cloudflare",
        model_id="@cf/meta/llama-3.1-8b-instruct",
    )
    body, headers = signed_request(payload)

    response = client.post("/internal/ai/text/execute", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["text"] == "Cloudflare text"
    assert "test-cf-token" not in response.text


def test_stored_gemini_credential_is_used_without_environment_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY", key)
    encryption = CredentialEncryption.from_environment()
    database = FakeDatabase({
        "encrypted_secret": encryption.encrypt("stored-gemini-key", "gemini"),
        "encrypted_metadata": None,
        "enabled": True,
        "status": "configured",
    })

    async def fake_generate(self, **kwargs):
        assert kwargs["api_key"] == "stored-gemini-key"
        return GeminiResponse(200, {"candidates": [{"content": {"parts": [{"text": "stored result"}]}}]})

    monkeypatch.setattr("app.services.ai.gemini_execution.HttpxGeminiTransport.generate", fake_generate)
    client = TestClient(create_app(database_client=database, data_dir=tmp_path))
    payload = make_request(credential_source="stored")
    body, headers = signed_request(payload)

    response = client.post("/internal/ai/text/execute", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["text"] == "stored result"
    assert "stored-gemini-key" not in response.text


def test_stored_nvidia_request_uses_generic_internal_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("AI_CREDENTIAL_ENCRYPTION_KEY", key)
    encryption = CredentialEncryption.from_environment()
    database = FakeDatabase({
        "provider_id": "nvidia",
        "encrypted_secret": encryption.encrypt("stored-nvidia-key", "nvidia"),
        "encrypted_metadata": None,
        "enabled": True,
        "status": "configured",
    })

    async def fake_complete(self, **kwargs):
        assert kwargs["api_key"] == "stored-nvidia-key"
        assert kwargs["model"] == "nvidia/llama-3.3-nemotron-super-49b-v1"
        from app.services.ai.nvidia_execution import NVIDIAResponse
        return NVIDIAResponse(200, {
            "id": "nvidia-request",
            "model": "nvidia/llama-3.3-nemotron-super-49b-v1",
            "choices": [{"message": {"content": "NVIDIA text"}, "finish_reason": "stop"}],
            "usage": {"total_tokens": 9},
        })

    monkeypatch.setattr("app.services.ai.nvidia_execution.HttpxNVIDIATransport.complete", fake_complete)
    client = TestClient(create_app(database_client=database, data_dir=tmp_path))
    payload = make_request(
        provider_id="nvidia",
        model_id="nvidia/llama-3.3-nemotron-super-49b-v1",
        credential_source="stored",
    )
    body, headers = signed_request(payload)

    response = client.post("/internal/ai/text/execute", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["text"] == "NVIDIA text"
    assert response.json()["provider_id"] == "nvidia"
    assert response.json()["model_id"] == "nvidia/llama-3.3-nemotron-super-49b-v1"
    assert "stored-nvidia-key" not in response.text


def test_stored_credential_does_not_fallback_to_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", "environment-key")
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request(credential_source="stored"))

    response = client.post("/internal/ai/text/execute", content=body, headers=headers)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AI_CREDENTIAL_MISSING"
    assert "environment-key" not in response.text


def test_unknown_provider_and_model_are_safe(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))

    for changes, expected in [
        ({"provider_id": "unknown"}, "AI_PROVIDER_UNKNOWN"),
        ({"model_id": "unknown"}, "AI_MODEL_UNKNOWN"),
    ]:
        payload = make_request(**changes)
        body, headers = signed_request(payload)
        response = client.post("/internal/ai/text/execute", content=body, headers=headers)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == expected


def test_duplicate_request_nonce_is_rejected_before_execution(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    async def fake_generate(self, **kwargs):
        return GeminiResponse(200, {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})

    monkeypatch.setattr("app.services.ai.gemini_execution.HttpxGeminiTransport.generate", fake_generate)
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request(), nonce="same-nonce")

    first = client.post("/internal/ai/text/execute", content=body, headers=headers)
    second = client.post("/internal/ai/text/execute", content=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 401
    assert second.json()["error"]["code"] == "INTERNAL_REQUEST_REPLAYED"


def test_arbitrary_headers_and_urls_are_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))
    payload = make_request(headers={"Authorization": "Bearer secret"}, url="https://provider.invalid")
    body, headers = signed_request(payload)

    response = client.post("/internal/ai/text/execute", content=body, headers=headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AI_EXECUTION_FAILED"
    assert "secret" not in response.text


def test_provider_output_and_raw_errors_are_normalized(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    async def fake_generate(self, **kwargs):
        return GeminiResponse(401, {"error": {"message": "provider secret body"}})

    monkeypatch.setattr("app.services.ai.gemini_execution.HttpxGeminiTransport.generate", fake_generate)
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request())

    response = client.post("/internal/ai/text/execute", content=body, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AI_CREDENTIAL_INVALID"
    assert "provider secret body" not in response.text
    assert "test-gemini-key" not in response.text


def test_quota_error_has_stable_code(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    async def fake_generate(self, **kwargs):
        return GeminiResponse(402, {"error": {"message": "quota body"}})

    monkeypatch.setattr("app.services.ai.gemini_execution.HttpxGeminiTransport.generate", fake_generate)
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request())

    response = client.post("/internal/ai/text/execute", content=body, headers=headers)

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "AI_QUOTA_EXCEEDED"
    assert "quota body" not in response.text


def test_permission_denied_has_stable_non_retryable_code(monkeypatch, tmp_path):
    monkeypatch.setenv("N8N_INTERNAL_SIGNING_SECRET", SECRET)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    async def fake_generate(self, **kwargs):
        return GeminiResponse(403, {"error": {"message": "permission body"}})

    monkeypatch.setattr("app.services.ai.gemini_execution.HttpxGeminiTransport.generate", fake_generate)
    client = TestClient(create_app(database_client=FakeDatabase(), data_dir=tmp_path))
    body, headers = signed_request(make_request())

    response = client.post("/internal/ai/text/execute", content=body, headers=headers)

    assert response.status_code == 403
    assert response.json()["error"] == {
        "code": "AI_PERMISSION_DENIED",
        "message": "provider execution failed",
        "retryable": False,
    }
    assert "permission body" not in response.text
