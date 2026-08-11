import asyncio

import pytest
from pydantic import SecretStr

from app.services.ai.adapters import default_adapter_registry
from app.services.ai.credential_resolution import ExecutionContext, ResolvedProviderCredential
from app.services.ai.cloudflare_execution import CloudflareResponse, HttpxCloudflareTransport, register_cloudflare_executions
from app.services.ai.provider_executor import ProviderExecutionError, ProviderExecutionRegistry, ProviderExecutor
from app.services.ai.routing import RoutingDecision


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def run(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def context(*, text_model="@cf/meta/llama-3.1-8b-instruct", image_model="@cf/black-forest-labs/flux-1-schnell", strategy="environment", capability="text_generation"):
    decision = RoutingDecision(
        text_provider="cloudflare",
        text_model=text_model,
        visual_source="ai",
        image_provider="cloudflare",
        image_model=image_model,
        credential_strategy=strategy,
        routing_version=1,
    )
    credential = ResolvedProviderCredential("cloudflare", strategy, SecretStr("cf-secret"), account_id="test-account")
    return ExecutionContext(decision, (credential,), job_id="job-1")


def prepared_request(*, capability="text_generation", model="@cf/meta/llama-3.1-8b-instruct", strategy="environment", parameters=None):
    ctx = context(text_model=model, image_model=model, strategy=strategy)
    return ProviderExecutor().prepare(
        adapter=default_adapter_registry().get("cloudflare"),
        context=ctx,
        capability=capability,
        model_id=model,
        parameters=parameters or {"prompt": "Write one sentence."},
        request_id="request-1",
    )


def executor_for(response, capability="text_generation"):
    transport = FakeTransport(response)
    registry = ProviderExecutionRegistry()
    register_cloudflare_executions(registry, transport=transport)
    return ProviderExecutor(registry), transport


class TestCloudflareTextExecution:
    def test_returns_normalized_text_with_finish_reason(self):
        executor, transport = executor_for(CloudflareResponse(200, {"success": True, "result": {"response": "Hello world"}}))

        result = asyncio.run(executor.execute(prepared_request(parameters={"prompt": "hello", "temperature": 0.4, "max_tokens": 12})))

        assert result.state == "completed"
        assert result.output.text == "Hello world"
        assert result.output.capability == "text_generation"
        assert transport.calls[0]["model"] == "@cf/meta/llama-3.1-8b-instruct"
        assert transport.calls[0]["account_id"] == "test-account"
        assert transport.calls[0]["api_key"] == "cf-secret"
        assert transport.calls[0]["body"] == {
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 12,
            "temperature": 0.4,
        }
        assert "cf-secret" not in repr(result)

    def test_uses_system_instruction(self):
        executor, transport = executor_for(CloudflareResponse(200, {"success": True, "result": {"response": "Concise answer"}}))

        result = asyncio.run(executor.execute(prepared_request(parameters={"prompt": "hello", "system_prompt": "Be concise."})))

        assert result.output.text == "Concise answer"
        assert transport.calls[0]["body"]["messages"] == [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "hello"},
        ]

    def test_preserves_opaque_model_id(self):
        executor, transport = executor_for(CloudflareResponse(200, {"success": True, "result": {"response": "ok"}}))
        model = "@cf/meta/llama-3.1-8b-instruct-fp16"

        result = asyncio.run(executor.execute(prepared_request(model=model, parameters={"prompt": "hello"})))

        assert result.output.model_id == model
        assert transport.calls[0]["model"] == model

    @pytest.mark.parametrize(
        ("status", "code"),
        [(400, "invalid_request"), (401, "invalid_credentials"), (403, "permission_denied"), (429, "rate_limited"), (500, "unavailable")],
    )
    def test_http_errors_are_normalized_without_provider_body(self, status, code):
        executor, _ = executor_for(CloudflareResponse(status, {"success": False, "errors": [{"message": "secret body"}]}))

        result = asyncio.run(executor.execute(prepared_request()))

        assert result.state == "failed"
        assert result.error.code == code
        assert "secret body" not in repr(result)
        assert "cf-secret" not in repr(result)

    def test_cloudflare_error_response_normalizes(self):
        executor, _ = executor_for(CloudflareResponse(200, {"success": False, "errors": [{"message": "rate limit"}]}))

        result = asyncio.run(executor.execute(prepared_request()))

        assert result.state == "failed"
        assert result.error.code == "provider_error"

    def test_transport_timeout_is_safe(self):
        class BrokenTransport:
            async def run(self, **kwargs):
                raise TimeoutError("cf-secret and body")

        registry = ProviderExecutionRegistry()
        register_cloudflare_executions(registry, transport=BrokenTransport())
        executor = ProviderExecutor(registry)

        result = asyncio.run(executor.execute(prepared_request()))

        assert result.state == "failed"
        assert result.error.code == "timeout"
        assert "cf-secret" not in repr(result)

    def test_transport_unavailable_is_safe(self):
        class OfflineTransport:
            async def run(self, **kwargs):
                raise ConnectionError("provider down")

        registry = ProviderExecutionRegistry()
        register_cloudflare_executions(registry, transport=OfflineTransport())
        executor = ProviderExecutor(registry)

        result = asyncio.run(executor.execute(prepared_request()))

        assert result.state == "failed"
        assert result.error.code == "unavailable"

    def test_missing_account_id_at_runtime_is_detected(self):
        decision = RoutingDecision(
            text_provider="cloudflare",
            text_model="@cf/meta/llama-3.1-8b-instruct",
            visual_source="ai",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            credential_strategy="environment",
            routing_version=1,
        )
        ctx = ExecutionContext(decision, (ResolvedProviderCredential("cloudflare", "environment", SecretStr("x")),), job_id="job-1")
        prepared = ProviderExecutor().prepare(
            adapter=default_adapter_registry().get("cloudflare"),
            context=ctx,
            capability="text_generation",
            model_id="@cf/meta/llama-3.1-8b-instruct",
            parameters={"prompt": "hello"},
            request_id="request-1",
        )

        executor, _ = executor_for(CloudflareResponse(200, {"success": True, "result": {"response": "ok"}}))
        result = asyncio.run(executor.execute(prepared))

        assert result.state == "failed"
        assert result.error.code == "credential_resolution_error"

    def test_environment_strategy_passes_api_key_and_account_id(self):
        executor, transport = executor_for(CloudflareResponse(200, {"success": True, "result": {"response": "env text"}}))

        result = asyncio.run(executor.execute(prepared_request(strategy="environment")))

        assert result.state == "completed"
        assert transport.calls[0]["api_key"] == "cf-secret"
        assert transport.calls[0]["account_id"] == "test-account"

    def test_empty_response_is_detected(self):
        executor, _ = executor_for(CloudflareResponse(200, {"success": True, "result": {"response": ""}}))

        result = asyncio.run(executor.execute(prepared_request()))

        assert result.state == "failed"
        assert result.error.code == "empty_response"

    def test_outcome_uses_choices_content_when_legacy_response_field_is_non_string(self):
        # Cloudflare sometimes returns the text under choices[].message.content with the
        # legacy `result.response` field being null/non-string. The executor must still
        # extract that text instead of failing with empty_response.
        body = {
            "success": True,
            "result": {
                "response": None,
                "choices": [{"message": {"content": "  Electric vehicles rule the road.  "}}],
            },
        }
        executor, _ = executor_for(CloudflareResponse(200, body))

        result = asyncio.run(executor.execute(prepared_request()))

        assert result.state == "completed"
        assert result.output.text == "Electric vehicles rule the road."

    def test_missing_result_is_detected(self):
        executor, _ = executor_for(CloudflareResponse(200, {"success": True}))

        result = asyncio.run(executor.execute(prepared_request()))

        assert result.state == "failed"
        assert result.error.code == "malformed_response"

    def test_missing_credential_is_detected(self):
        decision = RoutingDecision(
            text_provider="cloudflare",
            text_model="@cf/meta/llama-3.1-8b-instruct",
            visual_source="ai",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            credential_strategy="environment",
            routing_version=1,
        )
        context = ExecutionContext(decision, (), job_id="job-1")
        with pytest.raises(ProviderExecutionError) as error:
            ProviderExecutor().prepare(
                adapter=default_adapter_registry().get("cloudflare"),
                context=context,
                capability="text_generation",
                model_id="@cf/meta/llama-3.1-8b-instruct",
                parameters={"prompt": "hello"},
                request_id="request-1",
            )

        assert error.value.code == "credential_resolution_error"


