"""Fail-closed repository safety checks for isolated smoke preparation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit


REQUIRED = {
    "CLIPCRAFT_ENV",
    "CLIPCRAFT_SMOKE_TEST_MODE",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "CLIPCRAFT_SUPABASE_PROJECT_REF",
    "CLIPCRAFT_SUPABASE_HOST_ALLOWLIST",
    "CLIPCRAFT_STORAGE_MODE",
    "CLIPCRAFT_STORAGE_BUCKET",
    "CLIPCRAFT_STORAGE_HOST",
    "CLIPCRAFT_STORAGE_HOST_ALLOWLIST",
    "CLIPCRAFT_TEXT_PROVIDER_MODE",
    "CLIPCRAFT_TEXT_PROVIDER_ENDPOINT",
    "CLIPCRAFT_IMAGE_PROVIDER_MODE",
    "CLIPCRAFT_IMAGE_PROVIDER_ENDPOINT",
    "CLIPCRAFT_TTS_MODE",
    "CLIPCRAFT_TTS_ENDPOINT",
    "CLIPCRAFT_RENDERER_MODE",
    "CLIPCRAFT_RENDERER_ENDPOINT",
    "CLIPCRAFT_N8N_INTERNAL_URL",
    "CLIPCRAFT_N8N_HOST_ALLOWLIST",
    "CLIPCRAFT_TEST_NAMESPACE",
    "CLIPCRAFT_CORRELATION_ID",
    "CLIPCRAFT_IDEMPOTENCY_KEY",
    "CLIPCRAFT_CLEANUP_MODE",
}
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


class SafetyError(ValueError):
    pass


def _required(config, name):
    value = str(config.get(name, "")).strip()
    if not value:
        raise SafetyError(f"missing required value: {name}")
    return value


def _host(value, name):
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise SafetyError(f"ambiguous endpoint: {name}")
    return parsed.hostname.lower()


def _allowlisted(host, allowlist, name):
    allowed = {item.strip().lower() for item in str(allowlist).split(",") if item.strip()}
    if not allowed or host not in allowed:
        raise SafetyError(f"{name} target is not explicitly allowlisted")


def classify_targets(config):
    result = {}
    supabase_host = _host(_required(config, "SUPABASE_URL"), "SUPABASE_URL")
    _allowlisted(supabase_host, _required(config, "CLIPCRAFT_SUPABASE_HOST_ALLOWLIST"), "Supabase")
    project_ref = _required(config, "CLIPCRAFT_SUPABASE_PROJECT_REF")
    if project_ref not in supabase_host or any(marker in supabase_host for marker in ("prod", "production")):
        raise SafetyError("Supabase target is not a verified non-production project")
    result["supabase"] = {"classification": "NON_PRODUCTION", "hostname": supabase_host, "projectReference": project_ref}

    storage_host = _required(config, "CLIPCRAFT_STORAGE_HOST").lower()
    _allowlisted(storage_host, _required(config, "CLIPCRAFT_STORAGE_HOST_ALLOWLIST"), "Storage")
    bucket = _required(config, "CLIPCRAFT_STORAGE_BUCKET")
    if any(marker in f"{storage_host}/{bucket}".lower() for marker in ("prod", "production")):
        raise SafetyError("storage target is production")
    if str(config.get("CLIPCRAFT_STORAGE_MODE")) != "dedicated_bucket":
        raise SafetyError("storage must use a dedicated non-production bucket")
    result["storage"] = {"classification": "NON_PRODUCTION", "hostname": storage_host, "bucket": bucket}

    for boundary in ("TEXT", "IMAGE"):
        mode = _required(config, f"CLIPCRAFT_{boundary}_PROVIDER_MODE")
        endpoint = _required(config, f"CLIPCRAFT_{boundary}_PROVIDER_ENDPOINT")
        if mode != "mock" or not endpoint.startswith("mock://"):
            raise SafetyError(f"{boundary.lower()} provider is not mocked")
        result[f"{boundary.lower()}Provider"] = {"classification": "TEST_MOCKED", "mode": mode, "endpoint": "mock"}
    for boundary in ("TTS", "RENDERER"):
        mode = _required(config, f"CLIPCRAFT_{boundary}_MODE")
        endpoint = _required(config, f"CLIPCRAFT_{boundary}_ENDPOINT")
        if mode != "mock" or not endpoint.startswith("mock://"):
            raise SafetyError(f"{boundary.lower()} target is not mocked")
        result[boundary.lower()] = {"classification": "TEST_MOCKED", "mode": mode, "endpoint": "mock"}

    n8n_host = _host(_required(config, "CLIPCRAFT_N8N_INTERNAL_URL"), "CLIPCRAFT_N8N_INTERNAL_URL")
    _allowlisted(n8n_host, _required(config, "CLIPCRAFT_N8N_HOST_ALLOWLIST"), "internal n8n")
    result["internalN8n"] = {"classification": "NON_PRODUCTION", "hostname": n8n_host}
    return result


def validate_config(config):
    missing = sorted(REQUIRED - set(config))
    if missing:
        raise SafetyError(f"missing required values: {', '.join(missing)}")
    if config.get("CLIPCRAFT_ENV") not in {"staging", "test"}:
        raise SafetyError("CLIPCRAFT_ENV must be staging or test")
    if str(config.get("CLIPCRAFT_SMOKE_TEST_MODE")).lower() != "true":
        raise SafetyError("smoke-test mode must be explicitly enabled")
    if config.get("CLIPCRAFT_CLEANUP_MODE") != "strict_namespace":
        raise SafetyError("cleanup mode must be strict_namespace")
    namespace = _required(config, "CLIPCRAFT_TEST_NAMESPACE")
    if any(marker in namespace.lower() for marker in ("prod", "production")):
        raise SafetyError("test namespace is production-like")
    if not UUID_RE.fullmatch(_required(config, "CLIPCRAFT_CORRELATION_ID")):
        raise SafetyError("correlation ID must be a UUIDv4")
    if not UUID_RE.fullmatch(_required(config, "CLIPCRAFT_IDEMPOTENCY_KEY")):
        raise SafetyError("idempotency key must be a UUIDv4")
    return {"environment": config["CLIPCRAFT_ENV"], "smokeTestMode": True, "targets": classify_targets(config), "namespace": namespace}


def validate_harness(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    node_types = [node.get("type") for node in data.get("nodes", [])]
    refs = [str(node.get("parameters", {}).get("workflowId", "")) for node in data.get("nodes", []) if node.get("type") == "n8n-nodes-base.executeWorkflow"]
    if data.get("active") is not False:
        raise SafetyError("smoke harness must remain inactive")
    if any(node_type in {"n8n-nodes-base.webhook", "n8n-nodes-base.scheduleTrigger"} for node_type in node_types):
        raise SafetyError("smoke harness cannot contain public webhook or schedule")
    if "3" in refs or any("WF03" in json.dumps(data).upper() for _ in [0]):
        raise SafetyError("smoke harness cannot reference WF03")
    if "dWTF2UGXX3R73PDW" not in refs:
        raise SafetyError("smoke harness must invoke WF04")
    return {"active": False, "publicWebhook": False, "schedule": False, "wf03Referenced": False, "wf04Referenced": True}


def validate_mock_contracts(contracts):
    text = contracts["text"]
    if not (text.get("success") is True and isinstance(text.get("result"), str) and isinstance(text.get("provider"), str) and isinstance(text.get("retryCount"), int) and isinstance(text.get("timestamp"), str)):
        raise SafetyError("text mock schema mismatch")
    image = contracts["image"]
    if not (image.get("success") is True and isinstance(image.get("imageBase64"), str) and image.get("format") == "png" and isinstance(image.get("context"), dict)):
        raise SafetyError("image mock schema mismatch")
    tts = contracts["tts"]
    if not isinstance(tts.get("audio_url"), str):
        raise SafetyError("TTS mock schema mismatch")
    render = contracts["render"]
    if not (render.get("success") is True and isinstance(render.get("videoUrl"), str) and isinstance(render.get("thumbnailUrl"), str)):
        raise SafetyError("renderer mock schema mismatch")
    failure = contracts["failure"]
    required = {"jobId", "workerId", "leaseToken", "attemptNumber", "pipelineRevision", "stageRunId", "runToken", "error", "failureClass", "retryable"}
    if not required <= failure.keys():
        raise SafetyError("WF14 failure mock schema mismatch")
    return True


def load_json_contract(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
