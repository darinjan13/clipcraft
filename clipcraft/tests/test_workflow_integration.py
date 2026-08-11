import base64
import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / "clipcraft" / "workflows"
WF09_BACKUP = (
    ROOT
    / "clipcraft"
    / "backups"
    / "phase-7-cutover"
    / "wf09-stage-hashing-20260804T132837Z.json"
)
WF09_PRE_ITEM_LINEAGE_BACKUP = (
    ROOT
    / "clipcraft"
    / "backups"
    / "phase-7-cutover"
    / "wf09-stage-hashing-20260804T224750Z.json"
)
STAGE_WORKFLOWS = [
    "04-generate-script-and-scenes.json",
    "05-generate-scene-images.json",
    "06-generate-narration.json",
    "07-build-captions.json",
    "08-build-render-manifest.json",
    "09-render-video.json",
]
INTERNAL_WORKFLOW_TRIGGER_TARGETS = [
    *STAGE_WORKFLOWS,
    "14-error-handler.json",
    "17-ai-generate-text.json",
    "18-ai-generate-image.json",
]


def workflow(name):
    return json.loads((WORKFLOWS / name).read_text(encoding="utf-8"))


def node_map(data):
    return {node["name"]: node for node in data["nodes"]}


def all_text(data):
    return json.dumps(data, sort_keys=True)


def workflow_edges(data):
    edges = {node["name"]: set() for node in data["nodes"]}
    for source, outputs in data["connections"].items():
        for branch in outputs.get("main", []):
            edges[source].update(link["node"] for link in branch)
    return edges


def path_exists(edges, start, target, forbidden=frozenset()):
    pending = [start]
    visited = set(forbidden)
    while pending:
        node = pending.pop()
        if node == target:
            return True
        if node in visited:
            continue
        visited.add(node)
        pending.extend(edges.get(node, ()))
    return False


