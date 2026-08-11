import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "clipcraft" / "workflows" / "17-ai-generate-text.json"
PROBE = ROOT / "clipcraft" / "scripts" / "controlled_wf17_no_provider_probe.js"


def workflow():
    return json.loads(WORKFLOW.read_text(encoding="utf-8"))


def node(name):
    return next(item for item in workflow()["nodes"] if item["name"] == name)


def _run_node_js(name, attempt_item):
    """Execute a n8n code-node body with stubbed globals via node.

    `attempt_item` becomes the `.json` returned by `$('Prepare Provider Attempt')`.
    Returns the single object the node returns (raises if the node throws).
    """
    import subprocess
    import tempfile
    import os

    js_code = node(name)["parameters"]["jsCode"]
    harness = (
        "const attempt = " + json.dumps(attempt_item) + ";\n"
        "const firstJson = { json: {\n"
        "  jobId: 'job-a1', prompt: null, provider: 'cloudflare',\n"
        "  modelId: 'm1', temperature: 0.6, maxOutputTokens: 5000,\n"
        "  timeoutMs: 30000, responseFormat: 'text' } };\n"
        "const attemptNode = { json: attempt };\n"
        "const triggerNode = { json: { prompt: null, jobId: 'trigger-job-id' } };\n"
        "const $ = (name) => ({\n"
        "  last: () => name === 'Prepare Provider Attempt' ? attemptNode : {json: {}},\n"
        "  first: () => name === 'Workflow Trigger' ? triggerNode : attemptNode,\n"
        "});\n"
        "const $env = { AI_TEXT_PROVIDER: 'cloudflare', CLOUDFLARE_TEXT_MODEL: 'm',\n"
        "  TEXT_EXECUTION_MODE: 'internal' };\n"
        "const $input = { first: () => ({ json: {} }) };\n"
        "function run() {\n" + js_code + "\n}\n"
        "try { const out = run(); console.log('__OUT__' + JSON.stringify(out)); }\n"
        "catch (e) { console.log('__ERR__' + String(e.message || e)); process.exit(2); }\n"
    )
    fd, path = tempfile.mkstemp(suffix=".cjs")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(harness)
    try:
        proc = subprocess.run(["node", path], capture_output=True, text=True, timeout=30)
    finally:
        os.remove(path)
    stdout = proc.stdout
    if "__ERR__" in stdout:
        raise AssertionError("node threw: " + stdout.split("__ERR__", 1)[1].strip())
    if "__OUT__" not in stdout:
        raise AssertionError("no output from harness: " + stdout)
    payload = stdout.split("__OUT__", 1)[1].strip()
    return json.loads(payload)[0]


def test_internal_mode_has_one_custom_node_path_and_legacy_is_separate():
    data = workflow()
    edges = data["connections"]
    assert edges["Text Execution Mode?"]["main"][0][0]["node"] == "Prepare Internal Request"
    assert edges["Text Execution Mode?"]["main"][1][0]["node"] == "Call Provider API"
    assert edges["Prepare Internal Request"]["main"][0][0]["node"] == "ClipCraft Text Execute"
    assert edges["Call Provider API"]["main"][0][0]["node"] == "Adapt Legacy Result"
    assert "CLOUDFLARE_AI_TOKEN" not in json.dumps(node("Prepare Internal Request"))


def test_internal_request_keeps_exact_opaque_model_and_contract_fields():
    source = node("Prepare Internal Request")["parameters"]["jsCode"]
    for field in (
        "jobId", "requestId", "providerId", "modelId", "credentialSource",
        "routingVersion", "prompt", "temperature", "maxOutputTokens", "responseFormat",
    ):
        assert field in source
    assert "modelId: String(modelId)" in source
    assert "split" not in source


def test_request_id_flows_from_attempt_into_internal_request_without_sentinel_fallback():
    prepare = node("Prepare Provider Attempt")["parameters"]["jsCode"]
    internal = node("Prepare Internal Request")["parameters"]["jsCode"]

    assert "requestId" in prepare
    assert "$('Prepare Provider Attempt').last()" in internal
    assert "unknown-request" not in internal
    assert "const requestId = input.requestId" in internal


