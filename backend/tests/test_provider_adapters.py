import pytest

from app.services.ai.adapters import (
    AdapterRegistry,
    AdapterValidationError,
    Capability,
    ProviderAdapter,
    default_adapter_registry,
)
from app.services.ai.credential_resolution import ExecutionContext, ResolvedProviderCredential
from app.services.ai.routing import RoutingDecision
from pydantic import SecretStr


def context(provider="cloudflare", visual_source="ai"):
    decision = RoutingDecision(
        text_provider=provider,
        text_model="@cf/meta/llama-3.1-8b-instruct",
        visual_source=visual_source,
        image_provider="cloudflare" if visual_source == "ai" else None,
        image_model="@cf/black-forest-labs/flux-1-schnell" if visual_source == "ai" else None,
        credential_strategy="environment",
        routing_version=1,
    )
    credential = ResolvedProviderCredential(provider, "environment", SecretStr("not-used-by-adapter"))
    return ExecutionContext(decision, (credential,), job_id="job-1")


def test_default_registry_contains_all_initial_adapters():
    registry = default_adapter_registry()

    assert registry.provider_ids() == {"gemini", "cloudflare", "pexels", "nvidia"}
    assert registry.get("gemini").supports("text_generation")
    assert registry.get("cloudflare").supports("image_generation")
    assert registry.get("pexels").supports("stock_media")
    assert registry.get("nvidia").supports("connection_test")
    assert registry.get("nvidia").supports("text_generation")
    assert not registry.get("nvidia").supports("image_generation")


def test_registry_lookup_and_duplicate_registration_are_safe():
    registry = AdapterRegistry()
    adapter = ProviderAdapter("anthropic", {"text_generation"})
    registry.register(adapter)

    assert registry.get("anthropic") is adapter
    with pytest.raises(AdapterValidationError) as missing:
        registry.get("missing")
    assert missing.value.code == "adapter_not_found"
    with pytest.raises(AdapterValidationError) as duplicate:
        registry.register(ProviderAdapter("anthropic", {"text_generation"}))
    assert duplicate.value.code == "adapter_already_registered"


@pytest.mark.parametrize(
    ("provider_id", "capability", "request_data", "code"),
    [
        ("gemini", "image_generation", {"prompt": "image"}, "unsupported_capability"),
        ("nvidia", "image_generation", {"prompt": "image"}, "unsupported_capability"),
        ("cloudflare", "text_generation", {}, "prompt_required"),
        ("pexels", "stock_media", {}, "query_required"),
    ],
)
def test_adapters_reject_unsupported_operations_safely(provider_id, capability, request_data, code):
    adapter = default_adapter_registry().get(provider_id)

    with pytest.raises(AdapterValidationError) as error:
        adapter.prepare_request(capability, request_data)

    assert error.value.code == code
    assert "not-used-by-adapter" not in str(error.value)


def test_provider_specific_request_preparation_is_pure_metadata():
    registry = default_adapter_registry()

    text = registry.get("cloudflare").prepare_request("text_generation", {"prompt": "hello", "temperature": 0.2})
    image = registry.get("cloudflare").prepare_request("image_generation", {"prompt": "sunset"})
    stock = registry.get("pexels").prepare_request("stock_media", {"query": "sunset", "orientation": "portrait"})

    assert text.payload == {"prompt": "hello", "temperature": 0.2}
    assert image.payload == {"prompt": "sunset"}
    assert stock.payload == {"query": "sunset", "orientation": "portrait"}
    assert text.provider_id == image.provider_id == "cloudflare"
    assert stock.capability == "stock_media"


@pytest.mark.parametrize(
    "request_data",
    [
        {"headers": {"Authorization": "Bearer secret"}},
        {"metadata": {"apiKey": "secret"}},
        {"access_token": "secret"},
        {"private-key": "secret"},
    ],
)
def test_adapters_reject_nested_and_aliased_sensitive_fields(request_data):
    with pytest.raises(AdapterValidationError) as error:
        default_adapter_registry().get("cloudflare").prepare_request("text_generation", {"prompt": "hello", **request_data})

    assert error.value.code == "sensitive_field_forbidden"


def test_adapters_reject_non_string_request_keys_and_freeze_nested_payloads():
    adapter = ProviderAdapter("generic", {"text_generation", "stock_media"})

    with pytest.raises(AdapterValidationError) as error:
        adapter.prepare_request("text_generation", {1: "not-a-field"})
    assert error.value.code == "invalid_request"

    prepared = adapter.prepare_request("text_generation", {"prompt": "hello", "options": {"temperature": 0.2}, "items": ["a"]})
    with pytest.raises(TypeError):
        prepared.payload["options"]["temperature"] = 0.9
    with pytest.raises((TypeError, AttributeError)):
        prepared.payload["items"].append("b")


def test_execution_context_preparation_does_not_expose_secret():
    adapter = default_adapter_registry().get("cloudflare")

    prepared = adapter.prepare_execution_context(context())

    assert prepared.provider_id == "cloudflare"
    assert prepared.job_id == "job-1"
    assert prepared.credential_strategy == "environment"
    assert "not-used-by-adapter" not in repr(prepared)


def test_context_for_wrong_provider_is_rejected():
    adapter = default_adapter_registry().get("gemini")

    with pytest.raises(AdapterValidationError) as error:
        adapter.prepare_execution_context(context(provider="cloudflare"))

    assert error.value.code == "provider_mismatch"


def test_custom_adapter_can_be_registered_without_registry_code_changes():
    class AnthropicAdapter(ProviderAdapter):
        pass

    registry = AdapterRegistry()
    registry.register(AnthropicAdapter("anthropic", {"text_generation"}))

    prepared = registry.get("anthropic").prepare_request("text_generation", {"prompt": "hello"})

    assert prepared.provider_id == "anthropic"
    assert prepared.capability == "text_generation"


def test_health_is_local_and_does_not_claim_provider_execution():
    health = default_adapter_registry().get("gemini").health()

    assert health.status == "registered"
    assert health.checked_remotely is False