def execute_code_node(js_code, input_json):
    runner = """
const code = Buffer.from(process.argv[1], 'base64').toString('utf8');
const input = JSON.parse(Buffer.from(process.argv[2], 'base64').toString('utf8'));
const loadLegacyCrypto = moduleName => {
  if (moduleName === 'crypto') return require('crypto');
  throw new Error(`Module not allowed: ${moduleName}`);
};
const execute = new Function('$json', 'require', `return (async () => {${code}\n})();`);
execute(input, loadLegacyCrypto)
  .then(items => process.stdout.write(JSON.stringify(items)))
  .catch(error => { console.error(error.stack || error); process.exit(1); });
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            runner,
            base64.b64encode(js_code.encode("utf-8")).decode("ascii"),
            base64.b64encode(json.dumps(input_json).encode("utf-8")).decode("ascii"),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return json.loads(completed.stdout)


def load_wf09_gate_a_contract():
    contract_path = ROOT / "clipcraft" / "scripts" / "wf09_gate_a_contract.js"
    completed = subprocess.run(
        [
            "node",
            "-e",
            "const contract = require(process.argv[1]); process.stdout.write(JSON.stringify(contract));",
            str(contract_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return json.loads(completed.stdout)


def test_worker_uses_fenced_claim_and_internal_execute_workflows():
    data = workflow("03-video-job-worker.json")
    nodes = node_map(data)
    claim = nodes["Claim Next Job"]
    assert "claim_next_video_job_fenced" in all_text(claim)
    assert "p_worker_id" in claim["parameters"]["jsonBody"]
    assert "p_lease_seconds" in claim["parameters"]["jsonBody"]
    assert "p_lease_seconds" in claim["parameters"]["jsonBody"]
    assert nodes["Extract Job Info"]["type"] == "n8n-nodes-base.code"
    calls = [node for node in data["nodes"] if node["name"].startswith("Call ")]
    assert len(calls) == 6
    assert all(node["type"] == "n8n-nodes-base.executeWorkflow" for node in calls)
    assert all("workflowId" in node["parameters"] for node in calls)
    assert all(
        node["type"] == "n8n-nodes-base.code"
        for node in data["nodes"]
        if node["name"].startswith("Update Progress ")
    )
    assert nodes["Complete Job RPC"]["type"] == "n8n-nodes-base.code"


def test_internal_stages_are_fenced_and_not_public_webhooks():
    for filename in STAGE_WORKFLOWS:
        data = workflow(filename)
        text = all_text(data)
        assert not any(node["type"] == "n8n-nodes-base.webhook" for node in data["nodes"])
        assert not any(node["type"] == "n8n-nodes-base.respondToWebhook" for node in data["nodes"])
        assert "workflowTrigger" in text
        assert "begin_job_stage" in text
        assert "reserve_stage_external_attempt" in text
        assert "heartbeat_video_job" in text
        assert "finalize_stage_success" in text or "fail_job_stage" in text
        assert "={{ $env.SUPABASE_URL" in text
        assert "={ $env.SUPABASE_URL" not in text
        for field in ("jobId", "workerId", "leaseToken", "attemptNumber", "pipelineRevision"):
            assert field in text


def test_error_handler_owns_fenced_failure_finalization():
    data = workflow("14-error-handler.json")
    text = all_text(data)
    assert not any(node["type"] == "n8n-nodes-base.webhook" for node in data["nodes"])
    assert "workflowTrigger" in text
    assert "heartbeat_video_job" in text
    assert "fail_job_stage" in text
    for field in ("jobId", "workerId", "leaseToken", "attemptNumber", "pipelineRevision", "stageRunId", "runToken"):
        assert field in text
    trigger = next(node for node in data["nodes"] if node["type"] == "n8n-nodes-base.workflowTrigger")
    assert trigger["typeVersion"] == 1
    assert trigger["parameters"].get("events") == ["update"]


def test_error_handler_accepts_legacy_generic_and_fully_fenced_failure_contexts():
    data = workflow("14-error-handler.json")
    nodes = node_map(data)
    text = all_text(data)
    trigger_target = data["connections"]["Workflow Trigger"]["main"][0][0]["node"]
    normalize = nodes[trigger_target]["parameters"]["jsCode"]
    assert "$json.body ?? $json" in normalize
    assert "jobId" in normalize and "job_id" in normalize
    assert "error" in normalize
    throwing_statements = [statement for statement in normalize.split(";") if "throw" in statement]
    for statement in throwing_statements:
        for field in ("workerId", "leaseToken", "attemptNumber", "pipelineRevision", "stageRunId", "runToken"):
            assert field not in statement, f"generic failures must not require {field}"
    assert "persist_video_job_failure" in text
    assert "fail_job_stage" in text
    conditional_text = "\n".join(
        all_text(node["parameters"])
        for node in data["nodes"]
        if node["type"] in ("n8n-nodes-base.code", "n8n-nodes-base.if")
    )
    for field in ("workerId", "leaseToken", "attemptNumber", "pipelineRevision", "stageRunId", "runToken"):
        assert field in conditional_text


def test_error_handler_uses_deterministic_failure_idempotency_metadata():
    data = workflow("14-error-handler.json")
    idempotency_logic = "\n".join(
        all_text(node["parameters"])
        for node in data["nodes"]
        if "idempotency" in all_text(node["parameters"]).lower()
    )
    assert idempotency_logic
    assert "jobId" in idempotency_logic or "job_id" in idempotency_logic
    assert "execution" in idempotency_logic or (
        "stage" in idempotency_logic and "attempt" in idempotency_logic.lower()
    )
    for nondeterministic_source in ("Date.now", "new Date", "Math.random", "randomUUID"):
        assert nondeterministic_source not in idempotency_logic
    text = all_text(data)
    assert "idempotency" in text
    assert "metadata" in text


def test_error_handler_persists_generic_failure_after_optional_fenced_finalization():
    data = workflow("14-error-handler.json")
    generic_nodes = [node for node in data["nodes"] if "persist_video_job_failure" in all_text(node)]
    assert len(generic_nodes) == 1
    persist_name = generic_nodes[0]["name"]
    fenced_nodes = [node for node in data["nodes"] if "fail_job_stage" in all_text(node)]
    assert len(fenced_nodes) == 1
    fenced_name = fenced_nodes[0]["name"]
    trigger_name = next(node["name"] for node in data["nodes"] if node["type"] == "n8n-nodes-base.workflowTrigger")
    edges = workflow_edges(data)
    fence_only_nodes = {
        node["name"] for node in data["nodes"]
        if "fail_job_stage" in all_text(node) or "heartbeat_video_job" in all_text(node)
    }
    assert path_exists(edges, trigger_name, persist_name, fence_only_nodes), (
        "generic contexts must reach persistence without fenced finalization"
    )
    fenced_then_persist = path_exists(edges, trigger_name, fenced_name) and path_exists(edges, fenced_name, persist_name)
    persist_then_fenced = path_exists(edges, trigger_name, persist_name) and path_exists(edges, persist_name, fenced_name)
    assert fenced_then_persist or persist_then_fenced, (
        "fully leased failures must include both fenced and generic persistence"
    )


def test_content_generation_parameters_remain_stable_and_event_logging_is_non_blocking():
    contracts = {
        "04-generate-script-and-scenes.json": {
            "Build Prompt": ("brief.contentStyle", "fullScenes", "full video duration"),
            "Validate Output": ("Invalid AI JSON", "motions", "transitions"),
            "Execute AI Text": ("17",),
        },
        "06-generate-narration.json": {
            "Extract Narration Text": ("script.fullNarration", "s.narration).join(' ')",),
            "Call TTS": ("/tts", '"voice": "af_heart"', '"language": "en"'),
        },
        "07-build-captions.json": {
            "Generate ASS File": ("PlayResX: 1080", "PlayResY: 1920", "captions.ass"),
        },
        "08-build-render-manifest.json": {
            "Build Manifest": ("width: 1080", "height: 1920", "fps: 30", "render-manifest.json"),
        },
        "09-render-video.json": {
            "Execute FFmpeg": ("http://clipcraft-renderer:8088/render", "={{ { jobId: $json.id } }}"),
        },
    }
    for filename, node_contracts in contracts.items():
        data = workflow(filename)
        nodes = node_map(data)
        for name, fragments in node_contracts.items():
            parameters = "\n".join(str(value) for value in nodes[name]["parameters"].values())
            for fragment in fragments:
                assert fragment in parameters, f"{filename}:{name} changed content-generation parameters"
        event_writers = [
            node for node in data["nodes"]
            if node["type"] in (
                "n8n-nodes-base.httpRequest", "n8n-nodes-base.postgres",
                "n8n-nodes-base.supabase", "n8n-nodes-base.executeWorkflow",
            )
            and (
                "video_job_event" in all_text(node["parameters"]).lower()
                or "event_type" in all_text(node["parameters"]).lower()
                or "event" in node["name"].lower()
            )
        ]
        assert all(
            node.get("continueOnFail") is True
            or node.get("onError") in ("continueRegularOutput", "continueErrorOutput")
            for node in event_writers
        ), (
            f"{filename} event side channels must not fail primary generation"
        )

def test_internal_workflow_trigger_targets_use_runtime_supported_events():
    for filename in INTERNAL_WORKFLOW_TRIGGER_TARGETS:
        data = workflow(filename)
        trigger = next(node for node in data["nodes"] if node["type"] == "n8n-nodes-base.workflowTrigger")
        assert trigger["typeVersion"] == 1
        assert isinstance(trigger["parameters"].get("events"), list)
        assert trigger["parameters"]["events"] == ["update"]
        assert not any(node["type"] == "n8n-nodes-base.webhook" for node in data["nodes"])
        assert not any(node["type"] == "n8n-nodes-base.scheduleTrigger" for node in data["nodes"])


def test_uuid_generation_uses_the_runtime_safe_v4_strategy():
    for filename in ("02-create-video-job.json", "05-generate-scene-images.json", "17-ai-generate-text.json", "18-ai-generate-image.json"):
        data = workflow(filename)
        code = "\n".join(
            node["parameters"].get("jsCode", "")
            for node in data["nodes"]
            if node["type"] == "n8n-nodes-base.code"
        )
        assert "crypto.randomUUID" not in code
        assert "globalThis.crypto" not in code
        assert "Uint8Array(16)" in code
        assert "| 0x40" in code
        assert "| 0x80" in code


def test_wf18_normalizer_does_not_require_the_unselected_legacy_request_node():
    data = workflow("18-ai-generate-image.json")
    normalize = node_map(data)["Normalize Response"]["parameters"]["jsCode"]
    assert "$('Build Request')" not in normalize


def test_wf04_enters_the_stage_context_before_loading_the_job():
    data = workflow("04-generate-script-and-scenes.json")
    edges = data["connections"]

    assert edges["Workflow Trigger"]["main"][0][0]["node"] == "Normalize Stage Context"
    assert edges["Normalize Stage Context"]["main"][0][0]["node"] == "Hash Stage Input"
    assert edges["Hash Stage Input"]["main"][0][0]["node"] == "Begin Stage"
    assert edges["Merge Heartbeat Context"]["main"][0][0]["node"] == "Validate"
    assert edges["Workflow Trigger"]["main"][0][0]["node"] != "Validate"


def test_wf04_rejects_missing_run_token_without_a_fallback():
    nodes = node_map(workflow("04-generate-script-and-scenes.json"))
    merge = nodes["Merge Stage Context"]["parameters"]["jsCode"]
    failure = nodes["Finalize Provider Failure"]["parameters"]["jsonBody"]

    assert "RUN_TOKEN_REQUIRED" in merge
    assert "$if($('Merge Heartbeat Context').isExecuted" not in failure
    assert "runToken" in failure


def test_wf17_internal_attempts_have_valid_request_ids_without_caller_changes():
    data = workflow("17-ai-generate-text.json")
    nodes = node_map(data)
    attempt = nodes["Prepare Provider Attempt"]["parameters"]["jsCode"]
    internal = nodes["Prepare Internal Request"]["parameters"]["jsCode"]
    assert "Uint8Array(16)" in attempt
    assert "| 0x40" in attempt
    assert "retryCount > 0" in attempt
    assert "Workflow Trigger" in internal
    assert "requestId" in internal


def test_regeneration_adapters_are_enqueue_only_and_idempotent():
    for filename in ("12-regenerate-scene.json", "13-regenerate-video.json"):
        data = workflow(filename)
        text = all_text(data)
        assert "enqueue_regeneration" in text
        assert "client_request_id" in text
        assert "p_operation" in text
        assert "={{ $env.SUPABASE_URL" in text
        assert "={ $env.SUPABASE_URL" not in text
        assert "('SCENE_" not in text
        assert "('SCRIPT_" not in text
        assert not any(
            node.get("type") == "n8n-nodes-base.httpRequest"
            and any(method in json.dumps(node.get("parameters", {})) for method in ("PATCH", "DELETE"))
            for node in data["nodes"]
        )


def test_wf16_is_not_modified_by_4b2_contracts():
    data = workflow("16-resolve-asset-paths.json")
    assert any(node.get("name") == "Resolve Path" for node in data["nodes"])
    assert "workflowTrigger" in all_text(data)


def test_edited_workflow_graphs_have_no_stale_or_dangling_connections():
    for filename in ["03-video-job-worker.json", *STAGE_WORKFLOWS, "12-regenerate-scene.json", "13-regenerate-video.json", "14-error-handler.json"]:
        data = workflow(filename)
        names = {node["name"] for node in data["nodes"]}
        assert set(data["connections"]) <= names
        for value in data["connections"].values():
            for outputs in value.get("main", []):
                assert all(link["node"] in names for link in outputs)


def test_wf17_has_a_mode_gate_with_legacy_default():
    data = workflow("17-ai-generate-text.json")
    nodes = node_map(data)
    edges = workflow_edges(data)

    mode = nodes["Text Execution Mode?"]
    assert mode["type"] == "n8n-nodes-base.if"
    condition = json.dumps(mode["parameters"]["conditions"])
    assert "TEXT_EXECUTION_MODE" in condition
    assert "internal" in condition

    gate = data["connections"]["Text Execution Mode?"]["main"]
    assert len(gate) == 2
    internal_branch, legacy_branch = gate[0], gate[1]
    assert internal_branch[0]["node"] == "Prepare Internal Request"
    assert legacy_branch[0]["node"] == "Call Provider API"

    assert "Prepare Internal Request" in edges
    assert "ClipCraft Text Execute" in edges
    assert "Adapt Internal Result" in edges
    assert "Call Provider API" in edges
    assert "Adapt Legacy Result" in edges
    assert "Adapt Internal Result" in edges["ClipCraft Text Execute"]
    assert "Adapt Legacy Result" in edges["Call Provider API"]
    assert "Evaluate Provider Result" in edges["Adapt Internal Result"]
    assert "Evaluate Provider Result" in edges["Adapt Legacy Result"]


def test_wf17_mode_gate_does_not_allow_dual_provider_execution():
    data = workflow("17-ai-generate-text.json")
    edges = workflow_edges(data)
    mode = "Text Execution Mode?"
    gate = data["connections"][mode]["main"]

    internal_branch = gate[0][0]["node"]
    legacy_branch = gate[1][0]["node"]
    internal_nodes = {
        "Prepare Internal Request", "ClipCraft Text Execute", "Adapt Internal Result",
    }
    legacy_nodes = {
        "Call Provider API", "Adapt Legacy Result",
    }
    assert internal_nodes.isdisjoint(legacy_nodes)
    assert internal_branch in internal_nodes
    assert legacy_branch in legacy_nodes

    for node in internal_nodes:
        for target in edges.get(node, ()):
            assert target not in legacy_nodes, "internal branch must not reach legacy provider nodes"
    for node in legacy_nodes:
        for target in edges.get(node, ()):
            assert target not in internal_nodes, "legacy branch must not reach internal provider nodes"

    assert "Evaluate Provider Result" in edges["Adapt Internal Result"]
    assert "Evaluate Provider Result" in edges["Adapt Legacy Result"]

    retry_paths = [link["node"] for link in data["connections"]["Retryable Failure?"]["main"][0]]
    non_retry_paths = [link["node"] for link in data["connections"]["Retryable Failure?"]["main"][1]]
    assert "Increment Retry" in retry_paths
    assert "Normalize Response" in non_retry_paths
    assert "Prepare Provider Attempt" in edges["Increment Retry"]


def test_wf17_internal_branch_uses_custom_node_and_encrypted_credential_only():
    data = workflow("17-ai-generate-text.json")
    text = all_text(data)
    custom = next(node for node in data["nodes"] if node["type"] == "CUSTOM.clipCraftTextExecute")

    assert custom["name"] == "ClipCraft Text Execute"
    assert "clipCraftInternalApi" in json.dumps(custom["credentials"])
    assert "signingSecret" not in json.dumps(custom["credentials"])
    assert "CLOUDFLARE_AI_TOKEN" not in json.dumps(custom)
    assert "Authorization" not in json.dumps(custom)
    assert "N8N_INTERNAL_SIGNING_SECRET" not in text
    assert "/internal/ai/text/execute" not in text

    for key in ("jobId", "requestId", "providerId", "modelId", "credentialSource", "routingVersion"):
        assert key in json.dumps(custom["parameters"])


def test_wf17_internal_branch_preserves_raw_model_ids():
    data = workflow("17-ai-generate-text.json")
    custom = next(node for node in data["nodes"] if node["type"] == "CUSTOM.clipCraftTextExecute")
    model_expression = custom["parameters"]["modelId"]
    assert "={{ $json.modelId }}" == model_expression
    assert "split" not in model_expression
    assert ":" not in json.dumps(custom["parameters"]["modelId"]).replace("$json.modelId", "")


def test_wf17_adapters_converge_into_the_evaluator_shape():
    data = workflow("17-ai-generate-text.json")
    nodes = node_map(data)
    edges = workflow_edges(data)

    internal = nodes["Adapt Internal Result"]["parameters"]["jsCode"]
    legacy = nodes["Adapt Legacy Result"]["parameters"]["jsCode"]

    for code, branch in ((internal, "internal"), (legacy, "legacy")):
        assert "success" in code
        assert "result" in code
        assert "provider" in code
        assert "statusCode" in code

    assert "result: input.text" in internal
    assert "errors" in internal
    assert "error" in internal
    assert "Evaluate Provider Result" in edges["Adapt Internal Result"]
    assert "Evaluate Provider Result" in edges["Adapt Legacy Result"]
    assert "result?.response" in nodes["Normalize Response"]["parameters"]["jsCode"] or "providerResponse?.result" in nodes["Normalize Response"]["parameters"]["jsCode"]


def test_wf17_internal_failure_uses_existing_failure_path_without_legacy_fallback():
    data = workflow("17-ai-generate-text.json")
    nodes = node_map(data)
    edges = workflow_edges(data)

    internal_adapter = nodes["Adapt Internal Result"]["parameters"]["jsCode"]
    assert "retryable" in internal_adapter
    assert "error.retryable" in internal_adapter

    evaluator = nodes["Evaluate Provider Result"]["parameters"]["jsCode"]
    assert "shouldRetry" in evaluator
    assert "retryExhausted" in evaluator
    assert "Normalize Response" in edges["Retryable Failure?"]

    retry_true = [link["node"] for link in data["connections"]["Retryable Failure?"]["main"][0]]
    retry_false = [link["node"] for link in data["connections"]["Retryable Failure?"]["main"][1]]
    assert "Increment Retry" in retry_true
    assert "Normalize Response" in retry_false
    assert "Evaluate Provider Result" in edges["Adapt Internal Result"]
    assert "Call Provider API" not in edges["Adapt Internal Result"]
    assert "Adapt Legacy Result" not in edges["Adapt Internal Result"]


def test_wf17_callers_consume_only_response_result_and_are_unchanged():
    for filename in ("01-chat-message.json", "04-generate-script-and-scenes.json"):
        data = workflow(filename)
        text = all_text(data)
        assert '"17"' in text or "17" in text
        assert "response.result" in text
        assert "clipCraftTextExecute" not in text
        assert "signingSecret" not in text


def test_wf05_generates_one_fresh_request_id_per_scene_item():
    data = workflow("05-generate-scene-images.json")
    prepare = node_map(data)["Prepare Items"]["parameters"]["jsCode"]

    assert "uuidV4" in prepare
    assert "request_id" in prepare
    assert "job_id +" not in prepare
    assert "scene_id +" not in prepare
    assert "scene_index +" not in prepare
    assert "request_id: uuidV4()" in prepare


def test_wf18_has_legacy_default_mode_gate_and_disjoint_provider_branches():
    data = workflow("18-ai-generate-image.json")
    nodes = node_map(data)
    edges = workflow_edges(data)

    initial_mode = nodes["Initial Image Execution Mode?"]
    assert initial_mode["type"] == "n8n-nodes-base.if"
    condition = json.dumps(initial_mode["parameters"]["conditions"])
    assert "IMAGE_EXECUTION_MODE" in condition
    assert "internal" in condition

    initial_gate = data["connections"]["Initial Image Execution Mode?"]["main"]
    assert initial_gate[0][0]["node"] == "Build Internal Image Request"
    assert initial_gate[1][0]["node"] == "Build Request"
    assert "CLOUDFLARE_AI_TOKEN" not in json.dumps(nodes["Build Internal Image Request"])
    assert "Authorization" not in json.dumps(nodes["Build Internal Image Request"])
    retry_mode = data["connections"]["Image Execution Mode?"]["main"]
    assert retry_mode[0][0]["node"] == "Prepare Internal Image Request"
    assert retry_mode[1][0]["node"] == "Call Provider API"

    internal_nodes = {
        "Prepare Internal Image Request",
        "Assign Internal Request ID",
        "ClipCraft Image Execute",
        "Adapt Internal Image Result",
    }
    legacy_nodes = {"Call Provider API"}
    assert internal_nodes.isdisjoint(legacy_nodes)
    for node in internal_nodes:
        assert not edges.get(node, set()) & legacy_nodes
    assert "Evaluate Provider Result" in edges["Adapt Internal Image Result"]
    assert "Evaluate Provider Result" in edges["Call Provider API"]
    assert "Image Execution Mode?" in edges["Prepare Provider Attempt"]


def test_wf18_internal_request_preserves_scene_and_attempt_fields():
    data = workflow("18-ai-generate-image.json")
    nodes = node_map(data)
    prepare = nodes["Prepare Internal Image Request"]["parameters"]["jsCode"]
    custom = nodes["ClipCraft Image Execute"]
    adapter = nodes["Adapt Internal Image Result"]["parameters"]["jsCode"]

    for field in ("jobId", "sceneId", "sceneIndex", "requestId", "providerId", "modelId", "credentialSource", "routingVersion", "prompt", "width", "height", "seed", "steps"):
        assert field in prepare or field in json.dumps(custom["parameters"])
    assert "request_id" in prepare
    assert "randomUUID" not in prepare
    request_id = nodes["Assign Internal Request ID"]["parameters"]["jsCode"]
    assert "uuidV4" in request_id
    assert "retryCount > 0" in request_id
    assert "input.requestId" in request_id
    assert "getBinaryDataBuffer" in adapter
    assert "toString('base64')" in adapter
    assert "image/png" in adapter
    assert "image/jpeg" in adapter
    assert "input.mimeType" in adapter
    assert "AI_RESPONSE_INVALID" in adapter
    assert "providerResponse" not in adapter
    assert "clipCraftInternalApi" in json.dumps(custom["credentials"])
    assert "CLOUDFLARE_AI_TOKEN" not in json.dumps(custom)
    assert "Authorization" not in json.dumps(custom)
    preserve = nodes["Preserve Request ID"]["parameters"]["jsCode"]
    assert "providerResponse?.requestId" in preserve


def test_wf18_internal_branch_preserves_retry_and_downstream_contracts():
    data = workflow("18-ai-generate-image.json")
    nodes = node_map(data)
    edges = workflow_edges(data)

    assert "Prepare Provider Attempt" in edges["Increment Retry"]
    assert "Increment Retry" in data["connections"]["Retryable Failure?"]["main"][0][0]["node"]
    assert "Normalize Response" in data["connections"]["Retryable Failure?"]["main"][1][0]["node"]
    assert "providerResponse?.result?.image" in nodes["Normalize Response"]["parameters"]["jsCode"]
    assert "context" in nodes["Normalize Response"]["parameters"]["jsCode"]

    wf05 = workflow("05-generate-scene-images.json")
    save = node_map(wf05)["Save Image File"]["parameters"]["jsCode"]
    assert "response.imageBase64" in save
    assert "context.jobId" in save
    assert "context.sceneId" in save
    assert "context.sceneIndex" in save
    assert "Preserve Request ID" in edges["Normalize Response"]
    assert node_map(data)["Call Provider API"]["parameters"]["url"] == "={{ $json.url }}"
    assert "scene-' + padded + '.png" in save


def test_wf04_wf08_stage_normalizers_retain_raw_canonical_semantics():
    stage_defaults = {
        "04-generate-script-and-scenes.json": ("generate_script", "job"),
        "05-generate-scene-images.json": ("generate_images", "all-scenes"),
        "06-generate-narration.json": ("generate_voice", "job"),
        "07-build-captions.json": ("build_captions", "job"),
        "08-build-render-manifest.json": ("build_manifest", "job"),
    }
    input_json = {
        "jobId": "11111111-1111-4111-8111-111111111111",
        "workerId": "worker-1",
        "leaseToken": "lease-1",
        "attemptNumber": 3,
        "pipelineRevision": "7",
        "currentRevision": "9",
    }

    for filename, (stage, item_key) in stage_defaults.items():
        normalize = node_map(workflow(filename))["Normalize Stage Context"]["parameters"]["jsCode"]
        items = execute_code_node(normalize, input_json)
        assert len(items) == 1
        output = items[0]["json"]
        expected_canonical = json.dumps(
            {
                "jobId": input_json["jobId"],
                "pipelineRevision": input_json["pipelineRevision"],
                "stage": stage,
                "itemKey": item_key,
                "revision": input_json["currentRevision"],
            },
            separators=(",", ":"),
        )

        assert output.get("stageHashInput") == expected_canonical
        assert "inputHash" not in output
        for key in ("jobId", "workerId", "leaseToken", "currentRevision"):
            assert output[key] == input_json[key]
        assert output["attemptNumber"] == 3
        assert output["pipelineRevision"] == 7
        assert output["stage"] == stage
        assert output["itemKey"] == item_key
        assert not re.search(r"require\s*\(\s*['\"]crypto['\"]\s*\)", normalize)


def test_wf09_accepts_legacy_context_and_canonicalizes_numeric_pipeline_revision():
    normalize = node_map(workflow("09-render-video.json"))["Normalize Stage Context"][
        "parameters"
    ]["jsCode"]
    job_id = "11111111-1111-4111-8111-111111111111"
    items = execute_code_node(
        normalize,
        {
            "body": {
                "id": job_id,
                "claimed_by": "legacy-worker",
                "lease_token": "legacy-lease",
                "attempt_number": "4",
                "pipeline_revision": "7",
            }
        },
    )
    output = items[0]["json"]

    assert output["jobId"] == job_id
    assert output["workerId"] == "legacy-worker"
    assert output["leaseToken"] == "legacy-lease"
    assert output["attemptNumber"] == 4
    assert output["pipelineRevision"] == 7
    assert output["stage"] == "render"
    assert output["itemKey"] == "job"
    assert output["stageHashInput"] == json.dumps(
        {
            "jobId": job_id,
            "pipelineRevision": 7,
            "stage": "render",
            "itemKey": "job",
            "revision": 7,
        },
        separators=(",", ":"),
    )
    assert "inputHash" not in output
    assert not re.search(r"require\s*\(\s*['\"]crypto['\"]\s*\)", normalize)


def test_wf09_trigger_enters_fenced_stage_wrapper_without_bypass():
    data = workflow("09-render-video.json")
    edges = workflow_edges(data)
    expected_trigger_connection = {
        "main": [[{"node": "Normalize Stage Context", "type": "main", "index": 0}]]
    }

    assert data["connections"].get("Workflow Trigger") == expected_trigger_connection
    assert path_exists(edges, "Workflow Trigger", "Validate Input")

    required_nodes = (
        "Normalize Stage Context",
        "Hash Stage Input",
        "Begin Stage",
        "Merge Stage Context",
        "Stage Started?",
        "Reserve External Attempt",
        "Merge Attempt Context",
        "Heartbeat Stage Lease",
        "Merge Heartbeat Context",
    )
    for required_node in required_nodes:
        assert not path_exists(
            edges,
            "Workflow Trigger",
            "Validate Input",
            {required_node},
        ), f"Workflow Trigger bypasses required fenced node: {required_node}"


def test_wf09_stage_started_uses_exact_strict_boolean_if_schema():
    stage_started = node_map(workflow("09-render-video.json"))["Stage Started?"]

    assert stage_started["parameters"] == {
        "conditions": {
            "options": {
                "caseSensitive": True,
                "leftValue": "",
                "typeValidation": "strict",
                "version": 1,
            },
            "conditions": [
                {
                    "leftValue": "={{ $json.stageState === 'STARTED' }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "equals"},
                }
            ],
            "combinator": "and",
        },
        "options": {},
    }


def test_wf09_offline_runtime_declares_exact_safe_graph_contract():
    source = (ROOT / "clipcraft" / "scripts" / "wf09_gate_a_offline_runtime.js").read_text(
        encoding="utf-8"
    )
    expected_node_types = {
        "Manual Trigger": "n8n-nodes-base.manualTrigger",
        "Fixed Safe Input": "n8n-nodes-base.code",
        "Normalize Stage Context": "n8n-nodes-base.code",
        "Hash Stage Input": "n8n-nodes-base.crypto",
        "Stub Begin Stage": "n8n-nodes-base.code",
        "Merge Stage Context": "n8n-nodes-base.code",
        "Stage Started?": "n8n-nodes-base.if",
        "Stub Reserve External Attempt": "n8n-nodes-base.code",
        "Merge Attempt Context": "n8n-nodes-base.code",
        "Stub Heartbeat Stage Lease": "n8n-nodes-base.code",
        "Merge Heartbeat Context": "n8n-nodes-base.code",
        "Stub Render Output": "n8n-nodes-base.code",
        "Stub Build Response": "n8n-nodes-base.code",
        "Finalize Boundary": "n8n-nodes-base.code",
    }
    expected_connections = {
        "Manual Trigger": {"main": [[{"node": "Fixed Safe Input", "type": "main", "index": 0}]]},
        "Fixed Safe Input": {"main": [[{"node": "Normalize Stage Context", "type": "main", "index": 0}]]},
        "Normalize Stage Context": {"main": [[{"node": "Hash Stage Input", "type": "main", "index": 0}]]},
        "Hash Stage Input": {"main": [[{"node": "Stub Begin Stage", "type": "main", "index": 0}]]},
        "Stub Begin Stage": {"main": [[{"node": "Merge Stage Context", "type": "main", "index": 0}]]},
        "Merge Stage Context": {"main": [[{"node": "Stage Started?", "type": "main", "index": 0}]]},
        "Stage Started?": {"main": [[{"node": "Stub Reserve External Attempt", "type": "main", "index": 0}], []]},
        "Stub Reserve External Attempt": {"main": [[{"node": "Merge Attempt Context", "type": "main", "index": 0}]]},
        "Merge Attempt Context": {"main": [[{"node": "Stub Heartbeat Stage Lease", "type": "main", "index": 0}]]},
        "Stub Heartbeat Stage Lease": {"main": [[{"node": "Merge Heartbeat Context", "type": "main", "index": 0}]]},
        "Merge Heartbeat Context": {"main": [[{"node": "Stub Render Output", "type": "main", "index": 0}]]},
        "Stub Render Output": {"main": [[{"node": "Stub Build Response", "type": "main", "index": 0}]]},
        "Stub Build Response": {"main": [[{"node": "Finalize Boundary", "type": "main", "index": 0}]]},
    }
    node_types_match = re.search(r"const EXPECTED_NODE_TYPES = JSON\.parse\('([^\n]+)'\);", source)
    connections_match = re.search(r"const EXPECTED_CONNECTIONS = JSON\.parse\('([^\n]+)'\);", source)

    assert node_types_match
    assert connections_match
    assert json.loads(node_types_match.group(1)) == expected_node_types
    assert json.loads(connections_match.group(1)) == expected_connections
    build_response = load_wf09_gate_a_contract()["BUILD_RESPONSE_CODE"]
    for field in (
        "jobId", "stage", "itemKey", "attemptNumber", "pipelineRevision",
        "runToken", "inputHash", "videoUrl", "thumbnailUrl",
    ):
        assert f"{field}: input.{field}" in build_response
    assert "pairedItem: {item: 0}" in build_response
    assert "stableStringify(actualNodeTypes) !== stableStringify(EXPECTED_NODE_TYPES)" in source
    assert "stableStringify(workflow.connections) !== stableStringify(EXPECTED_CONNECTIONS)" in source
    assert "cleanupErrors" in source


def test_wf09_gate_a_harnesses_share_canonical_code_contract():
    contract = load_wf09_gate_a_contract()
    expected_keys = {
        "EXPECTED_JOB_ID",
        "EXPECTED_LEASE_TOKEN",
        "EXPECTED_STAGE_RUN_ID",
        "EXPECTED_RUN_TOKEN",
        "UNWRAP_CODE",
        "BEGIN_CODE",
        "RESERVE_CODE",
        "HEARTBEAT_CODE",
        "RENDER_CODE",
        "BUILD_RESPONSE_CODE",
        "FINALIZE_CODE",
    }
    assert set(contract) == expected_keys
    assert contract["EXPECTED_JOB_ID"] == "11111111-1111-4111-8111-111111111111"
    assert contract["EXPECTED_LEASE_TOKEN"] == "22222222-2222-4222-8222-222222222222"
    assert contract["EXPECTED_RUN_TOKEN"] == "33333333-3333-4333-8333-333333333333"
    assert contract["EXPECTED_STAGE_RUN_ID"] == "44444444-4444-4444-8444-444444444444"

    for filename in (
        "wf09_gate_a_offline_runtime.js",
        "controlled_wf09_graph_no_provider_probe.js",
    ):
        source = (ROOT / "clipcraft" / "scripts" / filename).read_text(encoding="utf-8")
        assert "require('./wf09_gate_a_contract')" in source

    code_names = {
        "UNWRAP_CODE",
        "BEGIN_CODE",
        "RESERVE_CODE",
        "HEARTBEAT_CODE",
        "RENDER_CODE",
        "BUILD_RESPONSE_CODE",
        "FINALIZE_CODE",
    }
    for name in code_names:
        code = contract[name]
        assert len(re.findall(r"return\s*\[\{\s*json\s*:", code)) == 1
        assert re.search(r"pairedItem\s*:\s*\{\s*item\s*:\s*0\s*\}", code)
        assert "providerCalls" not in code
        assert "rendererInvocations" not in code

    identity_fields = (
        "jobId",
        "stage",
        "itemKey",
        "attemptNumber",
        "pipelineRevision",
        "videoUrl",
        "thumbnailUrl",
        "inputHash",
        "runToken",
    )
    for field in identity_fields:
        assert f"{field}: input.{field}" in contract["BUILD_RESPONSE_CODE"]
        assert field in contract["FINALIZE_CODE"]
    assert "success: true" in contract["BUILD_RESPONSE_CODE"]
    assert "$input.all()" in contract["FINALIZE_CODE"]
    assert "items.length !== 1" in contract["FINALIZE_CODE"]
    assert "$('Hash Stage Input').first().json.inputHash" in contract["FINALIZE_CODE"]
    for flag in ("gateA", "finalizationBoundaryReached", "runTokenMatches", "inputHashMatches"):
        assert flag in contract["FINALIZE_CODE"]


def test_wf09_native_offline_runtime_preserves_item_lineage():
    expected_boundaries = [
        "Manual Trigger",
        "Fixed Safe Input",
        "Normalize Stage Context",
        "Hash Stage Input",
        "Stub Begin Stage",
        "Merge Stage Context",
        "Stage Started?",
        "Stub Reserve External Attempt",
        "Merge Attempt Context",
        "Stub Heartbeat Stage Lease",
        "Merge Heartbeat Context",
        "Stub Render Output",
        "Stub Build Response",
        "Finalize Boundary",
    ]
    harness = ROOT / "clipcraft" / "scripts" / "wf09_gate_a_offline_runtime.js"
    completed = subprocess.run(
        ["node", str(harness)],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.stdout.strip(), f"offline harness emitted no diagnostic: {completed.stderr}"
    try:
        diagnostic = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise AssertionError(
            f"offline harness emitted non-JSON output: {completed.stdout!r}; stderr={completed.stderr!r}"
        ) from error

    assert completed.returncode in (0, 1), (
        f"offline harness infrastructure failure (exit {completed.returncode}): {diagnostic}"
    )
    assert diagnostic["isolated"] is True
    assert diagnostic["offline"] is True
    assert diagnostic["networkMode"] == "none"
    assert diagnostic["executionId"].startswith("isolated-cli-")
    assert diagnostic["infrastructureError"] is None
    assert diagnostic["expectedNodeNames"] == expected_boundaries
    assert set(diagnostic["outputCounts"]) == set(expected_boundaries)

    if completed.returncode == 1:
        reached = expected_boundaries[:7]
        missing = expected_boundaries[7:]
        assert diagnostic["executedNodeNames"] == reached
        assert diagnostic["missingNodeNames"] == missing
        for name in reached[:-1]:
            assert diagnostic["outputCounts"][name] == [1]
        assert diagnostic["lastNodeExecuted"] == "Stage Started?"
        assert diagnostic["lastItemProducingNode"] == "Stage Started?"
        assert diagnostic["outputCounts"]["Stage Started?"] == [0, 1]
        for name in missing:
            assert diagnostic["outputCounts"][name] is None
        raise AssertionError(
            "native n8n behavioral RED (tooling and isolation validated): "
            + json.dumps(diagnostic, sort_keys=True)
        )

    assert diagnostic["executedNodeNames"] == expected_boundaries
    assert diagnostic["missingNodeNames"] == []
    for name in expected_boundaries:
        expected_count = [1, 0] if name == "Stage Started?" else [1]
        assert diagnostic["outputCounts"][name] == expected_count
    assert diagnostic["lastNodeExecuted"] == "Finalize Boundary"
    assert diagnostic["lastItemProducingNode"] == "Finalize Boundary"
    assert diagnostic["finalItemCount"] == 1
    assert diagnostic["runTokenMatches"] is True
    assert diagnostic["inputHashMatches"] is True


def test_wf09_success_path_reaches_fenced_finalization():
    data = workflow("09-render-video.json")
    edges = workflow_edges(data)
    expected_build_response_connection = {
        "main": [[{"node": "Finalize Stage", "type": "main", "index": 0}]]
    }

    assert data["connections"].get("Build Response") == expected_build_response_connection
    assert path_exists(edges, "Build Response", "Return Stage Result")
    assert "Return Stage Result" in edges["Finalize Stage"]


def test_wf09_cached_path_cannot_reach_renderer_or_finalization():
    edges = workflow_edges(workflow("09-render-video.json"))

    for target in ("Execute FFmpeg", "Finalize Stage", "Mark Completed"):
        assert not path_exists(edges, "Return Cached Stage", target)


def test_wf09_preserves_pre_cutover_normalization_compatibility():
    backup = json.loads(WF09_BACKUP.read_text(encoding="utf-8"))
    legacy_normalize = node_map(backup)["Normalize Stage Context"]["parameters"]["jsCode"]
    normalize = node_map(workflow("09-render-video.json"))["Normalize Stage Context"][
        "parameters"
    ]["jsCode"]
    legacy_input = {
        "body": {
            "id": "22222222-2222-4222-8222-222222222222",
            "pipeline_revision": "12",
            "currentRevision": 15,
            "itemKey": "legacy-job",
        }
    }

    previous = execute_code_node(legacy_normalize, legacy_input)[0]["json"]
    current = execute_code_node(normalize, legacy_input)[0]["json"]

    for key in (
        "jobId",
        "workerId",
        "leaseToken",
        "attemptNumber",
        "pipelineRevision",
        "stage",
        "itemKey",
    ):
        assert current[key] == previous[key]
    assert current["stageHashInput"] == previous["inputHash"]
    assert "inputHash" not in current


def test_wf09_is_pre_cutover_workflow_plus_only_approved_hashing_changes():
    backup = json.loads(WF09_BACKUP.read_text(encoding="utf-8"))
    pre_item_lineage_backup = json.loads(
        WF09_PRE_ITEM_LINEAGE_BACKUP.read_text(encoding="utf-8")
    )
    current = workflow("09-render-video.json")
    backup_nodes = node_map(backup)
    current_nodes = node_map(current)

    assert set(current_nodes) == set(backup_nodes) | {"Hash Stage Input"}
    for name, node in backup_nodes.items():
        if name not in {"Normalize Stage Context", "Merge Stage Context", "Stage Started?"}:
            assert current_nodes[name] == node, f"unexpected WF09 node drift: {name}"

    expected_stage_started = copy.deepcopy(
        node_map(pre_item_lineage_backup)["Stage Started?"]
    )
    expected_stage_started["parameters"] = {
        "conditions": {
            "options": {
                "caseSensitive": True,
                "leftValue": "",
                "typeValidation": "strict",
                "version": 1,
            },
            "conditions": [
                {
                    "leftValue": "={{ $json.stageState === 'STARTED' }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "equals"},
                }
            ],
            "combinator": "and",
        },
        "options": {},
    }
    assert current_nodes["Stage Started?"] == expected_stage_started

    approved_connection_changes = {
        "Normalize Stage Context",
        "Hash Stage Input",
        "Workflow Trigger",
        "Build Response",
    }
    backup_connections = {
        name: value
        for name, value in backup["connections"].items()
        if name not in approved_connection_changes
    }
    current_connections = {
        name: value
        for name, value in current["connections"].items()
        if name not in approved_connection_changes
    }
    assert current_connections == backup_connections
    assert current["settings"] == backup["settings"]
    assert "staticData" in current
    assert current["staticData"] == backup["staticData"]
    assert current["pinData"] == backup["pinData"]


def test_stage_workflows_hash_canonical_input_with_the_trusted_crypto_node():
    expected_parameters = {
        "action": "hash",
        "binaryData": False,
        "type": "SHA256",
        "value": "={{ $json.stageHashInput }}",
        "dataPropertyName": "inputHash",
        "encoding": "hex",
    }

    for filename in STAGE_WORKFLOWS:
        data = workflow(filename)
        hash_nodes = [node for node in data["nodes"] if node["name"] == "Hash Stage Input"]
        assert len(hash_nodes) == 1, f"{filename} must have one top-level Hash Stage Input node"
        hash_node = hash_nodes[0]
        assert hash_node["type"] == "n8n-nodes-base.crypto"
        assert hash_node["typeVersion"] == 2
        assert hash_node["parameters"] == expected_parameters
        assert "credentials" not in hash_node
        assert "continueOnFail" not in hash_node
        assert "onError" not in hash_node


def test_stage_workflows_hash_between_normalization_and_begin_stage():
    for filename in STAGE_WORKFLOWS:
        connections = workflow(filename)["connections"]
        assert connections["Normalize Stage Context"]["main"] == [
            [{"node": "Hash Stage Input", "type": "main", "index": 0}]
        ]
        assert connections["Hash Stage Input"]["main"] == [
            [{"node": "Begin Stage", "type": "main", "index": 0}]
        ]


def test_stage_merges_preserve_hash_and_remove_temporary_hash_input():
    for filename in STAGE_WORKFLOWS:
        merge = node_map(workflow(filename))["Merge Stage Context"]["parameters"]["jsCode"]
        assert "const {stageHashInput, ...context} = $('Hash Stage Input').first().json;" in merge
        assert "$('Normalize Stage Context')" not in merge
        assert "{...context," in merge


def test_stage_hash_canonical_format_has_a_fixed_compatible_digest():
    normalize = node_map(workflow("04-generate-script-and-scenes.json"))[
        "Normalize Stage Context"
    ]["parameters"]["jsCode"]
    items = execute_code_node(
        normalize,
        {
            "jobId": "11111111-1111-4111-8111-111111111111",
            "workerId": "worker-1",
            "leaseToken": "lease-1",
            "attemptNumber": 1,
            "pipelineRevision": 1,
            "currentRevision": 1,
        },
    )
    output = items[0]["json"]

    assert "stageHashInput" in output
    assert hashlib.sha256(output["stageHashInput"].encode("utf-8")).hexdigest() == (
        "d10d537471f2b7711d4b537e073982adb05d8e0c7be176995d1b729b549d42f0"
    )


def test_wf04_provider_free_probe_exercises_live_trusted_hash_contract():
    source = (ROOT / "clipcraft" / "scripts" / "controlled_wf04_run_token_no_provider_probe.js").read_text(
        encoding="utf-8"
    )

    assert "node.name === 'Hash Stage Input'" in source
    assert "resolve(__dirname, '..', 'workflows', '04-generate-script-and-scenes.json')" in source
    assert "stableStringify(liveNode) !== stableStringify(desiredNode)" in source
    assert "activeVersion" not in source
    for node in ("normalize", "hash", "merge"):
        assert f"...{node}," in source
    assert "new Set(['n8n-nodes-base.webhook', 'n8n-nodes-base.code', 'n8n-nodes-base.crypto'])" in source
    assert "node.credentials" in source
    desired_nodes = node_map(workflow("04-generate-script-and-scenes.json"))
    code_sources = {
        "Normalize Stage Context": desired_nodes["Normalize Stage Context"]["parameters"]["jsCode"],
        "Merge Stage Context": desired_nodes["Merge Stage Context"]["parameters"]["jsCode"],
        "Unwrap Probe Input": "const input = $json.body ?? $json; return [{json: input}];",
        "Begin Stage": "const input = $json; return [{json: {state: 'STARTED', stage_run_id: '44444444-4444-4444-8444-444444444444', run_token: '33333333-3333-4333-8333-333333333333', output: null}}];",
        "Generate Script Token Stop": "const input = $json; const runTokenPresent = typeof input.runToken === 'string'; const runTokenMatches = input.runToken === '33333333-3333-4333-8333-333333333333'; const inputHashMatches = input.inputHash === 'd10d537471f2b7711d4b537e073982adb05d8e0c7be176995d1b729b549d42f0'; const stageHashInputAbsent = !Object.prototype.hasOwnProperty.call(input, 'stageHashInput'); const providerCalls = 0; if (!runTokenPresent) throw new Error('RUN_TOKEN_REQUIRED'); if (!runTokenMatches || !inputHashMatches || !stageHashInputAbsent || providerCalls !== 0) throw new Error('PROBE_CONTRACT_FAILED'); return [{json: {probeStopped: true, runTokenPresent, runTokenMatches, inputHash: input.inputHash, inputHashMatches, stageHashInputAbsent, jobId: input.jobId, providerCalls: 0}}];",
    }
    expected_code_pins = {
        name: hashlib.sha256(js_code.encode("utf-8")).hexdigest()
        for name, js_code in code_sources.items()
    }
    missing_pins = {
        name: digest for name, digest in expected_code_pins.items() if digest not in source
    }
    assert not missing_pins, f"missing Code SHA pins: {missing_pins}"
    assert "createHash('sha256')" in source
    assert "codeNodes.length !== expectedCodePins.size" in source
    assert "suspiciousCode" not in source
    assert "validateProbeSafety(workflow)" in source
    create_workflow = source.index("api('/api/v1/workflows', { method: 'POST'")
    assert source.index("assertNodeIdentity('Merge Stage Context'") < create_workflow
    assert source.index("validateProbeSafety(workflow)") < create_workflow
    assert "'Normalize Stage Context': { main: [[{ node: 'Hash Stage Input'" in source
    assert "'Hash Stage Input': { main: [[{ node: 'Begin Stage'" in source
    assert "d10d537471f2b7711d4b537e073982adb05d8e0c7be176995d1b729b549d42f0" in source
    assert "stageHashInputAbsent" in source
    assert "providerCalls: 0" in source
    assert "new AbortController()" in source
    assert "setTimeout" in source and "clearTimeout" in source
    assert source.count("fetch(") == 1
    fetch_helper = source[source.index("async function fetchWithTimeout"):source.index("async function api")]
    assert "await response.text()" in fetch_helper
    assert "primaryError" in source and "cleanupErrors" in source
    assert "cleanupErrors.push(`deactivate:" in source
    assert "cleanupErrors.push(`delete:" in source
    assert "execFileSync('docker'" in source and "timeout:" in source.split("execFileSync('docker'", 1)[1].split(");", 1)[0]
    assert "probeName" in source
    assert "listWorkflowsByExactName" in source
    assert "workflow.name === probeName" in source
    assert "recoveryAttempts" in source
    assert "recovered workflow" in source
    assert "[404]" in source
    assert "temporary workflow still exists" in source
    status_check = source.index("if (response.status !== 200)")
    json_parse = source.index("JSON.parse(text)", status_check)
    assert status_check < json_parse
    assert "Webhook returned HTTP ${response.status}: ${text}" in source


def test_wf04_ledger_state_probe_pins_desired_route_chain():
    source = (
        ROOT
        / "clipcraft"
        / "scripts"
        / "controlled_wf04_ledger_state_no_provider_probe.js"
    ).read_text(encoding="utf-8")

    assert "Phase 7 Checkpoint 1S" in source
    assert "resolve(__dirname, '..', 'workflows', '04-generate-script-and-scenes.json')" in source
    assert "api('/api/v1/workflows/dWTF2UGXX3R73PDW')" in source
    assert "stageStarted = liveNodes('Stage Started?')" in source
    assert "routeCached = liveNodes('Route Cached?')" in source
    assert "routeRunning = liveNodes('Route Running?')" in source
    assert "validateProbeSafety(workflow)" in source
    assert "n8n-nodes-base.if" in source
    assert "providerCalls" in source
    assert "stoppedAtProvider" in source
    for state in (
        "'STARTED'",
        "'CACHED_SUCCESS'",
        "'RUNNING'",
        "'FAILED'",
        "'INPUT_HASH_MISMATCH'",
        "'INVALID_ITEM_KEY'",
        "'UNKNOWN_OUTCOME'",
        "'NOT_A_STATE'",
    ):
        assert state in source
    assert "failClosed" in source
    assert "WF04_LEDGER_STATE_UNSUPPORTED" in source or "WF04_LEDGER_STATE_UNSUPPORTED" in source
    assert "must fail closed, got ${response.status}" in source

    # The probe must pin the live/desired stage-lane jsCode so that a runtime drift is detected.
    desired = workflow("04-generate-script-and-scenes.json")
    desired_nodes = node_map(desired)
    code_sources = {
        "Normalize Stage Context": desired_nodes["Normalize Stage Context"]["parameters"]["jsCode"],
        "Merge Stage Context": desired_nodes["Merge Stage Context"]["parameters"]["jsCode"],
        "Return Cached Stage": desired_nodes["Return Cached Stage"]["parameters"]["jsCode"],
        "Return Already Running": desired_nodes["Return Already Running"]["parameters"]["jsCode"],
        "Return Stage Failure": desired_nodes["Return Stage Failure"]["parameters"]["jsCode"],
    }
    for name, js_code in code_sources.items():
        digest = hashlib.sha256(js_code.encode("utf-8")).hexdigest()
        assert digest in source, f"missing SHA pin for {name}: {digest}"
    assert "new Set(['n8n-nodes-base.webhook', 'n8n-nodes-base.code', 'n8n-nodes-base.crypto', 'n8n-nodes-base.if'])" in source
    assert "execFileSync('docker'" in source


def test_wf04_ledger_route_if_nodes_use_equals_boolean_operator():
    """n8n's boolean filter switch only matches 'equals'/'notEquals'/'true'/'false';
    the operation 'equal' falls through to 'Unknown filter parameter operator' => always false.
    All WF04 stage-lane routing IF nodes must use 'equals' so the ledgers route correctly."""
    wf = workflow("04-generate-script-and-scenes.json")
    route_if_nodes = [
        "Stage Started?",
        "Route Cached?",
        "Route Running?",
    ]
    routed = 0
    for name in route_if_nodes:
        node = node_map(wf).get(name)
        if node is None:
            continue
        routed += 1
        assert node["type"] == "n8n-nodes-base.if"
        conds = node["parameters"]["conditions"]["conditions"]
        assert len(conds) == 1
        op = conds[0]["operator"]
        assert op["type"] == "boolean"
        assert op["operation"] == "equals", f"{name} uses '{op['operation']}' which never routes true in n8n"
    assert routed == 3
    # The new-style stage-routing IF nodes (with conditions list) must not regress to the broken 'equal'.
    for node in node_map(wf).values():
        if node.get("type") != "n8n-nodes-base.if":
            continue
        params = node.get("parameters") or {}
        conds = (params.get("conditions") or {}).get("conditions")
        if not isinstance(conds, list):
            continue  # legacy boolean[]-style IF nodes are out of scope for this check
        for cond in conds:
            if cond["operator"]["type"] == "boolean":
                assert cond["operator"]["operation"] != "equal"


def test_wf09_provider_free_probe_covers_gate_a_without_external_nodes():
    source = (ROOT / "clipcraft" / "scripts" / "controlled_wf09_graph_no_provider_probe.js").read_text(
        encoding="utf-8"
    )
    contract = load_wf09_gate_a_contract()
    assert "resolve(__dirname, '..', 'workflows', '09-render-video.json')" in source
    assert "api('/api/v1/workflows/gqX0rJ1gqzHCNDso')" in source
    assert "const LIVE_WORKFLOW_ID = 'gqX0rJ1gqzHCNDso'" in source
    assert "const LIVE_WORKFLOW_NAME = 'Render AI Video'" in source
    assert "live.active !== true" in source
    assert "projectWritableNode" in source
    assert "WRITABLE_NODE_KEYS" in source
    assert "'outputs'" not in source[source.index("const WRITABLE_NODE_KEYS"):source.index("];", source.index("const WRITABLE_NODE_KEYS"))]
    assert "projectExecutableWorkflow(live)" in source
    assert "projectExecutableWorkflow(local)" in source
    assert "nodes: workflow.nodes.map(projectWritableNode)" in source
    assert "connections: workflow.connections" in source
    assert "settings: workflow.settings" in source
    assert "staticData: workflow.staticData ?? null" in source
    assert "Live WF09 executable graph differs from the local workflow definition" in source
    for node in ("normalize", "hash", "mergeStage", "stageStarted", "mergeAttempt", "mergeHeartbeat"):
        assert f"...{node}," in source

    expected_node_types = {
        "Workflow Trigger": "n8n-nodes-base.webhook",
        "Unwrap Probe Input": "n8n-nodes-base.code",
        "Normalize Stage Context": "n8n-nodes-base.code",
        "Hash Stage Input": "n8n-nodes-base.crypto",
        "Stub Begin Stage": "n8n-nodes-base.code",
        "Merge Stage Context": "n8n-nodes-base.code",
        "Stage Started?": "n8n-nodes-base.if",
        "Stub Reserve External Attempt": "n8n-nodes-base.code",
        "Merge Attempt Context": "n8n-nodes-base.code",
        "Stub Heartbeat Stage Lease": "n8n-nodes-base.code",
        "Merge Heartbeat Context": "n8n-nodes-base.code",
        "Stub Render Output": "n8n-nodes-base.code",
        "Stub Build Response": "n8n-nodes-base.code",
        "Finalize Boundary": "n8n-nodes-base.code",
    }
    node_type_block = source[
        source.index("const EXPECTED_NODE_TYPES = new Map(["):
        source.index("]);", source.index("const EXPECTED_NODE_TYPES = new Map(["))
    ]
    actual_node_types = dict(re.findall(r"\['([^']+)', '([^']+)'\]", node_type_block))
    assert actual_node_types == expected_node_types

    code_sources = {
        "Normalize Stage Context": node_map(workflow("09-render-video.json"))["Normalize Stage Context"]["parameters"]["jsCode"],
        "Merge Stage Context": node_map(workflow("09-render-video.json"))["Merge Stage Context"]["parameters"]["jsCode"],
        "Merge Attempt Context": node_map(workflow("09-render-video.json"))["Merge Attempt Context"]["parameters"]["jsCode"],
        "Merge Heartbeat Context": node_map(workflow("09-render-video.json"))["Merge Heartbeat Context"]["parameters"]["jsCode"],
        "Unwrap Probe Input": contract["UNWRAP_CODE"],
        "Stub Begin Stage": contract["BEGIN_CODE"],
        "Stub Reserve External Attempt": contract["RESERVE_CODE"],
        "Stub Heartbeat Stage Lease": contract["HEARTBEAT_CODE"],
        "Stub Render Output": contract["RENDER_CODE"],
        "Stub Build Response": contract["BUILD_RESPONSE_CODE"],
        "Finalize Boundary": contract["FINALIZE_CODE"],
    }
    expected_pins = {
        name: hashlib.sha256(js_code.encode("utf-8")).hexdigest()
        for name, js_code in code_sources.items()
    }
    pin_block = source[source.index("const expectedCodePins = new Map(["):source.index("]);", source.index("const expectedCodePins = new Map(["))]
    actual_pins = dict(re.findall(r"\['([^']+)', '([0-9a-f]{64})'\]", pin_block))
    assert actual_pins == expected_pins

    assert "workflow.nodes.length !== EXPECTED_NODE_TYPES.size" in source
    assert "actualNames.size !== EXPECTED_NODE_TYPES.size" in source
    assert "EXPECTED_NODE_TYPES.get(node.name) !== node.type" in source
    assert "stableStringify(workflow.connections) !== stableStringify(EXPECTED_CONNECTIONS)" in source
    assert "node.credentials != null" in source
    assert "Object.prototype.hasOwnProperty.call(node, 'credentials')" in source
    assert "stableStringify(node).includes('$env')" in source
    assert "codeNodes.length !== expectedCodePins.size" in source
    assert "stableStringify(hashNode.parameters) !== stableStringify(EXPECTED_HASH_PARAMETERS)" in source
    assert "validateProbeSafety(workflow)" in source
    assert "n8n-nodes-base.httpRequest" not in source
    assert "n8n-nodes-base.executeWorkflow" not in source
    assert "externalCallCapableNodes.length" in source
    assert "rendererNodes.length" in source
    assert "return { providerCalls: 0, rendererInvocations: 0 }" in source

    expected_connections = {
        "Workflow Trigger": {"main": [[{"node": "Unwrap Probe Input", "type": "main", "index": 0}]]},
        "Unwrap Probe Input": {"main": [[{"node": "Normalize Stage Context", "type": "main", "index": 0}]]},
        "Normalize Stage Context": {"main": [[{"node": "Hash Stage Input", "type": "main", "index": 0}]]},
        "Hash Stage Input": {"main": [[{"node": "Stub Begin Stage", "type": "main", "index": 0}]]},
        "Stub Begin Stage": {"main": [[{"node": "Merge Stage Context", "type": "main", "index": 0}]]},
        "Merge Stage Context": {"main": [[{"node": "Stage Started?", "type": "main", "index": 0}]]},
        "Stage Started?": {"main": [[{"node": "Stub Reserve External Attempt", "type": "main", "index": 0}], []]},
        "Stub Reserve External Attempt": {"main": [[{"node": "Merge Attempt Context", "type": "main", "index": 0}]]},
        "Merge Attempt Context": {"main": [[{"node": "Stub Heartbeat Stage Lease", "type": "main", "index": 0}]]},
        "Stub Heartbeat Stage Lease": {"main": [[{"node": "Merge Heartbeat Context", "type": "main", "index": 0}]]},
        "Merge Heartbeat Context": {"main": [[{"node": "Stub Render Output", "type": "main", "index": 0}]]},
        "Stub Render Output": {"main": [[{"node": "Stub Build Response", "type": "main", "index": 0}]]},
        "Stub Build Response": {"main": [[{"node": "Finalize Boundary", "type": "main", "index": 0}]]},
    }
    connections_match = re.search(r"const EXPECTED_CONNECTIONS = JSON\.parse\('([^\n]+)'\);", source)
    assert connections_match
    assert json.loads(connections_match.group(1)) == expected_connections

    assert "runTokenMatches" in contract["FINALIZE_CODE"]
    assert "inputHashMatches" in contract["FINALIZE_CODE"]
    assert "$input.all()" in contract["FINALIZE_CODE"]
    assert "items.length !== 1" in contract["FINALIZE_CODE"]
    assert "finalizationBoundaryReached: true" in contract["FINALIZE_CODE"]
    shared_code = "\n".join(contract[name] for name in (
        "UNWRAP_CODE", "BEGIN_CODE", "RESERVE_CODE", "HEARTBEAT_CODE",
        "RENDER_CODE", "BUILD_RESPONSE_CODE", "FINALIZE_CODE",
    ))
    assert "providerCalls" not in shared_code
    assert "rendererInvocations" not in shared_code
    assert "finalizationCount" not in shared_code
    assert "finalizationCount: result.finalizationBoundaryReached ? 1 : 0" in source
    assert "...structuralSafety" in source
    assert "new AbortController()" in source
    assert "await response.text()" in source
    assert source.count("fetch(") == 1
    assert "const CREATE_TIMEOUT_MS = 30_000;" in source
    assert "const UNKNOWN_CREATE_RECOVERY_ATTEMPTS = 60;" in source
    assert "const UNKNOWN_CREATE_RECOVERY_DELAY_MS = 2_000;" in source
    assert "timeoutMs = fetchTimeoutMs" in source
    create_call = source[source.index("api('/api/v1/workflows', { method: 'POST'"):]
    create_call = create_call[:create_call.index(");") + 2]
    assert "CREATE_TIMEOUT_MS" in create_call
    assert "primaryError" in source and "cleanupErrors" in source
    assert "listWorkflowsByExactName" in source
    assert "workflow.name === probeName" in source
    assert re.search(r"const recoveryAttempts = (?:1[0-9]|[2-9][0-9]+);", source)
    assert re.search(r"const recoveryDelayMs = (?:1000|[1-9][0-9]{3,});", source)
    assert "knownWorkflowIds.add" in source
    assert "listRunningExecutionsForWorkflowIds" in source
    assert "waitForNoRunningExecutions" in source
    assert "status: 'running'" in source
    assert "execution.workflowId ?? execution.workflowData?.id" in source
    assert "before deletion" in source
    assert "after deletion" in source
    assert "running executions remain" in source
    assert "pollExactNameAbsence" in source
    assert "pollExactNameAbsence(probeName, knownWorkflowIds, deletedWorkflowIds, cleanupErrors, UNKNOWN_CREATE_RECOVERY_ATTEMPTS, UNKNOWN_CREATE_RECOVERY_DELAY_MS)" in source
    assert "if (id)" in source
    assert "else" in source[source.index("if (id)"):source.index("if (primaryError")]
    assert "verify deletion" in source.lower()
    assert "[404]" in source
    assert "DELETE /api/v1/executions" not in source

    create_workflow = source.index("api('/api/v1/workflows', { method: 'POST'")
    assert source.index("assertLiveWorkflowIdentity(live, local)") < source.index("const workflow = {")
    assert source.index("validateProbeSafety(workflow)") < create_workflow
    status_check = source.index("if (response.status !== 200)")
    assert status_check < source.index("JSON.parse(text)", status_check)


def test_wf09_gate_a_failure_summary_is_useful_and_sanitized():
    source = (ROOT / "clipcraft" / "scripts" / "controlled_wf09_graph_no_provider_probe.js").read_text(
        encoding="utf-8"
    )
    helper_start = source.index("function safeGateSummary(report)")
    helper_end = source.index("\n}\n\n", helper_start) + 2
    helper_source = source[helper_start:helper_end]
    report = {
        "gateA": False,
        "finalizationBoundaryReached": True,
        "runTokenMatches": False,
        "inputHashMatches": True,
        "finalizationCount": 0,
        "providerCalls": 0,
        "rendererInvocations": 0,
        "jobId": "sensitive-job-id",
        "runToken": "sensitive-run-token",
        "inputHash": "sensitive-input-hash",
        "credentials": {"apiKey": "sensitive-credential"},
        "payload": {"secret": "sensitive-payload"},
        "videoUrl": "https://sensitive.example/video.mp4",
        "thumbnailUrl": "https://sensitive.example/thumb.jpg",
        "stack": "sensitive-stack-body",
        "body": "sensitive-response-body",
    }
    runner = """
