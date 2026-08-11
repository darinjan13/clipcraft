import asyncio
import pytest
from pydantic import SecretStr

from app.services.ai.adapters import AdapterValidationError, PreparedExecutionContext, PreparedProviderRequest, default_adapter_registry
from app.services.ai.credential_resolution import ExecutionContext, ResolvedProviderCredential
from app.services.ai.provider_executor import (
    ExecutionLifecycle,
    ProviderExecutionError,
    ProviderExecutor,
)
from app.services.ai.routing import RoutingDecision


def make_context():
    decision = RoutingDecision(
        text_provider="cloudflare",
        text_model="@cf/meta/llama-3.1-8b-instruct",
        visual_source="ai",
        image_provider="cloudflare",
        image_model="@cf/black-forest-labs/flux-1-schnell",
        credential_strategy="environment",
        routing_version=1,
    )
    credential = ResolvedProviderCredential("cloudflare", "environment", SecretStr("executor-secret"))
    return ExecutionContext(decision, (credential,), job_id="job-1")


def test_executor_prepares_normalized_ready_request():
    result = ProviderExecutor().prepare(
        adapter=default_adapter_registry().get("cloudflare"),
        context=make_context(),
        capability="text_generation",
        model_id="@cf/meta/llama-3.1-8b-instruct",
        parameters={"prompt": "hello"},
        request_id="request-1",
    )

    assert result.state == "ready"
    assert result.lifecycle == ("prepared", "validated", "ready")
    assert result.request.provider_id == "cloudflare"
    assert result.request.model_id == "@cf/meta/llama-3.1-8b-instruct"
    assert result.request.capability == "text_generation"
    assert result.request.payload["prompt"] == "hello"
    assert result.metadata.request_id == "request-1"
    assert result.metadata.credential_strategy == "environment"


def test_executor_validates_model_capability_and_context():
    with pytest.raises(ProviderExecutionError) as error:
        ProviderExecutor().prepare(
            adapter=default_adapter_registry().get("cloudflare"),
            context=make_context(),
            capability="text_generation",
            model_id="@cf/black-forest-labs/flux-1-schnell",
            parameters={"prompt": "hello"},
            request_id="request-1",
        )

    assert error.value.code == "invalid_execution_context"


@pytest.mark.parametrize(
    ("adapter_id", "capability", "code"),
    [
        ("gemini", "image_generation", "missing_capability"),
        ("nvidia", "text_generation", "missing_capability"),
    ],
)
def test_executor_rejects_unsupported_provider_capabilities(adapter_id, capability, code):
    with pytest.raises(ProviderExecutionError) as error:
        ProviderExecutor().prepare(
            adapter=default_adapter_registry().get(adapter_id),
            context=make_context(),
            capability=capability,
            model_id=None,
            parameters={"prompt": "hello"},
            request_id="request-1",
        )

    assert error.value.code == code


def test_executor_rejects_missing_adapter():
    with pytest.raises(ProviderExecutionError) as error:
        ProviderExecutor().prepare(
            adapter=None,
            context=make_context(),
            capability="text_generation",
            model_id="model",
            parameters={"prompt": "hello"},
            request_id="request-1",
        )

    assert error.value.code == "adapter_missing"


def test_executor_normalizes_adapter_failures():
    class BrokenAdapter:
        provider_id = "cloudflare"

        def prepare_execution_context(self, context):
            raise AdapterValidationError("credential_missing", "credential is missing")

    with pytest.raises(ProviderExecutionError) as error:
        ProviderExecutor().prepare(
            adapter=BrokenAdapter(),
            context=make_context(),
            capability="text_generation",
            model_id="@cf/meta/llama-3.1-8b-instruct",
            parameters={"prompt": "hello"},
            request_id="request-1",
        )

    assert error.value.code == "credential_resolution_error"
    assert "executor-secret" not in str(error.value)


def test_executor_metadata_redacts_secrets_and_execute_is_reserved():
    result = ProviderExecutor().prepare(
        adapter=default_adapter_registry().get("cloudflare"),
        context=make_context(),
        capability="text_generation",
        model_id="@cf/meta/llama-3.1-8b-instruct",
        parameters={"prompt": "hello"},
        request_id="request-1",
    )
    assert "executor-secret" not in repr(result)

    with pytest.raises(ProviderExecutionError) as error:
        asyncio.run(ProviderExecutor().execute(result))
    assert error.value.code == "execution_not_implemented"


def test_executor_rejects_inconsistent_adapter_context_and_freezes_adapter_payload():
    class InconsistentAdapter:
        provider_id = "cloudflare"

        def supports(self, capability):
            return capability == "text_generation"

        def prepare_execution_context(self, context):
            return PreparedExecutionContext("gemini", "environment", 1, "job-1")

        def prepare_request(self, capability, parameters):
            return PreparedProviderRequest("cloudflare", capability, {"nested": {"value": 1}})

    with pytest.raises(ProviderExecutionError) as error:
        ProviderExecutor().prepare(
            adapter=InconsistentAdapter(),
            context=make_context(),
            capability="text_generation",
            model_id="@cf/meta/llama-3.1-8b-instruct",
            parameters={"prompt": "hello"},
            request_id="request-1",
        )

    assert error.value.code == "configuration_error"

    class MutableAdapter(InconsistentAdapter):
        def prepare_execution_context(self, context):
            return PreparedExecutionContext("cloudflare", "environment", 1, "job-1")

    result = ProviderExecutor().prepare(
        adapter=MutableAdapter(),
        context=make_context(),
        capability="text_generation",
        model_id="@cf/meta/llama-3.1-8b-instruct",
        parameters={"prompt": "hello"},
        request_id="request-1",
    )
    with pytest.raises(TypeError):
        result.request.payload["nested"]["value"] = 2


def test_lifecycle_contains_only_pre_execution_states():
    assert set(ExecutionLifecycle) == {"prepared", "validated", "ready", "executing", "completed", "failed"}
