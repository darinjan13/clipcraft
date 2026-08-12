import asyncio

import pytest
from pydantic import SecretStr


MODEL_ID = "nvidia/llama-3.3-nemotron-super-49b-v1"


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def prepared_request(parameters=None):
    from app.services.ai.adapters import default_adapter_registry
    from app.services.ai.credential_resolution import ExecutionContext, ResolvedProviderCredential
    from app.services.ai.provider_executor import ProviderExecutor
    from app.services.ai.routing import RoutingDecision

    decision = RoutingDecision(
        text_provider="nvidia",
        text_model=MODEL_ID,
        visual_source="ai",
        image_provider="cloudflare",
        image_model="@cf/black-forest-labs/flux-1-schnell",
        credential_strategy="stored",
        routing_version=1,
    )
    context = ExecutionContext(
        decision,
        (ResolvedProviderCredential("nvidia", "stored", SecretStr("nvidia-secret")),),
        job_id="job-1",
    )
    return ProviderExecutor().prepare(
        adapter=default_adapter_registry().get("nvidia"),
        context=context,
        capability="text_generation",
        model_id=MODEL_ID,
        parameters=parameters or {"prompt": "Write one sentence."},
        request_id="request-1",
    )


def executor_for(response):
    from app.services.ai.nvidia_execution import register_nvidia_execution
    from app.services.ai.provider_executor import ProviderExecutionRegistry, ProviderExecutor

    transport = FakeTransport(response)
    registry = ProviderExecutionRegistry()
    register_nvidia_execution(registry, transport=transport)
    return ProviderExecutor(registry), transport


def test_nvidia_execution_returns_normalized_openai_compatible_text():
    from app.services.ai.nvidia_execution import NVIDIAResponse

    executor, transport = executor_for(NVIDIAResponse(200, {
        "id": "request-from-provider",
        "model": MODEL_ID,
        "choices": [{"message": {"content": "Hello world"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
    }))

    result = asyncio.run(executor.execute(prepared_request({
        "prompt": "hello",
        "system_prompt": "Be concise.",
        "temperature": 0.4,
        "max_tokens": 12,
    })))

    assert result.state == "completed"
    assert result.output.provider_id == "nvidia"
    assert result.output.model_id == MODEL_ID
    assert result.output.text == "Hello world"
    assert result.output.finish_reason == "stop"
    assert result.output.usage == {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}
    assert result.output.provider_request_id == "request-from-provider"
    assert transport.calls == [{
        "model": MODEL_ID,
        "api_key": "nvidia-secret",
        "body": {
            "model": MODEL_ID,
            "messages": [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "hello"},
            ],
            "temperature": 0.4,
            "max_tokens": 12,
            "stream": False,
        },
        "timeout_seconds": 120.0,
    }]
    assert "nvidia-secret" not in repr(result)


@pytest.mark.parametrize(
    ("status", "code"),
    [(400, "invalid_request"), (401, "invalid_credentials"), (403, "permission_denied"), (402, "quota_exceeded"), (429, "rate_limited"), (500, "unavailable")],
)
def test_nvidia_http_errors_are_normalized_without_provider_body(status, code):
    from app.services.ai.nvidia_execution import NVIDIAResponse

    executor, _ = executor_for(NVIDIAResponse(status, {"error": {"message": "secret provider body"}}))

    result = asyncio.run(executor.execute(prepared_request()))

    assert result.state == "failed"
    assert result.error.code == code
    assert "secret provider body" not in repr(result)
    assert "nvidia-secret" not in repr(result)


@pytest.mark.parametrize(
    "body",
    [None, {}, {"choices": []}, {"choices": [{}]}, {"choices": [{"message": {"content": ""}}]}],
)
def test_nvidia_malformed_or_empty_responses_are_not_success(body):
    from app.services.ai.nvidia_execution import NVIDIAResponse

    executor, _ = executor_for(NVIDIAResponse(200, body))

    result = asyncio.run(executor.execute(prepared_request()))

    assert result.state == "failed"
    assert result.error.code in {"malformed_response", "empty_response"}


def test_nvidia_length_finish_reason_is_truncated_not_success():
    from app.services.ai.nvidia_execution import NVIDIAResponse

    executor, _ = executor_for(NVIDIAResponse(200, {
        "choices": [{"message": {"content": "partial JSON"}, "finish_reason": "length"}],
    }))

    result = asyncio.run(executor.execute(prepared_request()))

    assert result.state == "failed"
    assert result.error.code == "truncated_response"


def test_nvidia_transport_uses_fixed_endpoint_bearer_auth_and_no_redirects(monkeypatch):
    from app.services.ai.nvidia_execution import HttpxNVIDIATransport

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
    asyncio.run(HttpxNVIDIATransport().complete(
        model=MODEL_ID,
        api_key="nvidia-secret",
        body={"model": MODEL_ID},
        timeout_seconds=5,
    ))

    assert captured["url"] == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert captured["kwargs"]["headers"] == {"Authorization": "Bearer nvidia-secret", "Content-Type": "application/json"}
    assert captured["kwargs"]["json"] == {"model": MODEL_ID}
    assert captured["client"] == {"timeout": 5, "follow_redirects": False}
    assert "nvidia-secret" not in captured["url"]


def test_nvidia_transport_timeout_is_safe():
    from app.services.ai.nvidia_execution import register_nvidia_execution
    from app.services.ai.provider_executor import ProviderExecutionRegistry, ProviderExecutor

    class BrokenTransport:
        async def complete(self, **kwargs):
            raise TimeoutError("nvidia-secret and raw provider body")

    registry = ProviderExecutionRegistry()
    register_nvidia_execution(registry, transport=BrokenTransport())

    result = asyncio.run(ProviderExecutor(registry).execute(prepared_request()))

    assert result.state == "failed"
    assert result.error.code == "timeout"
    assert "nvidia-secret" not in repr(result)
