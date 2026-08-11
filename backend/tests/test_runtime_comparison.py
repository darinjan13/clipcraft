from app.services.ai.runtime_comparison import (
    ComparisonMetric,
    RuntimeComparisonEngine,
    RuntimeMetadata,
)


def metadata(**overrides):
    values = {
        "provider_id": "gemini",
        "model_id": "gemini-2.5-flash",
        "capability": "text_generation",
        "routing_version": 1,
        "state": "completed",
    }
    values.update(overrides)
    return RuntimeMetadata(**values)


def test_matching_runtime_metadata_returns_match():
    result = RuntimeComparisonEngine(enabled=True).compare(metadata(), metadata())

    assert isinstance(result, ComparisonMetric)
    assert result.outcome == "match"
    assert result.mismatch_category is None


def test_provider_mismatch_is_normalized():
    result = RuntimeComparisonEngine(enabled=True).compare(metadata(), metadata(provider_id="cloudflare"))

    assert result.outcome == "mismatch"
    assert result.mismatch_category == "provider"


def test_model_mismatch_is_normalized():
    result = RuntimeComparisonEngine(enabled=True).compare(metadata(), metadata(model_id="gemini-2.5-pro"))

    assert result.outcome == "mismatch"
    assert result.mismatch_category == "model"


def test_capability_mismatch_is_normalized():
    result = RuntimeComparisonEngine(enabled=True).compare(metadata(), metadata(capability="image_generation"))

    assert result.outcome == "mismatch"
    assert result.mismatch_category == "capability"


def test_state_mismatch_is_normalized():
    result = RuntimeComparisonEngine(enabled=True).compare(metadata(), metadata(state="failed"))

    assert result.outcome == "mismatch"
    assert result.mismatch_category == "state"


def test_routing_version_mismatch_is_normalized():
    result = RuntimeComparisonEngine(enabled=True).compare(metadata(), metadata(routing_version=2))

    assert result.outcome == "mismatch"
    assert result.mismatch_category == "routing_version"


def test_missing_metadata_is_skipped():
    result = RuntimeComparisonEngine(enabled=True).compare(metadata(), None)

    assert result.outcome == "skipped"
    assert result.mismatch_category == "shadow_unavailable"


def test_missing_legacy_metadata_is_skipped():
    result = RuntimeComparisonEngine(enabled=True).compare(None, metadata())

    assert result.outcome == "skipped"
    assert result.mismatch_category == "legacy_unavailable"


def test_invalid_metadata_is_validation_failed():
    result = RuntimeComparisonEngine(enabled=True).compare(metadata(provider_id=""), metadata())

    assert result.outcome == "validation_failed"
    assert result.mismatch_category == "invalid_metadata"


def test_invalid_metadata_types_are_validation_failed():
    result = RuntimeComparisonEngine(enabled=True).compare(
        metadata(provider_id=123, routing_version="one"),
        metadata(),
    )

    assert result.outcome == "validation_failed"
    assert result.mismatch_category == "invalid_metadata"


def test_disabled_comparison_is_skipped_without_comparing():
    result = RuntimeComparisonEngine(enabled=False).compare(
        metadata(provider_id="gemini"),
        metadata(provider_id="cloudflare"),
    )

    assert result.outcome == "skipped"
    assert result.mismatch_category == "comparison_disabled"


def test_safe_metric_excludes_prompts_outputs_and_credentials():
    result = RuntimeComparisonEngine(enabled=True).compare(metadata(), metadata())

    rendered = repr(result)
    assert "prompt" not in rendered
    assert "response" not in rendered
    assert "secret" not in rendered
    assert "token" not in rendered
