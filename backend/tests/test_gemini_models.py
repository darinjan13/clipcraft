from app.services.ai.gemini_execution import text_fallback_models
from app.services.ai.provider_registry import (
    DEFAULT_TEXT_MODEL,
    resolve_provider_selection,
)


def test_default_text_model_is_flash_lite():
    assert DEFAULT_TEXT_MODEL == "gemini-3.5-flash-lite"
    assert resolve_provider_selection()["text_model"] == "gemini-3.5-flash-lite"


def test_all_flash_models_are_registered_text():
    chain = text_fallback_models("gemini-3.5-flash-lite")
    for model_id in (
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.7-flash",
        "gemini-3.8-flash",
        "gemini-3.5-flash",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
    ):
        assert model_id in chain


def test_fallback_chain_prefers_requested_model_first():
    chain = text_fallback_models("gemini-3.6-flash")
    assert chain[0] == "gemini-3.6-flash"
    assert len(chain) == len(set(chain))
