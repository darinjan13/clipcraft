import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "clipcraft" / "workflows" / "02-create-video-job.json"


def validate_code():
    data = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    return next(node for node in data["nodes"] if node["name"] == "Validate and Create Job")["parameters"]["jsCode"]


def run_validate(payload):
    script = """
const fs = require('fs');
const code = fs.readFileSync(0, 'utf8');
const fn = new Function('$json', code);
process.stdout.write(JSON.stringify(fn(JSON.parse(process.env.WF02_PAYLOAD))));
"""
    env = {**os.environ, "WF02_PAYLOAD": json.dumps(payload)}
    return subprocess.run(
        ["node", "-e", script],
        input=validate_code(),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def valid_payload(**brief_overrides):
    brief = {
        "topic": "How bees help plants grow",
        "duration": 30,
        "sceneCount": 6,
        "language": "English",
        "contentStyle": "Simple educational",
        "visualStyle": "Bright cinematic nature documentary",
        "voiceTone": "Warm and clear",
        "captionStyle": "bold highlighted words",
    }
    brief.update(brief_overrides)
    return {"channelId": "wf02-test", "sessionId": "session-1", "brief": brief}


def test_validate_and_create_source_parses_in_node_runtime():
    result = run_validate(valid_payload())
    assert result.returncode == 0, result.stderr


def test_valid_create_payload_preserves_exact_job_contract():
    result = run_validate(valid_payload())
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)[0]["json"]
    assert output["status"] == "queued"
    assert output["progress"] == 0
    assert output["currentStep"] == "queued"
    assert output["channelId"] == "wf02-test"
    assert output["sessionId"] == "session-1"
    assert output["brief"] == {
        "topic": "How bees help plants grow",
        "duration": 30,
        "sceneCount": 6,
        "language": "English",
        "contentStyle": "Simple educational",
        "visualStyle": "Bright cinematic nature documentary",
        "voiceTone": "Warm and clear",
        "captionStyle": "bold highlighted words",
        "aspectRatio": "9:16",
    }
    assert len(output["jobId"]) == 36
    assert "credential" not in json.dumps(output).lower()
    assert "secret" not in json.dumps(output).lower()


def test_missing_required_field_is_rejected():
    result = run_validate(valid_payload(voiceTone=""))
    assert "Missing brief.voiceTone" in result.stderr


def test_invalid_duration_is_rejected():
    result = run_validate(valid_payload(duration=15))
    assert "brief.duration must be 30, 45, 60, or 90" in result.stderr


def test_scene_count_is_clamped_to_existing_bounds():
    result = run_validate(valid_payload(sceneCount=99))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0]["json"]["brief"]["sceneCount"] == 18


def test_provider_model_and_snapshot_extras_are_not_persisted_by_create_contract():
    result = run_validate(
        valid_payload(
            textProvider="cloudflare",
            textModel="@cf/meta/llama-3.1-8b-instruct",
            imageProvider="cloudflare",
            imageModel="@cf/black-forest-labs/flux-1-schnell",
            snapshotId="snapshot-1",
        )
    )
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)[0]["json"]
    for field in ("textProvider", "textModel", "imageProvider", "imageModel", "snapshotId"):
        assert field not in output["brief"]


def test_colon_containing_model_id_does_not_break_create_validation():
    result = run_validate(valid_payload(modelId="@cf/meta/llama-3.1-8b-instruct"))
    assert result.returncode == 0, result.stderr


def test_create_workflow_preserves_downstream_payload_shape():
    data = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    nodes = {node["name"]: node for node in data["nodes"]}
    insert = nodes["Insert Job"]["parameters"]["jsonBody"]
    assert '"id": "{{ $json.jobId }}"' in insert
    assert '"brief_json": {{ JSON.stringify($json.brief) }}' in insert
    assert '"status": "queued"' in insert
    assert '"current_step": "queued"' in insert
    assert data["connections"]["Insert Job"]["main"][0][0]["node"] == "Build Create Response"
