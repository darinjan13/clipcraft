import json
from pathlib import Path

import pytest

from clipcraft.smoke_safety import SafetyError, validate_config, validate_harness, validate_mock_contracts


ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "clipcraft" / "workflows" / "smoke-test-entry-harness.json"


def config():
    return {
        "CLIPCRAFT_ENV": "test",
        "CLIPCRAFT_SMOKE_TEST_MODE": "true",
        "SUPABASE_URL": "https://smoke-project.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "test-secret",
        "CLIPCRAFT_SUPABASE_PROJECT_REF": "smoke-project",
        "CLIPCRAFT_SUPABASE_HOST_ALLOWLIST": "smoke-project.supabase.co",
        "CLIPCRAFT_STORAGE_MODE": "dedicated_bucket",
        "CLIPCRAFT_STORAGE_BUCKET": "smoke-bucket",
        "CLIPCRAFT_STORAGE_HOST": "storage.smoke.test",
        "CLIPCRAFT_STORAGE_HOST_ALLOWLIST": "storage.smoke.test",
        "CLIPCRAFT_TEXT_PROVIDER_MODE": "mock",
        "CLIPCRAFT_TEXT_PROVIDER_ENDPOINT": "mock://text",
        "CLIPCRAFT_IMAGE_PROVIDER_MODE": "mock",
        "CLIPCRAFT_IMAGE_PROVIDER_ENDPOINT": "mock://image",
        "CLIPCRAFT_TTS_MODE": "mock",
        "CLIPCRAFT_TTS_ENDPOINT": "mock://tts",
        "CLIPCRAFT_RENDERER_MODE": "mock",
        "CLIPCRAFT_RENDERER_ENDPOINT": "mock://renderer",
        "CLIPCRAFT_N8N_INTERNAL_URL": "https://n8n.smoke.test",
        "CLIPCRAFT_N8N_HOST_ALLOWLIST": "n8n.smoke.test",
        "CLIPCRAFT_TEST_NAMESPACE": "smoke-test",
        "CLIPCRAFT_CORRELATION_ID": "123e4567-e89b-42d3-a456-426614174000",
        "CLIPCRAFT_IDEMPOTENCY_KEY": "123e4567-e89b-42d3-a456-426614174001",
        "CLIPCRAFT_CLEANUP_MODE": "strict_namespace",
    }


def contracts():
    return {
        "text": {"success": True, "type": "text", "result": "mock script", "provider": "mock", "model": "mock-text", "retryCount": 0, "timestamp": "2026-01-01T00:00:00Z"},
        "image": {"success": True, "type": "image", "imageBase64": "iVBORw0KGgo=", "format": "png", "provider": "mock", "model": "mock-image", "retryCount": 0, "timestamp": "2026-01-01T00:00:00Z", "context": {"jobId": "job", "sceneId": "scene", "sceneIndex": 1}},
        "tts": {"audio_url": "mock://audio/smoke.wav", "local_path": None},
        "render": {"success": True, "jobId": "job", "videoUrl": "mock://video/final.mp4", "thumbnailUrl": "mock://video/thumb.jpg"},
        "failure": {"jobId": "job", "workerId": "worker", "leaseToken": "lease", "attemptNumber": 1, "pipelineRevision": 1, "stageRunId": "run", "runToken": "token", "error": "mock failure", "failureClass": "runtime", "retryable": False},
    }


def rejects(change):
    value = config()
    change(value)
    with pytest.raises(SafetyError):
        validate_config(value)


def test_all_valid_isolated_configuration_is_accepted():
    result = validate_config(config())
    assert result["targets"]["supabase"]["classification"] == "NON_PRODUCTION"
    assert result["targets"]["textProvider"]["classification"] == "TEST_MOCKED"


@pytest.mark.parametrize("change", [
    lambda c: c.update(SUPABASE_URL="https://production.supabase.co", CLIPCRAFT_SUPABASE_PROJECT_REF="production", CLIPCRAFT_SUPABASE_HOST_ALLOWLIST="production.supabase.co"),
    lambda c: c.update(CLIPCRAFT_STORAGE_BUCKET="production-bucket"),
    lambda c: c.update(CLIPCRAFT_TEXT_PROVIDER_MODE="live", CLIPCRAFT_TEXT_PROVIDER_ENDPOINT="https://api.example.test"),
    lambda c: c.update(SUPABASE_URL="https://unknown.test", CLIPCRAFT_SUPABASE_HOST_ALLOWLIST="known.test"),
    lambda c: c.update(SUPABASE_URL=""),
    lambda c: c.update(CLIPCRAFT_IMAGE_PROVIDER_MODE="live"),
    lambda c: c.update(CLIPCRAFT_SMOKE_TEST_MODE="false"),
    lambda c: c.update(CLIPCRAFT_ENV="production"),
    lambda c: c.update(CLIPCRAFT_TEST_NAMESPACE=""),
    lambda c: c.update(CLIPCRAFT_CORRELATION_ID=""),
    lambda c: c.update(CLIPCRAFT_IDEMPOTENCY_KEY=""),
    lambda c: c.update(CLIPCRAFT_TTS_MODE="unknown"),
    lambda c: c.update(CLIPCRAFT_RENDERER_MODE="live"),
])
def test_unsafe_configuration_is_rejected(change):
    rejects(change)


def test_missing_variable_is_rejected():
    value = config()
    del value["CLIPCRAFT_STORAGE_HOST_ALLOWLIST"]
    with pytest.raises(SafetyError):
        validate_config(value)


def test_mock_contracts_are_schema_identical():
    assert validate_mock_contracts(contracts()) is True


def test_mock_schema_mismatch_is_rejected():
    value = contracts()
    del value["image"]["imageBase64"]
    with pytest.raises(SafetyError):
        validate_mock_contracts(value)


def test_harness_is_inactive_internal_and_excludes_wf03():
    result = validate_harness(HARNESS)
    assert result == {"active": False, "publicWebhook": False, "schedule": False, "wf03Referenced": False, "wf04Referenced": True}


def test_harness_active_state_is_rejected(tmp_path):
    data = json.loads(HARNESS.read_text(encoding="utf-8"))
    data["active"] = True
    path = tmp_path / "harness.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SafetyError):
        validate_harness(path)


def test_harness_wf03_reference_is_rejected(tmp_path):
    data = json.loads(HARNESS.read_text(encoding="utf-8"))
    data["nodes"][1]["parameters"]["workflowId"] = "3"
    path = tmp_path / "harness.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SafetyError):
        validate_harness(path)


def test_harness_has_no_webhook_or_schedule():
    data = json.loads(HARNESS.read_text(encoding="utf-8"))
    assert all(node["type"] not in {"n8n-nodes-base.webhook", "n8n-nodes-base.scheduleTrigger"} for node in data["nodes"])


@pytest.mark.parametrize("node_type", ["n8n-nodes-base.webhook", "n8n-nodes-base.scheduleTrigger"])
def test_harness_public_or_schedule_trigger_is_rejected(tmp_path, node_type):
    data = json.loads(HARNESS.read_text(encoding="utf-8"))
    data["nodes"].append({"type": node_type, "parameters": {}, "name": "Unsafe Entry"})
    path = tmp_path / "harness.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SafetyError):
        validate_harness(path)


def test_mixed_safe_and_unsafe_targets_fail_closed():
    value = config()
    value["CLIPCRAFT_STORAGE_HOST"] = "production-storage.test"
    with pytest.raises(SafetyError):
        validate_config(value)