const code = Buffer.from(process.argv[1], 'base64').toString('utf8');
const report = JSON.parse(Buffer.from(process.argv[2], 'base64').toString('utf8'));
const summarize = new Function(`${code}; return safeGateSummary;`)();
process.stdout.write(JSON.stringify(summarize(report)));
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            runner,
            base64.b64encode(helper_source.encode("utf-8")).decode("ascii"),
            base64.b64encode(json.dumps(report).encode("utf-8")).decode("ascii"),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    summary = json.loads(completed.stdout)

    assert summary == {
        "gateA": False,
        "finalizationBoundaryReached": True,
        "runTokenMatches": False,
        "inputHashMatches": True,
        "finalizationCount": 0,
        "providerCalls": 0,
        "rendererInvocations": 0,
    }
    serialized = json.dumps(summary, sort_keys=True)
    for forbidden_key in (
        "jobId", "runToken", "inputHash", "credentials", "payload", "videoUrl",
        "thumbnailUrl", "stack", "body",
    ):
        assert forbidden_key not in summary
    for forbidden_value in ("sensitive-", "https://"):
        assert forbidden_value not in serialized
    assert (
        "Provider-free WF09 probe did not satisfy Gate A: "
        "${JSON.stringify(safeGateSummary(report))}"
    ) in source