class TestCloudflareImageExecution:
    def test_returns_base64_image_output(self):
        executor, transport = executor_for(CloudflareResponse(200, {"success": True, "result": {"image": "base64imagedata"}}), capability="image_generation")

        result = asyncio.run(executor.execute(prepared_request(capability="image_generation", model="@cf/black-forest-labs/flux-1-schnell", parameters={"prompt": "sunset"})))

        assert result.state == "completed"
        assert result.output.text == "base64imagedata"
        assert result.output.capability == "image_generation"
        assert transport.calls[0]["body"] == {"prompt": "sunset"}
        assert "cf-secret" not in repr(result)

    def test_empty_image_is_rejected(self):
        executor, _ = executor_for(CloudflareResponse(200, {"success": True, "result": {"image": ""}}), capability="image_generation")

        result = asyncio.run(executor.execute(prepared_request(capability="image_generation", model="@cf/black-forest-labs/flux-1-schnell", parameters={"prompt": "sunset"})))

        assert result.state == "failed"
        assert result.error.code == "empty_response"

    def test_missing_image_field_is_detected(self):
        executor, _ = executor_for(CloudflareResponse(200, {"success": True, "result": {}}), capability="image_generation")

        result = asyncio.run(executor.execute(prepared_request(capability="image_generation", model="@cf/black-forest-labs/flux-1-schnell", parameters={"prompt": "sunset"})))

        assert result.state == "failed"
        assert result.error.code == "empty_response"

    def test_only_accepts_prompt_parameter(self):
        with pytest.raises(ProviderExecutionError) as error:
            prepared_request(capability="image_generation", model="@cf/black-forest-labs/flux-1-schnell", parameters={"prompt": "sunset", "temperature": 0.5})

        assert error.value.code == "configuration_error"

    def test_image_capability_rejects_text_only_model(self):
        decision = RoutingDecision(
            text_provider="cloudflare",
            text_model="@cf/meta/llama-3.1-8b-instruct",
            visual_source="ai",
            image_provider="cloudflare",
            image_model="@cf/black-forest-labs/flux-1-schnell",
            credential_strategy="environment",
            routing_version=1,
        )
        with pytest.raises(ProviderExecutionError) as error:
            ProviderExecutor().prepare(
                adapter=default_adapter_registry().get("cloudflare"),
                context=ExecutionContext(decision, (ResolvedProviderCredential("cloudflare", "environment", SecretStr("x"), account_id="a"),)),
                capability="image_generation",
                model_id="@cf/meta/llama-3.1-8b-instruct",
                parameters={"prompt": "sunset"},
                request_id="request-1",
            )

        assert error.value.code == "invalid_execution_context"

    def test_http_errors_are_normalized_for_image(self):
        executor, _ = executor_for(CloudflareResponse(401, {"success": False}), capability="image_generation")

        result = asyncio.run(executor.execute(prepared_request(capability="image_generation", model="@cf/black-forest-labs/flux-1-schnell", parameters={"prompt": "sunset"})))

        assert result.state == "failed"
        assert result.error.code == "invalid_credentials"


