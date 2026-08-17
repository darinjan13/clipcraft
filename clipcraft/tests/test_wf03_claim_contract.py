import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "clipcraft" / "workflows" / "03-video-job-worker.json"


def workflow():
    return json.loads(WORKFLOW.read_text(encoding="utf-8"))


def node(name):
    return next(item for item in workflow()["nodes"] if item["name"] == name)


def normalize_code():
    return node("Validate and Extract Claimed Job")["parameters"]["jsCode"]


def run_normalizer(response):
    script = """
const fs = require('fs');
const code = fs.readFileSync(0, 'utf8');
const fn = new Function('$input', code);
const result = fn({ first: () => ({ json: JSON.parse(process.env.WF03_RESPONSE) }) });
process.stdout.write(JSON.stringify(result));
"""
    env = {**os.environ, "WF03_RESPONSE": json.dumps(response)}
    return subprocess.run(
        ["node", "-e", script],
        input=normalize_code(),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def fenced_claim():
    return {
        "claimed": True,
        "lease_token": "11111111-1111-4111-8111-111111111111",
        "job": {
            "id": "22222222-2222-4222-8222-222222222222",
            "topic": "probe",
            "status": "generating_script",
            "current_step": "generating_script",
            "brief_json": {"duration": 30, "sceneCount": 6},
            "claimed_by": "clipcraft-n8n",
            "lease_expires_at": "2026-08-04T12:02:00.000Z",
            "attempt_number": 1,
            "pipeline_revision": 1,
            "next_stage": "generate_script",
            "last_completed_stage": None,
        },
    }


def test_direct_fenced_claim_normalizes_authoritative_fields_once():
    result = run_normalizer(fenced_claim())
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)[0]["json"]
    assert output["jobId"] == "22222222-2222-4222-8222-222222222222"
    assert output["leaseToken"] == "11111111-1111-4111-8111-111111111111"
    assert output["leaseExpiresAt"] == "2026-08-04T12:02:00.000Z"
    assert output["attemptNumber"] == 1
    assert output["pipelineRevision"] == 1
    assert output["claimedBy"] == "clipcraft-n8n"
    assert output["workerId"] == "clipcraft-n8n"
    assert output["nextStage"] == "generate_script"
    assert output["lastCompletedStage"] is None
    assert output["status"] == "generating_script"
    assert output["currentStep"] == "generating_script"


def test_one_element_array_and_nested_result_are_unwrapped():
    for response in ([fenced_claim()], {"result": fenced_claim()}):
        result = run_normalizer(response)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)[0]["json"]["leaseToken"] == "11111111-1111-4111-8111-111111111111"


def test_empty_claim_is_clean_no_work():
    result = run_normalizer({"claimed": False})
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_legacy_direct_row_is_rejected_without_synthetic_lease_context():
    row = fenced_claim()["job"]
    row.pop("lease_expires_at")
    row.pop("attempt_number")
    result = run_normalizer(row)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_multiple_rows_and_incomplete_fenced_claims_are_rejected():
    for response in ([fenced_claim(), fenced_claim()], {"claimed": True, "job": fenced_claim()["job"]}):
        result = run_normalizer(response)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == []


def test_invalid_uuid_timestamp_and_attempt_values_are_rejected():
    cases = [
        {**fenced_claim(), "lease_token": "not-a-uuid"},
        {**fenced_claim(), "job": {**fenced_claim()["job"], "lease_expires_at": "not-a-timestamp"}},
        {**fenced_claim(), "job": {**fenced_claim()["job"], "attempt_number": 0}},
        {**fenced_claim(), "job": {**fenced_claim()["job"], "pipeline_revision": 0}},
    ]
    for response in cases:
        result = run_normalizer(response)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == []


def test_wf03_has_one_fenced_claim_to_wf04_route_and_no_legacy_claim_url():
    data = workflow()
    text = json.dumps(data, sort_keys=True)
    claim = node("Claim Next Job")
    assert "claim_next_video_job_fenced" in claim["parameters"]["url"]
    assert "claim_next_video_job\" }}" not in text
    assert data["connections"]["Claim Next Job"]["main"][0][0]["node"] == "Validate and Extract Claimed Job"
    assert data["connections"]["Validate and Extract Claimed Job"]["main"][0][0]["node"] == "Route Claimed Stage"
    assert not any(
        link["node"] == "Extract Job Info"
        for links in data["connections"].values()
        for branch in links.get("main", [])
        for link in branch
    )


