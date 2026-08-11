import pytest

from app.config import Settings
from app.services.ai.routing import (
    DryRunProviderRouter,
    RoutingConfiguration,
    RoutingValidationError,
)


def router(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return DryRunProviderRouter(Settings.from_env())


def valid_configuration(**overrides):
    values = {
        "text_provider": "cloudflare",
        "text_model": "@cf/meta/llama-3.1-8b-instruct",
        "visual_source": "ai",
        "image_provider": "cloudflare",
        "image_model": "@cf/black-forest-labs/flux-1-schnell",
        "credential_source": "environment",
        "provider_configuration_version": "1",
    }
    return RoutingConfiguration(**{**values, **overrides})


def test_dry_run_router_returns_environment_decision_without_execution(monkeypatch):
    decision = router(monkeypatch).resolve(valid_configuration())

    assert decision.text_provider == "cloudflare"
    assert decision.text_model == "@cf/meta/llama-3.1-8b-instruct"
    assert decision.image_provider == "cloudflare"
    assert decision.image_model == "@cf/black-forest-labs/flux-1-schnell"
    assert decision.visual_source == "ai"
    assert decision.credential_strategy == "environment"
    assert decision.routing_version == 1


def test_router_rejects_unimplemented_pexels_visual_source(monkeypatch):
    with pytest.raises(RoutingValidationError) as error:
        router(monkeypatch).resolve(valid_configuration(visual_source="pexels", image_provider=None, image_model=None))

    assert error.value.code == "provider_unimplemented"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"text_provider": "missing"}, "unknown_provider"),
        ({"text_model": "@cf/black-forest-labs/flux-1-schnell"}, "provider_model_mismatch"),
        ({"text_provider": "gemini", "text_model": "gemini-2.5-flash"}, "unavailable_provider"),
        ({"visual_source": "unsupported"}, "unsupported_visual_source"),
        ({"credential_source": "stored"}, "unsupported_credential_source"),
        ({"provider_configuration_version": "2"}, "unsupported_provider_configuration_version"),
    ],
)
def test_router_returns_structured_validation_errors(monkeypatch, overrides, code):
    with pytest.raises(RoutingValidationError) as error:
        router(monkeypatch).resolve(valid_configuration(**overrides))

    assert error.value.code == code
    assert error.value.message