def test_stage_hashing_deployment_scripts_are_safe_and_exact():
    scripts = ROOT / "clipcraft" / "scripts"
    backup_path = scripts / "backup_stage_hashing_1o.js"
    import_path = scripts / "import_stage_hashing_1o.js"
    assert backup_path.is_file()
    assert import_path.is_file()

    backup = backup_path.read_text(encoding="utf-8")
    importer = import_path.read_text(encoding="utf-8")
    expected = {
        "05-generate-scene-images.json": ("gazJuTcoSGqYdGze", "Generate Scene Images", "wf05"),
        "06-generate-narration.json": ("UhWkv3GLHVSpWrMe", "Generate Narration", "wf06"),
        "07-build-captions.json": ("dNgYGCqkbwr552EW", "Build Captions", "wf07"),
        "08-build-render-manifest.json": ("iik8qVHvgD9xWWjI", "Build Render Manifest", "wf08"),
        "09-render-video.json": ("gqX0rJ1gqzHCNDso", "Render AI Video", "wf09"),
    }
    expected_mapping = "\n".join([
        "const WORKFLOWS = [",
        *[
            f"  {{ file: '{filename}', id: '{workflow_id}', name: '{name}', prefix: '{prefix}' }},"
            for filename, (workflow_id, name, prefix) in expected.items()
        ],
        "];",
    ])

    for source in (backup, importer):
        assert "resolve(__dirname, '..'" in source
        assert "execFileSync('docker'" in source
        docker_call = source.split("execFileSync('docker'", 1)[1].split(");", 1)[0]
        assert "timeout: 10_000" in docker_call
        assert "AbortSignal.timeout(10_000)" in source
        assert "console.log(apiKey" not in source
        assert "console.error(apiKey" not in source
        assert "N8N_API_KEY=${" not in source
        mapping_start = source.index("const WORKFLOWS = [")
        mapping_end = source.index("];", mapping_start) + 2
        assert source[mapping_start:mapping_end] == expected_mapping
        assert "04-generate-script-and-scenes.json" not in source

    assert "resolve(__dirname, '..', 'backups', 'phase-7-cutover')" in backup
    assert "stage-hashing-${stamp}.json" in backup
    assert "await Promise.all(WORKFLOWS.map" in backup
    assert backup.index("await Promise.all(WORKFLOWS.map") < backup.index("mkdirSync")
    assert "JSON.stringify(live, null, 2)" in backup
    assert "const destinations = liveWorkflows.map" in backup
    destinations = backup.index("const destinations = liveWorkflows.map")
    mkdir = backup.index("mkdirSync")
    existence_gate = backup.index("fs.existsSync(output)")
    first_write = backup.index("fs.writeFileSync")
    assert destinations < mkdir < existence_gate < first_write
    assert "const createdPaths = []" in backup
    assert "createdPaths.push(output)" in backup
    assert "fs.openSync(output, 'wx', 0o600)" in backup
    assert "for (const createdPath of createdPaths.reverse())" in backup
    assert "fs.unlinkSync(createdPath)" in backup
    assert "throw error" in backup
    for line in backup.splitlines():
        if "console." in line:
            assert "apiKey" not in line and "N8N_API_KEY" not in line
    assert "await Promise.all(WORKFLOWS.map" in importer
    preflight = importer.index("await Promise.all(WORKFLOWS.map")
    first_put = importer.index("method: 'PUT'")
    assert preflight < importer.index("assertBackupSet") < first_put
    assert preflight < importer.index("validateDesiredWorkflow") < first_put
    assert "const selectedBackups = assertBackupSet()" in importer
    assert "const stamps = [...new Set" in importer
    assert ".sort().reverse()" in importer
    assert "for (const stamp of stamps)" in importer
    assert "`${entry.prefix}-stage-hashing-${stamp}.json`" in importer
    assert "selected.length === WORKFLOWS.length" in importer
    assert "return selected" in importer
    assert "JSON.parse(fs.readFileSync(backupPath, 'utf8'))" in importer
    assert "catch" in importer
    assert "backup.id === entry.id" in importer
    assert "backup.name === entry.name" in importer
    assert "Array.isArray(backup.nodes)" in importer
    assert "backup.connections && typeof backup.connections === 'object'" in importer
    assert "!Array.isArray(backup.connections)" in importer
    assert "path: backupPath" in importer
    assert "deepEqual(selected.backup, liveById.get(selected.entry.id)" in importer
    selected_compare = importer.index("deepEqual(selected.backup, liveById.get(selected.entry.id)")
    assert preflight < selected_compare < first_put
    assert "wf.active !== true" in importer
    assert "Hash Stage Input" in importer
    assert "n8n-nodes-base.crypto" in importer
    assert "typeVersion !== 2" in importer
    for key, value in {
        "action": "hash",
        "binaryData": "false",
        "type": "SHA256",
        "value": "={{ $json.stageHashInput }}",
        "dataPropertyName": "inputHash",
        "encoding": "hex",
    }.items():
        assert key in importer and value in importer
    assert "Normalize Stage Context" in importer
    assert "Begin Stage" in importer
    assert "Merge Stage Context" in importer
    assert "$('Hash Stage Input').first().json" in importer
    assert "stageHashInput" in importer
    assert "Object.keys(payload)" in importer
    assert "['connections', 'name', 'nodes', 'settings', 'staticData']" in importer
    assert "name: before.name" in importer
    assert "connections: desired.connections" in importer
    writable_nodes = [
        "id",
        "name",
        "webhookId",
        "disabled",
        "notesInFlow",
        "notes",
        "type",
        "typeVersion",
        "executeOnce",
        "alwaysOutputData",
        "retryOnFail",
        "maxTries",
        "waitBetweenTries",
        "continueOnFail",
        "onError",
        "position",
        "parameters",
        "credentials",
        "customTelemetryTags",
    ]
    node_allowlist_start = importer.index("const WRITABLE_NODE_KEYS = [")
    node_allowlist_end = importer.index("];", node_allowlist_start) + 2
    node_allowlist = importer[node_allowlist_start:node_allowlist_end]
    for key in writable_nodes:
        assert f"'{key}'" in node_allowlist
    assert "'outputs'" not in node_allowlist
    assert "function projectWritableNode(node)" in importer
    assert "Object.prototype.hasOwnProperty.call(node, key)" in importer
    assert "node[key] !== undefined" in importer
    assert "projected[key] = node[key]" in importer
    writable_settings = [
        "saveExecutionProgress",
        "saveManualExecutions",
        "saveDataErrorExecution",
        "saveDataSuccessExecution",
        "executionTimeout",
        "errorWorkflow",
        "timezone",
        "executionOrder",
        "callerPolicy",
        "callerIds",
        "timeSavedPerExecution",
    ]
    allowlist_start = importer.index("const WRITABLE_SETTING_KEYS = [")
    allowlist_end = importer.index("];", allowlist_start) + 2
    allowlist = importer[allowlist_start:allowlist_end]
    for setting in writable_settings:
        assert f"'{setting}'" in allowlist
    assert "'executionOrder'" in allowlist and "'errorWorkflow'" in allowlist
    assert "binaryMode" not in allowlist
    assert "availableInMCP" not in allowlist
    assert "function projectWritableSettings(settings)" in importer
    assert "Object.prototype.hasOwnProperty.call(settings, key)" in importer
    assert "settings[key] !== undefined" in importer
    assert "projected[key] = settings[key]" in importer
    build_start = importer.index("function buildPayload(before, desired)")
    build_end = importer.index("function expectedUpdatedWorkflow", build_start)
    build_payload = importer[build_start:build_end]
    assert "nodes: desired.nodes.map(projectWritableNode)" in build_payload
    assert "settings: projectWritableSettings(before.settings)" in build_payload
    assert "settings: before.settings" not in build_payload
    expected_start = build_end
    expected_end = importer.index("function verifyWorkflow", expected_start)
    expected_workflow = importer[expected_start:expected_end]
    assert "nodes: desired.nodes.map(projectWritableNode)" in expected_workflow
    assert "settings: before.settings" in expected_workflow
    assert "settings: { executionOrder:" not in importer
    assert "staticData: before.staticData ?? null" in importer
    assert "staticData: desired.staticData ?? null" not in importer
    assert "method: 'POST'" in importer and "/activate" in importer
    assert "/deactivate" in importer
    assert "function buildPayload(before, desired)" in importer
    assert "function verifyWorkflow(entry, expected, actual" in importer
    assert "const attempted = []" in importer
    assert "const current = await api(`/api/v1/workflows/${entry.id}`)" in importer
    assert "deepEqual(current, selected.backup" in importer
    drift_fetch = importer.index("const current = await api(`/api/v1/workflows/${entry.id}`)")
    drift_compare = importer.index("deepEqual(current, selected.backup", drift_fetch)
    attempted = importer.index("attempted.push(attempt)", drift_compare)
    mutation = importer.index("method: 'PUT'", attempted)
    assert drift_fetch < drift_compare < attempted < mutation
    assert "await rollbackAttempted(attempted)" in importer
    assert "for (const attempt of [...attempted].reverse())" in importer
    assert "rollbackErrors.push" in importer
    assert "rollback errors:" in importer
    assert "await rollbackWorkflow(attempt.selected.entry, attempt.selected.backup, attempt.expected, attempt.uncertain)" in importer
    assert "const STABILIZATION_ATTEMPTS = 6" in importer
    assert "const STABILIZATION_DELAY_MS = 500" in importer
    assert "uncertain: false" in importer
    assert "attempt.uncertain = true" in importer
    assert "attempt.uncertain" in importer
    assert "function classifyWorkflowState(current, backup, expected)" in importer
    assert "async function observeRollbackState(entry, backup, expected, stabilize)" in importer
    assert "for (let attempt = 0; attempt < attempts; attempt += 1)" in importer
    assert "await delay(STABILIZATION_DELAY_MS)" in importer
    assert "const observed = await observeRollbackState(entry, backup, expected, uncertain)" in importer
    stabilized = importer.index("const observed = await observeRollbackState(entry, backup, expected, uncertain)")
    backup_noop = importer.index("observed.classification === 'backup'", stabilized)
    assert stabilized < backup_noop
    assert "buildPayload(backup, backup)" in importer
    assert "await reconcileActiveState(entry, backup.active" in importer
    assert "verifyWorkflow(entry, backup, restored, 'rollback')" in importer
    assert "function workflowMutationState(workflow)" in importer
    assert "const currentState = workflowMutationState(current)" in importer
    assert "const backupState = workflowMutationState(backup)" in importer
    assert "const desiredState = workflowMutationState(expected)" in importer
    already_backup = importer.index("stableStringify(currentState) === stableStringify(backupState)")
    concurrent_drift = importer.index("stableStringify(currentState) !== stableStringify(desiredState)")
    rollback_put = importer.index("method: 'PUT'", backup_noop)
    assert already_backup < concurrent_drift
    assert backup_noop < rollback_put
    assert "concurrent drift; rollback skipped" in importer
    assert "deepEqual(actual.settings, expected.settings" in importer
    assert "deepEqual(actual.staticData ?? null, expected.staticData ?? null" in importer
    assert "actual.nodes.length !== expected.nodes.length" in importer
    assert "projectExecutable(expected)" in importer
    assert "projectExecutable(actual)" in importer
    assert "activeVersion" not in importer
    assert "const text = await response.text()" in importer
    assert "typeof parsed.message === 'string'" in importer
    assert "parsed.message.slice(0, 300)" in importer
    assert "${text}" not in importer
    exact_merge_code = (
        "const {stageHashInput, ...context} = $('Hash Stage Input').first().json;\n"
        "const result = $json;\n"
        "return [{json: {...context, stageState: result.state, stageRunId: result.stage_run_id, "
        "runToken: result.run_token, cachedOutput: result.output}}];"
    )
    assert json.dumps(exact_merge_code) in importer
    assert "mergeCode !== expectedMergeCode" in importer
    for line in importer.splitlines():
        if "console." in line:
            assert "apiKey" not in line and "N8N_API_KEY" not in line