def test_wf03_routes_each_claimed_stage_to_the_matching_workflow():
    data = workflow()
    router = node("Route Claimed Stage")
    assert router["type"] == "n8n-nodes-base.switch"
    assert router["parameters"]["mode"] == "rules"
    routes = data["connections"]["Route Claimed Stage"]["main"]
    destinations = [branch[0]["node"] for branch in routes]
    assert destinations == [
        "Call Generate Script",
        "Update Progress Images",
        "Update Progress Narration",
        "Update Progress Captions",
        "Update Progress Manifest",
        "Update Progress Render",
    ]
    source = json.dumps(router["parameters"], sort_keys=True)
    for stage in ("generate_script", "generate_images", "generate_voice", "build_captions", "build_manifest", "render"):
        assert stage in source


def test_wf04_dispatch_preserves_canonical_lease_context_without_credentials():
    dispatch = node("Call Generate Script")
    assert dispatch["parameters"]["workflowId"]["value"] == "dWTF2UGXX3R73PDW"
    assert "SUPABASE_SERVICE_ROLE_KEY" not in json.dumps(dispatch)
    assert "leaseToken" in normalize_code()
    assert "attemptNumber" in normalize_code()
    assert "pipelineRevision" in normalize_code()


def test_all_call_execute_workflow_nodes_use_continue_regular_output_on_error():
    """Call Generate X nodes must set onError=continueRegularOutput so
    sub-workflow exceptions bubble as {error} regular output instead of
    aborting the parent execution (which stalls the job until STAGE_TIMEOUT)."""
    data = workflow()
    call_nodes = [
        n for n in data["nodes"]
        if n["type"] == "n8n-nodes-base.executeWorkflow"
        and n["name"].startswith("Call ")
    ]
    assert len(call_nodes) == 6, f"Expected 6 Call nodes, got {len(call_nodes)}"
    for n in call_nodes:
        assert n.get("onError") == "continueRegularOutput", (
            f"{n['name']} must have onError=continueRegularOutput, "
            f"got {n.get('onError', 'MISSING')}"
        )


def test_script_ok_is_if_node_routing_to_error_chain_on_false():
    """Script OK? must be an IF node (not a code node returning []),
    with true -> Update Progress Images and false -> Format Script Error."""
    n = node("Script OK?")
    assert n["type"] == "n8n-nodes-base.if", (
        f"Script OK? must be an IF node, got {n['type']}"
    )
    conns = workflow()["connections"]["Script OK?"]["main"]
    assert conns[0][0]["node"] == "Update Progress Images"
    assert conns[1][0]["node"] == "Format Script Error"


def test_all_stage_if_nodes_route_false_branch_to_format_error():
    """Every <Stage> OK? IF node must route its false branch [1] to the
    matching Format <Stage> Error node."""
    data = workflow()
    stages = ["Script", "Images", "Narration", "Captions", "Manifest", "Render"]
    for stage in stages:
        ok_node = f"{stage} OK?"
        assert data["connections"][ok_node]["main"][1][0]["node"] == f"Format {stage} Error", (
            f"{ok_node} false branch should go to Format {stage} Error"
        )


def test_all_format_error_nodes_chain_to_report_error():
    """Every Format <Stage> Error node must connect to Report <Stage> Error."""
    data = workflow()
    stages = ["Script", "Images", "Narration", "Captions", "Manifest", "Render"]
    for stage in stages:
        conns = data["connections"][f"Format {stage} Error"]["main"]
        assert conns[0][0]["node"] == f"Report {stage} Error", (
            f"Format {stage} Error should connect to Report {stage} Error"
        )


def test_all_report_error_nodes_dispatch_to_wf14_error_handler():
    """Every Report <Stage> Error executeWorkflow node must target
    the WF14 error handler workflow (ikP3QoBi9QwlkIg4)."""
    data = workflow()
    stages = ["Script", "Images", "Narration", "Captions", "Manifest", "Render"]
    for stage in stages:
        report_node = next(
            n for n in data["nodes"] if n["name"] == f"Report {stage} Error"
        )
        assert report_node["type"] == "n8n-nodes-base.executeWorkflow"
        wf_id = report_node["parameters"]["workflowId"]
        wf_id = wf_id["value"] if isinstance(wf_id, dict) else wf_id
        assert wf_id == "ikP3QoBi9QwlkIg4", (
            f"Report {stage} Error should target WF14 (ikP3QoBi9QwlkIg4), got {wf_id}"
        )
