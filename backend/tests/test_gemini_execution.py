import asyncio

import pytest
from pydantic import SecretStr

from app.services.ai.adapters import default_adapter_registry
from app.services.ai.credential_resolution import ExecutionContext, ResolvedProviderCredential
from app.services.ai.gemini_execution import GeminiResponse, HttpxGeminiTransport, register_gemini_execution
from app.services.ai.provider_executor import ProviderExecutionError, ProviderExecutionRegistry, ProviderExecutor
from app.services.ai.routing import RoutingDecision


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def prepared_request(*, model="gemini-2.5-flash", strategy="environment", parameters=None):
    decision = RoutingDecision(
        text_provider="gemini",
        text_model=model,
        visual_source="ai",
        image_provider="cloudflare",
        image_model="@cf/black-forest-labs/flux-1-schnell",
        credential_strategy=strategy,
        routing_version=1,
    )
    context = ExecutionContext(
        decision,
        (ResolvedProviderCredential("gemini", strategy, SecretStr("gemini-secret")),),
        job_id="job-1",
    )
    return ProviderExecutor().prepare(
        adapter=default_adapter_registry().get("gemini"),
        context=context,
        capability="text_generation",
        model_id=model,
        parameters=parameters or {"prompt": "Write one sentence."},
        request_id="request-1",
    )


def executor_for(response):
    transport = FakeTransport(response)
    registry = ProviderExecutionRegistry()
    register_gemini_execution(registry, transport=transport)
    return ProviderExecutor(registry), transport


def test_gemini_execution_returns_normalized_text_and_safe_usage_metadata():
    executor, transport = executor_for(GeminiResponse(200, {"candidates": [{"content": {"parts": [{"text": "Hello"}, {"text": " world"}]}, "finishReason": "STOP"}], "usageMetadata": {"totalTokenCount": 7}}))

    result = asyncio.run(executor.execute(prepared_request(parameters={"prompt": "hello", "temperature": 0.4, "max_tokens": 12})))

    assert result.state == "completed"
    assert result.output.text == "Hello world"
    assert result.output.finish_reason == "STOP"
    assert result.output.usage == {"totalTokenCount": 7}
    assert transport.calls[0]["model"] == "gemini-2.5-flash"
    assert transport.calls[0]["api_key"] == "gemini-secret"
    assert transport.calls[0]["body"] == {
        "contents": [{"role": "user", "parts": [{"text": "hello"}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 12},
    }
    assert "gemini-secret" not in repr(result)


def test_gemini_execution_uses_system_instruction_and_preserves_opaque_model_id():
    executor, transport = executor_for(GeminiResponse(200, {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}))
    model = "gemini-2.5-flash:version"

    result = asyncio.run(executor.execute(prepared_request(model=model, parameters={"prompt": "hello", "system_prompt": "Be concise."})))

    assert result.output.text == "ok"
    assert result.output.model_id == model
    assert transport.calls[0]["model"] == model
    assert transport.calls[0]["body"]["systemInstruction"] == {"parts": [{"text": "Be concise."}]}


@pytest.mark.parametrize(
    ("status", "code"),
    [(400, "invalid_request"), (401, "invalid_credentials"), (403, "permission_denied"), (429, "rate_limited"), (500, "unavailable")],
)
def test_gemini_http_errors_are_normalized_without_provider_body(status, code):
    executor, _ = executor_for(GeminiResponse(status, {"error": {"message": "secret provider body"}}))

    result = asyncio.run(executor.execute(prepared_request()))

    assert result.state == "failed"
    assert result.error.code == code
    assert "secret provider body" not in repr(result)
    assert "gemini-secret" not in repr(result)


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"promptFeedback": {"blockReason": "SAFETY"}}, "blocked_response"),
        (None, "malformed_response"),
        ({"candidates": []}, "malformed_response"),
        ({"candidates": [{"content": None}]}, "malformed_response"),
        ({"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png"}}]}}]}, "empty_response"),
        ({"candidates": [{"content": {"parts": [{"text": ""}]}}]}, "empty_response"),
    ],
)
def test_gemini_response_shapes_are_not_reported_as_success(body, code):
    executor, _ = executor_for(GeminiResponse(200, body))

    result = asyncio.run(executor.execute(prepared_request()))

    assert result.state == "failed"
    assert result.error.code == code


def test_gemini_transport_failures_are_safe():
    class BrokenTransport:
        async def generate(self, **kwargs):
            raise TimeoutError("gemini-secret and raw body")

    registry = ProviderExecutionRegistry()
    register_gemini_execution(registry, transport=BrokenTransport())
    executor = ProviderExecutor(registry)

    result = asyncio.run(executor.execute(prepared_request()))

    assert result.state == "failed"
    assert result.error.code == "timeout"
    assert "gemini-secret" not in repr(result)
    assert "raw body" not in repr(result)


def test_http_transport_uses_header_auth_and_encodes_model_without_query_secret(monkeypatch):
    captured = {}

    class Response:
        content = b"{}"
        status_code = 200
        headers = {}

        def json(self):
            return {}

    class Client:
        def __init__(self, **kwargs):
            captured["client"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            captured.update(url=url, kwargs=kwargs)
            return Response()

    monkeypatch.setattr("httpx.AsyncClient", Client)
    asyncio.run(HttpxGeminiTransport().generate(model="gemini/model:version", api_key="secret", body={"x": 1}, timeout_seconds=3))

    assert captured["url"].endswith("/models/gemini%2Fmodel%3Aversion:generateContent")
    assert "secret" not in captured["url"]
    assert captured["kwargs"]["headers"] == {"x-goog-api-key": "secret", "Content-Type": "application/json"}
    assert captured["client"] == {"timeout": 3, "follow_redirects": False}


def test_gemini_stored_strategy_is_passed_without_fallback():
    executor, transport = executor_for(GeminiResponse(200, {"candidates": [{"content": {"parts": [{"text": "stored"}]}}]}))

    result = asyncio.run(executor.execute(prepared_request(strategy="stored")))

    assert result.state == "completed"
    assert transport.calls[0]["api_key"] == "gemini-secret"


def test_gemini_image_capability_remains_unsupported():
    with pytest.raises(ProviderExecutionError) as error:
        ProviderExecutor().prepare(
            adapter=default_adapter_registry().get("gemini"),
            context=prepared_request().request.runtime_context,
            capability="image_generation",
            model_id="gemini-2.5-flash:image-preview",
            parameters={"prompt": "image"},
            request_id="request-1",
        )

    assert error.value.code == "missing_capability"
