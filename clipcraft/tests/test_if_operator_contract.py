import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / "clipcraft" / "workflows"

SUPPORTED_BOOLEAN_OPS = {"empty", "notEmpty", "true", "false", "equals", "notEquals"}
SUPPORTED_STRING_OPS = {
    "empty",
    "notEmpty",
    "equals",
    "notEquals",
    "contains",
    "notContains",
    "startsWith",
    "notStartsWith",
    "endsWith",
    "notEndsWith",
    "regex",
    "notRegex",
}
SUPPORTED_NUMBER_OPS = {"equals", "notEquals", "gt", "lt", "gte", "lte", "empty", "notEmpty"}


def workflow(name):
    return json.loads((WORKFLOWS / name).read_text(encoding="utf-8"))


def if_nodes(data):
    return [n for n in data["nodes"] if n["type"] == "n8n-nodes-base.if"]


def main_edges(data, node_name):
    return data["connections"].get(node_name, {}).get("main", [])


def true_target(edges):
    return edges[0][0]["node"] if edges and edges[0] else None


def false_target(edges):
    return edges[1][0]["node"] if len(edges) > 1 and edges[1] else None


def assert_supported_operator(n, name):
    cond = n["parameters"].get("conditions", {})
    if "boolean" in cond or "string" in cond or "number" in cond:
        return
    conditions = cond.get("conditions", [])
    assert conditions, f"{name} has no conditions"
    for c in conditions:
        op = c["operator"]
        t = op["type"]
        o = op["operation"]
        supported = {
            "boolean": SUPPORTED_BOOLEAN_OPS,
            "string": SUPPORTED_STRING_OPS,
            "number": SUPPORTED_NUMBER_OPS,
        }[t]
        assert o in supported, f"{name}: unsupported {t} operator '{o}'"


def test_queue_worker_ok_gates_use_equals():
    d = workflow("03-video-job-worker.json")
    for n in if_nodes(d):
        for c in n["parameters"].get("conditions", {}).get("conditions", []):
            if c["operator"]["type"] == "boolean":
                assert c["operator"]["operation"] == "equals", f"{n['name']} uses {c['operator']['operation']}"


def test_queue_worker_images_ok_wiring_matches_historical_contract():
    d = workflow("03-video-job-worker.json")
    edges = main_edges(d, "Images OK?")
    assert true_target(edges) == "Update Progress Narration"
    assert false_target(edges) == "Format Images Error"


def test_queue_worker_render_ok_wiring_is_correct():
    d = workflow("03-video-job-worker.json")
    edges = main_edges(d, "Render OK?")
    assert true_target(edges) == "Complete Job RPC"
    assert false_target(edges) == "Format Render Error"


def test_stage_started_gates_use_equals():
    for name in (
        "05-generate-scene-images.json",
        "06-generate-narration.json",
        "07-build-captions.json",
        "08-build-render-manifest.json",
    ):
        d = workflow(name)
        node = next(n for n in if_nodes(d) if n["name"] == "Stage Started?")
        c = node["parameters"]["conditions"]["conditions"][0]
        assert c["operator"]["operation"] == "equals", name
        edges = main_edges(d, "Stage Started?")
        assert true_target(edges) == "Reserve External Attempt", name
        assert false_target(edges) == "Return Cached Stage", name


def test_wf11_valid_input_swapped_and_operators_supported():
    d = workflow("11-get-video-result.json")
    valid = next(n for n in if_nodes(d) if n["name"] == "Valid Input?")
    edges = main_edges(d, "Valid Input?")
    assert true_target(edges) == "Format 500"
    assert false_target(edges) == "Load Job"
    found = next(n for n in if_nodes(d) if n["name"] == "Job Found?")
    assert found["parameters"]["conditions"]["conditions"][0]["operator"]["operation"] == "gt"
    completed = next(n for n in if_nodes(d) if n["name"] == "Job Completed?")
    assert completed["parameters"]["conditions"]["conditions"][0]["operator"]["operation"] == "equals"


def test_wf15_operators_supported_and_wiring_correct():
    d = workflow("15-download-asset.json")
    for n in if_nodes(d):
        assert_supported_operator(n, n["name"])
    edges = main_edges(d, "Input Valid?")
    assert true_target(edges) == "Check Job"
    assert false_target(edges) == "Return Error"
    edges = main_edges(d, "Exist OK?")
    assert true_target(edges) == "Read File"
    assert false_target(edges) == "Return Error"


def test_wf11_15_rightvalue_normalized_strict():
    expected = {
        "11-get-video-result.json": {
            "Valid Input?": True,
            "Job Found?": 0,
            "Job Completed?": "completed",
        },
        "15-download-asset.json": {
            "Input Valid?": True,
            "Exist OK?": True,
        },
    }
    for name, node_expected in expected.items():
        d = workflow(name)
        for n in if_nodes(d):
            c = n["parameters"]["conditions"]
            assert c.get("combinator") == "and", name
            assert c.get("options", {}).get("typeValidation") == "strict", name
            cond = c["conditions"]
            assert len(cond) == 1
            assert cond[0]["rightValue"] == node_expected[n["name"]], name


def test_no_unsupported_operators_in_touched_workflows():
    for name in (
        "03-video-job-worker.json",
        "05-generate-scene-images.json",
        "06-generate-narration.json",
        "07-build-captions.json",
        "08-build-render-manifest.json",
        "11-get-video-result.json",
        "15-download-asset.json",
    ):
        d = workflow(name)
        for n in if_nodes(d):
            assert_supported_operator(n, f"{name}:{n['name']}")