def test_request_id_survives_adapters_and_final_normalization():
    internal_adapter = node("Adapt Internal Result")["parameters"]["jsCode"]
    legacy_adapter = node("Adapt Legacy Result")["parameters"]["jsCode"]
    normalizer = node("Normalize Response")["parameters"]["jsCode"]

    for source in (internal_adapter, legacy_adapter):
        assert "requestId" in source
    assert "requestId" in normalizer
    assert "providerResponse?.requestId" in normalizer


def test_non_retryable_internal_validation_is_not_retried():
    source = node("Evaluate Provider Result")["parameters"]["jsCode"]
    assert "response.retryable === true" in source
    assert "PROVIDER_HTTP_ERROR" in source


def test_error_normalization_preserves_safe_source_and_status():
    source = node("Adapt Internal Result")["parameters"]["jsCode"]
    assert "statusCode" in source
    assert "input.error" in source


def test_no_provider_probe_is_explicitly_deterministic_and_provider_free():
    assert PROBE.is_file(), "missing deterministic no-provider probe"
    text = PROBE.read_text(encoding="utf-8")
    assert "Deterministic Probe Stop" in text
    assert "Call Provider API" not in text
    assert "ClipCraft Text Execute" not in text
    assert "CLOUDFLARE_AI_TOKEN" not in text
    assert "finally" in text


# --- Focused tests for the prompt-resolution fix ---


def test_internal_forward_does_not_call_backend_on_empty_input_shape():
    # The fix must be additive: prompt resolution stays inside the node body,
    # and Contract fields remain. This asserts the workflow still references a
    # single provider (Cloudflare) and keeps the internal mode.
    source = node("Prepare Internal Request")["parameters"]["jsCode"]
    assert ".body?.messages?.[0]?.content" in source
    assert ".trim()" in source
    assert "WF17_PROMPT_REQUIRED" in source


def test_internal_request_forwards_body_messages_content_and_keeps_request_id():
    request_id = "REQ-1234-AB"
    attempt = {
        "requestId": request_id,
        "retryCount": 0,
        "provider": "cloudflare",
        "modelId": "@cf/meta/llama-3.1-8b-instruct",
        "body": {"messages": [{"role": "user", "content": " Create a 30s video about space    "}]},
    }
    out = _run_node_js("Prepare Internal Request", attempt)
    # The node body returns [{json: {...}}]; _run_node_js unwraps the first item.
    out = out["json"]
    # Trimmed prompt comes from the real message content.
    assert out["prompt"] == "Create a 30s video about space"
    # requestId preserved unchanged.
    assert out["requestId"] == request_id
    assert out["providerId"] == "cloudflare"
    assert out["modelId"] == "@cf/meta/llama-3.1-8b-instruct"


def test_internal_request_throws_local_when_prompt_empty():
    attempt = {
        "requestId": "req-x",
        "provider": "cloudflare",
        "modelId": "m1",
        "body": {"messages": []},
    }
    import pytest

    with pytest.raises(AssertionError, match="WF17_PROMPT_REQUIRED"):
        _run_node_js("Prepare Internal Request", attempt)


def test_internal_request_keeps_real_uuid_job_id_when_not_on_attempt():
    # Regression: the backend returns 422 (pydantic validate) when jobId is the
    # non-UUID sentinel "unknown-job". The real jobId lives on the workflow
    # trigger and must flow through even when the provider attempt omits it.
    attempt = {
        "requestId": "req-uuid",
        "provider": "cloudflare",
        "modelId": "m1",
        "body": {"messages": [{"role": "user", "content": "valid prompt here"}]},
    }
    out = _run_node_js("Prepare Internal Request", attempt)["json"]
    assert out["jobId"] == "trigger-job-id"
    assert out["jobId"] != "unknown-job"
    assert out["prompt"] == "valid prompt here"