class TestCloudflareHttpTransport:
    def test_uses_bearer_auth_and_account_id_in_url(self, monkeypatch):
        captured = {}

        class Response:
            content = b'{"success":true,"result":{"response":"ok"}}'
            status_code = 200
            headers = {}

            def json(self):
                return {"success": True, "result": {"response": "ok"}}

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
        asyncio.run(HttpxCloudflareTransport().run(model="@cf/meta/llama-3.1-8b-instruct", account_id="my-account", api_key="my-token", body={"x": 1}, timeout_seconds=5))

        assert "my-account" in captured["url"]
        assert "@cf/meta/llama-3.1-8b-instruct" in captured["url"]
        assert captured["url"].startswith("https://api.cloudflare.com/client/v4/accounts/my-account/ai/run/")
        assert captured["kwargs"]["headers"] == {"Authorization": "Bearer my-token", "Content-Type": "application/json"}
        assert "my-token" not in captured["url"]
        assert captured["client"] == {"timeout": 5, "follow_redirects": False}


class TestCloudflareRegistration:
    def test_registers_text_and_image_capabilities(self):
        registry = ProviderExecutionRegistry()
        register_cloudflare_executions(registry)

        # Should not raise
        handler = registry.get("cloudflare", "text_generation")
        assert handler is not None

        handler = registry.get("cloudflare", "image_generation")
        assert handler is not None

    def test_duplicate_registration_raises(self):
        registry = ProviderExecutionRegistry()
        register_cloudflare_executions(registry)

        with pytest.raises(ProviderExecutionError) as error:
            register_cloudflare_executions(registry)
        assert error.value.code == "configuration_error"