def test_wf09_minimal_reconciler_is_offline_deterministic_and_shape_guarded():
    path = ROOT / "clipcraft" / "scripts" / "reconcile_wf09_minimal_1o.js"
    assert path.is_file()
    source = path.read_text(encoding="utf-8")

    assert "wf09-stage-hashing-20260804T132837Z.json" in source
    assert "09-render-video.json" in source
    assert "gqX0rJ1gqzHCNDso" in source
    assert "Render AI Video" in source
    assert "Normalize Stage Context" in source
    assert "Merge Stage Context" in source
    assert "Hash Stage Input" in source
    assert "Workflow Trigger" in source and "Validate Input" in source
    assert "writeFileSync(outputPath" in source
    assert "fetch(" not in source
    assert "execFile" not in source
    for forbidden in ("activeVersion", "activeVersionId", "shared", "versionCounter"):
        assert f"output.{forbidden}" not in source


def test_stage_hashing_importer_skips_wf05_wf08_and_selects_only_changed_wf09():
    importer = (
        ROOT / "clipcraft" / "scripts" / "import_stage_hashing_1o.js"
    ).read_text(encoding="utf-8")
    runner = r"""
const vm = require('vm');
let source = Buffer.from(process.argv[1], 'base64').toString('utf8');
source = source.replace(/\nmain\(\)\.catch\([\s\S]*$/, '\nmodule.exports = { isDesiredMutationStateUnchanged };');
const sandbox = {
  module: { exports: {} },
  exports: {},
  require(name) {
    if (name === 'child_process') {
      return { execFileSync: () => JSON.stringify([{ Config: { Env: ['N8N_API_KEY=test-only'] } }]) };
    }
    return require(name);
  },
  __dirname: process.cwd(),
  console,
  AbortSignal,
  fetch: () => { throw new Error('fetch must not be called'); },
};
vm.runInNewContext(source, sandbox);
const before = {
  id: 'wf05', name: 'Workflow', active: true,
  nodes: [{ id: 'node', name: 'Node', type: 'n8n-nodes-base.code', typeVersion: 2,
    position: [0, 0], parameters: { jsCode: 'same' }, outputs: 2 }],
  connections: {}, settings: { executionOrder: 'v1', availableInMCP: false }, staticData: null,
};
const unchangedDesired = {
  ...before,
  nodes: [{ id: 'node', name: 'Node', type: 'n8n-nodes-base.code', typeVersion: 2,
    position: [0, 0], parameters: { jsCode: 'same' } }],
};
const changedDesired = {
  ...unchangedDesired,
  nodes: [{ ...unchangedDesired.nodes[0], parameters: { jsCode: 'changed' } }],
};
const decide = sandbox.module.exports.isDesiredMutationStateUnchanged;
const decisions = ['wf05', 'wf06', 'wf07', 'wf08', 'wf09'].map((id) => {
  const live = { ...before, id };
  const desired = id === 'wf09' ? { ...changedDesired, id } : { ...unchangedDesired, id };
  return { id, skipped: decide(live, desired) };
});
process.stdout.write(JSON.stringify({
  decisions,
  putCandidates: decisions.filter(({ skipped }) => !skipped).map(({ id }) => id),
}));
"""
    completed = subprocess.run(
        ["node", "-e", runner, base64.b64encode(importer.encode("utf-8")).decode("ascii")],
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "decisions": [
            {"id": "wf05", "skipped": True},
            {"id": "wf06", "skipped": True},
            {"id": "wf07", "skipped": True},
            {"id": "wf08", "skipped": True},
            {"id": "wf09", "skipped": False},
        ],
        "putCandidates": ["wf09"],
    }
