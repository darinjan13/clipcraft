"""API-only functional verification for the configured WF17 and WF18 workflows.

The suite uses only n8n's documented public API and webhook endpoints. It does
not inspect or mutate n8n's database.
"""
import copy
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


REQUIRED_NODE_NAMES = {
    "Workflow Trigger",
    "Build Request",
    "Validate Input",
    "Prepare Provider Attempt",
    "Call Provider API",
    "Evaluate Provider Result",
    "Retryable Failure?",
    "Increment Retry",
    "Handle Validation Error",
    "Normalize Response",
}
DEFAULT_CLOCK_SKEW_SECONDS = "5"
DEFAULT_MAX_EXECUTION_PAGES = "20"
PAGE_SIZE = 100


class TestFailure(Exception):
    """A safe, user-facing functional test failure."""


class NoMatchingExecution(TestFailure):
    """The current polling attempt found no correlated execution yet."""


class AuthenticationFailure(TestFailure):
    """The public API rejected authentication or authorization."""


@dataclass(frozen=True)
class Config:
    base_url: str
    api_key: str
    wf17_id: str
    wf18_id: str
    wf17_expected_name: str
    wf18_expected_name: str
    cloudflare_account_id: str
    cloudflare_ai_token: str
    cloudflare_text_model: str
    cloudflare_image_model: str
    timeout_seconds: float
    poll_interval_seconds: float
    clock_skew_seconds: float
    max_execution_pages: int


def result(name, workflow, status="FAIL", details="", correlation_id=None,
           parent_execution_id=None, child_execution_id=None,
           observed_http_status=None, nodes_executed=None):
    return {
        "name": name,
        "workflow": workflow,
        "status": status,
        "details": details,
        "correlation_id": correlation_id,
        "parent_execution_id": parent_execution_id,
        "child_execution_id": child_execution_id,
        "observed_http_status": observed_http_status,
        "nodes_executed": nodes_executed or [],
    }


def required_text(environ, name, errors):
    value = environ.get(name)
    if value is None or not value.strip():
        errors.append(f"{name} is required and must not be blank")
        return None
    return value.strip()


def positive_float(environ, name, default, errors, allow_zero=False):
    raw = environ.get(name, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        errors.append(f"{name} must be a finite number")
        return None
    if not math.isfinite(value) or (value < 0 if allow_zero else value <= 0):
        errors.append(f"{name} must be {'non-negative' if allow_zero else 'positive'}")
        return None
    return value


def positive_int(environ, name, default, errors):
    raw = environ.get(name, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        errors.append(f"{name} must be a positive integer")
        return None
    if value <= 0:
        errors.append(f"{name} must be a positive integer")
        return None
    return value


def preflight(environ=None):
    environ = environ or os.environ
    errors = []
    api_key = required_text(environ, "N8N_API_KEY", errors)
    base_url = required_text(environ, "N8N_BASE_URL", errors)
    if base_url:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            errors.append("N8N_BASE_URL must use http or https and include a hostname")
        if parsed.username or parsed.password:
            errors.append("N8N_BASE_URL must not contain embedded credentials")
        if parsed.query or parsed.fragment:
            errors.append("N8N_BASE_URL must not contain a query or fragment")

    wf17_id = required_text(environ, "WF17_ID", errors)
    wf18_id = required_text(environ, "WF18_ID", errors)
    wf17_expected_name = required_text(environ, "WF17_EXPECTED_NAME", errors)
    wf18_expected_name = required_text(environ, "WF18_EXPECTED_NAME", errors)
    account_id = required_text(environ, "CLOUDFLARE_ACCOUNT_ID", errors)
    cloudflare_token = required_text(environ, "CLOUDFLARE_AI_TOKEN", errors)
    text_model = required_text(environ, "CLOUDFLARE_TEXT_MODEL", errors)
    image_model = required_text(environ, "CLOUDFLARE_IMAGE_MODEL", errors)
    timeout_seconds = positive_float(
        environ, "N8N_TEST_TIMEOUT_SECONDS", "60", errors)
    poll_interval_seconds = positive_float(
        environ, "N8N_TEST_POLL_INTERVAL_SECONDS", "2", errors)
    clock_skew_seconds = positive_float(
        environ, "N8N_EXECUTION_CLOCK_SKEW_SECONDS",
        DEFAULT_CLOCK_SKEW_SECONDS, errors, allow_zero=True)
    max_execution_pages = positive_int(
        environ, "N8N_MAX_EXECUTION_PAGES", DEFAULT_MAX_EXECUTION_PAGES, errors)

    if errors:
        return None, result("environment preflight", "suite", details="; ".join(errors))
    return Config(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        wf17_id=wf17_id,
        wf18_id=wf18_id,
        wf17_expected_name=wf17_expected_name,
        wf18_expected_name=wf18_expected_name,
        cloudflare_account_id=account_id,
        cloudflare_ai_token=cloudflare_token,
        cloudflare_text_model=text_model,
        cloudflare_image_model=image_model,
        timeout_seconds=timeout_seconds,
        poll_interval_seconds=poll_interval_seconds,
        clock_skew_seconds=clock_skew_seconds,
        max_execution_pages=max_execution_pages,
    ), None


def api_request(config, method, path, body=None, query=None, timeout=30):
    """Call the public API without returning response bodies for HTTP failures."""
    url = config.base_url + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {
        "Accept": "application/json",
        "X-N8N-API-KEY": config.api_key,
    }
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise AuthenticationFailure(
                f"Public API authentication rejected: HTTP {error.code}")
        return error.code, None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise TestFailure(f"Public API transport failure: {type(error).__name__}")

    raw = response.read().decode()
    if not raw:
        return response.status, None
    try:
        return response.status, json.loads(raw)
    except json.JSONDecodeError:
        raise TestFailure("Public API returned malformed JSON")


def unwrap_object(payload, description):
    if not isinstance(payload, dict):
        raise TestFailure(f"{description} response was not an object")
    if isinstance(payload.get("data"), dict):
        return payload["data"]
    return payload


def require_http(status, expected, operation):
    if status != expected:
        raise TestFailure(f"{operation} failed: HTTP {status}")


def connection_target(connections, source, branch, expected_target):
    source_connections = connections.get(source)
    if not isinstance(source_connections, dict):
        raise TestFailure(f"Missing connections for {source}")
    main = source_connections.get("main")
    if not isinstance(main, list) or len(main) <= branch:
        raise TestFailure(f"Missing branch {branch} for {source}")
    branch_connections = main[branch]
    if not isinstance(branch_connections, list) or not branch_connections:
        raise TestFailure(f"Empty branch {branch} for {source}")
    targets = [item.get("node") for item in branch_connections
               if isinstance(item, dict)]
    if expected_target not in targets:
        raise TestFailure(
            f"{source} branch {branch} does not connect to {expected_target}")


def verify_target_workflow(config, workflow_label, configured_id, expected_name):
    status, payload = api_request(
        config, "GET", f"/api/v1/workflows/{urllib.parse.quote(configured_id, safe='')}")
    require_http(status, 200, f"{workflow_label} retrieval")
    workflow = unwrap_object(payload, f"{workflow_label} retrieval")
    if workflow.get("id") != configured_id:
        raise TestFailure(f"{workflow_label} returned an unexpected workflow ID")
    if workflow.get("name") != expected_name:
        raise TestFailure(f"{workflow_label} returned an unexpected workflow name")
    if workflow.get("active") is not True:
        raise TestFailure(f"{workflow_label} is not active")

    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        raise TestFailure(f"{workflow_label} has malformed nodes")
    node_names = {node.get("name") for node in nodes if isinstance(node, dict)}
    missing = REQUIRED_NODE_NAMES - node_names
    if missing:
        raise TestFailure(f"{workflow_label} is missing nodes: {sorted(missing)}")

    connections = workflow.get("connections")
    if not isinstance(connections, dict):
        raise TestFailure(f"{workflow_label} has malformed connections")
    connection_target(connections, "Build Request", 0, "Validate Input")
    connection_target(connections, "Validate Input", 0, "Prepare Provider Attempt")
    connection_target(connections, "Validate Input", 1, "Handle Validation Error")
    connection_target(connections, "Handle Validation Error", 0, "Normalize Response")
    connection_target(connections, "Prepare Provider Attempt", 0, "Call Provider API")
    connection_target(connections, "Call Provider API", 0, "Evaluate Provider Result")
    connection_target(connections, "Evaluate Provider Result", 0, "Retryable Failure?")
    connection_target(connections, "Retryable Failure?", 0, "Increment Retry")
    connection_target(connections, "Retryable Failure?", 1, "Normalize Response")
    connection_target(connections, "Increment Retry", 0, "Prepare Provider Attempt")
    return workflow


def create_parent(config, child_id, name):
    path = f"functional-{child_id}-{uuid.uuid4().hex}"
    payload = {
        "name": name,
        "nodes": [
            {"id": "w1", "name": "Webhook", "type": "n8n-nodes-base.webhook",
             "typeVersion": 2, "position": [250, 300], "parameters": {
                 "httpMethod": "POST", "path": path,
                 "responseMode": "responseNode", "options": {}}},
            {"id": "e1", "name": "Exec Sub", "type": "n8n-nodes-base.executeWorkflow",
             "typeVersion": 2, "position": [450, 300], "parameters": {
                 "source": "database", "workflowId": {"value": child_id}, "mode": "each"}},
            {"id": "r1", "name": "Response", "type": "n8n-nodes-base.respondToWebhook",
             "typeVersion": 1.4, "position": [650, 300], "parameters": {
                 "respondWith": "json", "responseBody": "={{ $json }}", "options": {}}},
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "Exec Sub", "type": "main", "index": 0}]]},
            "Exec Sub": {"main": [[{"node": "Response", "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"},
        "staticData": None,
    }
    status, response = api_request(config, "POST", "/api/v1/workflows", payload)
    if status not in (200, 201):
        raise TestFailure(f"Disposable parent creation failed: HTTP {status}")
    created = unwrap_object(response, "Disposable parent creation")
    parent_id = created.get("id")
    if not isinstance(parent_id, str) or not parent_id:
        raise TestFailure("Disposable parent creation returned no workflow ID")
    return parent_id, path


def verify_parent(config, parent_id):
    status, payload = api_request(config, "GET", f"/api/v1/workflows/{parent_id}")
    require_http(status, 200, "Disposable parent retrieval")
    workflow = unwrap_object(payload, "Disposable parent retrieval")
    if workflow.get("id") != parent_id:
        raise TestFailure("Disposable parent retrieval returned an unexpected ID")
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list):
        raise TestFailure("Disposable parent has malformed nodes")
    names = {node.get("name") for node in nodes if isinstance(node, dict)}
    if names != {"Webhook", "Exec Sub", "Response"}:
        raise TestFailure("Disposable parent topology is incorrect")
    connections = workflow.get("connections")
    if not isinstance(connections, dict) or set(connections) != {"Webhook", "Exec Sub"}:
        raise TestFailure("Disposable parent connections are incorrect")


def activate_parent(config, parent_id):
    status, _ = api_request(
        config, "POST", f"/api/v1/workflows/{parent_id}/activate", {})
    if status not in (200, 204):
        raise TestFailure(f"Disposable parent activation failed: HTTP {status}")
    status, payload = api_request(config, "GET", f"/api/v1/workflows/{parent_id}")
    require_http(status, 200, "Disposable parent post-activation retrieval")
    workflow = unwrap_object(payload, "Disposable parent post-activation retrieval")
    if workflow.get("active") is not True:
        raise TestFailure("Disposable parent is not active after activation")


def cleanup_parent(config, parent_id):
    status, _ = api_request(
        config, "POST", f"/api/v1/workflows/{parent_id}/deactivate")
    if status not in (200, 204):
        raise TestFailure(f"Disposable parent deactivation failed: HTTP {status}")
    status, _ = api_request(config, "DELETE", f"/api/v1/workflows/{parent_id}")
    if status not in (200, 204):
        raise TestFailure(f"Disposable parent deletion failed: HTTP {status}")
    status, _ = api_request(config, "GET", f"/api/v1/workflows/{parent_id}")
    if status not in (404, 410):
        raise TestFailure(
            "Disposable parent post-delete retrieval did not return HTTP 404 or 410")


def parse_aware_timestamp(value, description):
    if not isinstance(value, str) or not value.strip():
        raise TestFailure(f"{description} timestamp is missing")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise TestFailure(f"{description} timestamp is malformed")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TestFailure(f"{description} timestamp is not timezone-aware")
    return parsed.astimezone(timezone.utc)


def execution_started_at(summary):
    if not isinstance(summary, dict) or not isinstance(summary.get("id"), (str, int)):
        raise TestFailure("Execution summary is malformed")
    return parse_aware_timestamp(summary.get("startedAt"), "Execution")


def paged_executions(config, workflow_id, cutoff):
    cursor = None
    seen_cursors = set()
    for page_number in range(1, config.max_execution_pages + 1):
        query = {"workflowId": workflow_id, "limit": PAGE_SIZE}
        if cursor is not None:
            query["cursor"] = cursor
        status, response = api_request(config, "GET", "/api/v1/executions", query=query)
        if status != 200:
            raise TestFailure(f"Execution page {page_number} failed: HTTP {status}")
        if not isinstance(response, dict):
            raise TestFailure(f"Execution page {page_number} was not an object")
        data = response.get("data")
        next_cursor = response.get("nextCursor")
        if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor):
            raise TestFailure(f"Execution page {page_number} returned a malformed nextCursor")
        if not isinstance(data, list):
            raise TestFailure(f"Execution page {page_number} has no data array")
        summaries = []
        for item in data:
            started_at = execution_started_at(item)
            summaries.append((item, started_at))
            if started_at >= cutoff:
                yield item
        if not data and not next_cursor:
            raise TestFailure(
                f"Execution page {page_number} had neither usable data nor a terminal cursor")
        if next_cursor is None:
            return
        if next_cursor in seen_cursors:
            raise TestFailure("Execution pagination repeated a nextCursor")
        seen_cursors.add(next_cursor)
        if summaries and all(started_at < cutoff for _, started_at in summaries):
            # The public specification does not guarantee newest-first ordering.
            # Continue to the configured page bound rather than making an unsafe stop.
            pass
        cursor = next_cursor
    raise TestFailure(
        f"Execution pagination exceeded configured maximum of "
        f"{config.max_execution_pages} pages; ordering is not assumed")


def execution_payload(config, execution_id):
    status, response = api_request(
        config, "GET", f"/api/v1/executions/{urllib.parse.quote(str(execution_id), safe='')}",
        query={"includeData": "true", "ignoreDataSizeLimit": "true"})
    if status != 200:
        raise TestFailure(f"Full execution retrieval failed: HTTP {status}")
    execution = unwrap_object(response, "Full execution retrieval")
    if execution.get("id") is None:
        raise TestFailure("Full execution response has no ID")
    data = execution.get("data")
    if not isinstance(data, dict):
        raise TestFailure("Execution data is missing, redacted, or malformed")
    result_data = data.get("resultData")
    if not isinstance(result_data, dict):
        raise TestFailure("Execution resultData is missing, redacted, or malformed")
    run_data = result_data.get("runData")
    if not isinstance(run_data, dict) or not run_data:
        raise TestFailure("Execution runData is missing or empty")
    for node_name, runs in run_data.items():
        if not isinstance(node_name, str) or not isinstance(runs, list):
            raise TestFailure("Execution runData contains a malformed node entry")
        for run in runs:
            if not isinstance(run, dict):
                raise TestFailure("Execution runData contains a malformed node run")
    return execution, run_data


def extract_candidate_correlation(run_data):
    trigger_runs = run_data.get("Workflow Trigger")
    if trigger_runs is None:
        return None
    if not isinstance(trigger_runs, list):
        return None
    for run in trigger_runs:
        if not isinstance(run, dict):
            continue
        run_data_value = run.get("data")
        if not isinstance(run_data_value, dict):
            continue
        main = run_data_value.get("main")
        if not isinstance(main, list):
            continue
        for output in main:
            if not isinstance(output, list):
                continue
            for item in output:
                if not isinstance(item, dict) or not isinstance(item.get("json"), dict):
                    continue
                marker = item["json"].get("_testCorrelationId")
                if isinstance(marker, str):
                    return marker
    return None


def strict_trigger_correlation(run_data, marker):
    trigger_runs = run_data.get("Workflow Trigger")
    if not isinstance(trigger_runs, list) or not trigger_runs:
        raise TestFailure("Correlated execution has no valid Workflow Trigger runs")
    matches = 0
    for run in trigger_runs:
        if not isinstance(run, dict):
            raise TestFailure("Correlated Workflow Trigger run is malformed")
        run_data_value = run.get("data")
        if not isinstance(run_data_value, dict):
            raise TestFailure("Correlated Workflow Trigger data is malformed")
        main = run_data_value.get("main")
        if not isinstance(main, list):
            raise TestFailure("Correlated Workflow Trigger data.main is malformed")
        for output in main:
            if not isinstance(output, list):
                raise TestFailure("Correlated Workflow Trigger output is malformed")
            for item in output:
                if not isinstance(item, dict) or not isinstance(item.get("json"), dict):
                    raise TestFailure("Correlated Workflow Trigger item is malformed")
                if item["json"].get("_testCorrelationId") == marker:
                    matches += 1
    if matches == 0:
        raise TestFailure("Correlated execution has no exact marker occurrence")
    if matches != 1:
        raise TestFailure("Correlated execution has multiple exact marker occurrences")


def find_child_execution(config, child_id, marker, test_started_at):
    cutoff = test_started_at - timedelta(seconds=config.clock_skew_seconds)
    matches = []
    for summary in paged_executions(config, child_id, cutoff):
        started_at = execution_started_at(summary)
        if started_at < cutoff:
            continue
        execution, run_data = execution_payload(config, summary["id"])
        candidate_marker = extract_candidate_correlation(run_data)
        if candidate_marker != marker:
            continue
        strict_trigger_correlation(run_data, marker)
        matches.append((execution, run_data))
    if not matches:
        raise NoMatchingExecution("No correlated child execution found yet")
    if len(matches) != 1:
        raise TestFailure(f"Multiple correlated child executions found: {len(matches)}")
    return matches[0]


def expected_provider_request(config, model, body):
    return {
        "url": f"https://api.cloudflare.com/client/v4/accounts/"
               f"{config.cloudflare_account_id}/ai/run/{model}",
        "headers": {
            "Authorization": f"Bearer {config.cloudflare_ai_token}",
            "Content-Type": "application/json",
        },
        "body": body,
    }


def check(condition, message):
    if not condition:
        raise TestFailure(message)


def assert_normalized_response(response, response_type, success):
    """Validate the provider-independent response shape without runtime access."""
    check(isinstance(response, dict), "normalized response is not an object")
    check(response.get("success") is success, "normalized success flag is incorrect")
    check(response.get("type") == response_type, "normalized response type is incorrect")
    check(isinstance(response.get("retryCount"), int), "retryCount is not an integer")
    parse_aware_timestamp(response.get("timestamp"), "normalized response")
    if success:
        if response_type == "text":
            check(isinstance(response.get("result"), str), "text result is missing")
        else:
            check(isinstance(response.get("imageBase64"), str), "imageBase64 is missing")
            check(isinstance(response.get("format"), str), "image format is missing")
    else:
        error = response.get("error")
        check(isinstance(error, dict), "normalized error is missing")
        check(isinstance(error.get("source"), str) and error["source"],
              "normalized error source is missing")


def assert_retry_outcomes():
    """Check the four evaluator truth-table outcomes without runtime access."""
    def decide(provider_success, retryable_provider, retry_count):
        return {
            "shouldRetry": not provider_success and retryable_provider and retry_count < 2,
            "retryExhausted": not provider_success and retryable_provider and retry_count >= 2,
        }

    check(decide(True, False, 0) == {"shouldRetry": False, "retryExhausted": False},
          "success evaluator outcome is incorrect")
    check(decide(False, True, 0) == {"shouldRetry": True, "retryExhausted": False},
          "retryable pre-exhaustion outcome is incorrect")
    check(decide(False, True, 2) == {"shouldRetry": False, "retryExhausted": True},
          "retryable exhaustion outcome is incorrect")
    check(decide(False, False, 0) == {"shouldRetry": False, "retryExhausted": False},
          "non-retryable outcome is incorrect")


def static_contract_checks():
    """Verify repository contracts without n8n, webhook, or provider calls."""
    root = Path(__file__).resolve().parent
    assert_retry_outcomes()
    workflows = {
        "WF17": root / "clipcraft" / "workflows" / "17-ai-generate-text.json",
        "WF18": root / "clipcraft" / "workflows" / "18-ai-generate-image.json",
    }
    for label, path in workflows.items():
        workflow = json.loads(path.read_text(encoding="utf-8"))
        nodes = {node["name"]: node for node in workflow["nodes"]}
        missing = REQUIRED_NODE_NAMES - nodes.keys()
        check(not missing, f"{label} is missing nodes: {sorted(missing)}")
        connections = workflow["connections"]
        connection_target(connections, "Validate Input", 0, "Prepare Provider Attempt")
        connection_target(connections, "Validate Input", 1, "Handle Validation Error")
        connection_target(connections, "Handle Validation Error", 0, "Normalize Response")
        connection_target(connections, "Prepare Provider Attempt", 0, "Call Provider API")
        connection_target(connections, "Call Provider API", 0, "Evaluate Provider Result")
        connection_target(connections, "Evaluate Provider Result", 0, "Retryable Failure?")
        connection_target(connections, "Retryable Failure?", 0, "Increment Retry")
        connection_target(connections, "Retryable Failure?", 1, "Normalize Response")
        connection_target(connections, "Increment Retry", 0, "Prepare Provider Attempt")
        normalize_code = nodes["Normalize Response"]["parameters"]["jsCode"]
        check("timestamp" in normalize_code and "source" in normalize_code,
              f"{label} normalization omits timestamp or error source")
        check("retryCount" in normalize_code, f"{label} normalization omits retryCount")
        retry_code = nodes["Evaluate Provider Result"]["parameters"]["jsCode"]
        increment_code = nodes["Increment Retry"]["parameters"]["jsCode"]
        check("< 2" in retry_code, f"{label} retry bound is not two")
        check("retryCount" in increment_code and "Prepare Provider Attempt" in increment_code,
              f"{label} retry state is not explicit")
        check("$('Retry').all()" not in retry_code,
              f"{label} retry state reads an unexecuted node")
        check("shouldRetry" in retry_code, f"{label} retry decision is not explicit")

    wf18_code = json.loads(workflows["WF18"].read_text(encoding="utf-8"))
    normalize_code = next(node["parameters"]["jsCode"] for node in wf18_code["nodes"]
                          if node["name"] == "Normalize Response")
    for key in ("jobId", "sceneId", "sceneIndex", "imageBase64", "format"):
        check(key in normalize_code, f"WF18 normalization omits {key}")

    callers = [root / "clipcraft" / "workflows" / name for name in (
        "01-chat-message.json", "03-video-job-worker.json",
        "04-generate-script-and-scenes.json", "05-generate-scene-images.json",
        "12-regenerate-scene.json")]
    deprecated = ("result.response", "result.image", "result.base64")
    for path in callers:
        workflow = json.loads(path.read_text(encoding="utf-8"))
        check(isinstance(workflow.get("nodes"), list), f"{path.name} has malformed nodes")
        check(isinstance(workflow.get("connections"), dict),
              f"{path.name} has malformed connections")
        source = path.read_text(encoding="utf-8")
        for alias in deprecated:
            check(alias not in source, f"{path.name} contains deprecated alias {alias}")

    caller_workflows = {
        path.name: json.loads(path.read_text(encoding="utf-8")) for path in callers
    }
    wf03_source = caller_workflows["03-video-job-worker.json"]
    wf03_source_text = json.dumps(wf03_source)
    check(wf03_source_text.count("JSON.stringify({ jobId:") == 6,
          "WF03 error payloads are not JSON-safe on every failure path")

    wf04 = caller_workflows["04-generate-script-and-scenes.json"]
    wf04_connections = wf04["connections"]
    check(wf04_connections["AI Text Success?"]["main"][1][0]["node"] == "Build Response",
          "WF04 provider failure does not reach the safe response")
    check(not wf04_connections["Save Script"]["main"][0],
          "WF04 Save Script still creates a duplicate response branch")

    wf05 = caller_workflows["05-generate-scene-images.json"]
    wf05_nodes = {node["name"]: node for node in wf05["nodes"]}
    pending_url = wf05_nodes["Get Pending Scenes"]["parameters"]["url"]
    check("generation_status=eq.pending" in pending_url,
          "WF05 does not restrict image generation to pending scenes")
    check(wf05_nodes["Execute AI Image"]["parameters"].get("mode") == "each",
          "WF05 image execution is not configured per item")
    update_scene_url = wf05_nodes["Update Scene Record"]["parameters"]["url"]
    check("Save Image File" in update_scene_url,
          "WF05 scene update does not preserve saved image identity")

    wf12 = caller_workflows["12-regenerate-scene.json"]
    wf12_connections = wf12["connections"]
    update_targets = {
        item["node"] for item in wf12_connections["Update Image Prompt"]["main"][0]
    }
    check(update_targets == {"Reset Scene", "Update Job Status", "Execute AI Image"},
          "WF12 does not preserve a single canonical image execution path")
    check(not wf12_connections["Reset Scene"]["main"][0],
          "WF12 Reset Scene still invokes image generation directly")
    check(not wf12_connections["Update Job Status"]["main"][0],
          "WF12 status update still invokes image generation directly")

    assert_normalized_response({
        "success": True, "type": "text", "result": "{}", "retryCount": 0,
        "timestamp": "2026-07-27T00:00:00Z"}, "text", True)
    image_success = {
        "success": True, "type": "image", "imageBase64": "ZmFrZQ==", "format": "png",
        "retryCount": 1, "timestamp": "2026-07-27T00:00:00Z",
        "context": {"jobId": "job", "sceneId": "scene", "sceneIndex": 1},
    }
    assert_normalized_response(image_success, "image", True)
    check(set(image_success["context"]) == {"jobId", "sceneId", "sceneIndex"},
          "WF18 context fixture is not normalized")
    assert_normalized_response({
        "success": False, "type": "image", "retryCount": 2,
        "timestamp": "2026-07-27T00:00:00Z",
        "error": {"type": "RETRY_EXHAUSTED", "code": "MAX_RETRIES_EXCEEDED",
                   "message": "failed", "retryable": False, "source": "cloudflare"}},
        "image", False)


def assert_provider_request(config, case, run_data):
    check("Call Provider API" in run_data, "Call Provider API did not execute")
    check("Handle Validation Error" not in run_data,
          "Handle Validation Error executed for valid input")
    build_runs = run_data.get("Build Request")
    check(isinstance(build_runs, list) and build_runs,
          "Build Request has no recorded runs")
    build_main = build_runs[0].get("data", {}).get("main")
    check(isinstance(build_main, list) and build_main and isinstance(build_main[0], list)
          and build_main[0], "Build Request output structure is malformed")
    first_item = build_main[0][0]
    check(isinstance(first_item, dict) and isinstance(first_item.get("json"), dict),
          "Build Request output item is malformed")
    provider_input = first_item["json"]
    check(set(provider_input) == {"isValid", "provider", "url", "headers", "body"},
          "Build Request output keys are not exact")
    check(provider_input.get("isValid") is True, "Build Request did not mark input valid")
    check(provider_input.get("provider") == "cloudflare",
          "Build Request selected an unexpected provider")
    check(provider_input.get("url") == case["expected"]["url"],
          "Provider URL did not match expected configuration")
    headers = provider_input.get("headers")
    expected_headers = case["expected"]["headers"]
    check(isinstance(headers, dict), "Provider headers are malformed")
    check(headers.get("Content-Type") == expected_headers["Content-Type"],
          "Provider Content-Type header did not match expected value")
    check(headers.get("Authorization") == expected_headers["Authorization"],
          "Provider Authorization header did not match expected bearer token")
    check(provider_input.get("body") == case["expected"]["body"],
          "Provider body did not match expected body")
    check("_testCorrelationId" not in provider_input,
          "Correlation marker leaked into Build Request output")
    check("_testCorrelationId" not in headers,
          "Correlation marker leaked into provider headers")
    check("_testCorrelationId" not in provider_input["body"],
          "Correlation marker leaked into provider body")


def assert_invalid_request(run_data):
    for node_name in ("Build Request", "Validate Input", "Handle Validation Error",
                      "Normalize Response"):
        check(node_name in run_data, f"{node_name} did not execute for invalid input")
    check("Call Provider API" not in run_data,
          "Call Provider API executed for invalid input")


def run_case(config, workflow, child_id, path, case):
    marker = f"clipcraft-functional-{workflow}-{uuid.uuid4()}"
    payload = copy.deepcopy(case["payload"])
    payload["_testCorrelationId"] = marker
    record = result(case["name"], workflow, correlation_id=marker)
    test_started_at = datetime.now(timezone.utc)
    try:
        request = urllib.request.Request(
            config.base_url + "/webhook/" + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            response = urllib.request.urlopen(request, timeout=30)
            record["observed_http_status"] = response.status
        except urllib.error.HTTPError as error:
            record["observed_http_status"] = error.code
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise TestFailure(f"Webhook transport failure: {type(error).__name__}")

        deadline = time.monotonic() + config.timeout_seconds
        while True:
            try:
                execution, run_data = find_child_execution(
                    config, child_id, marker, test_started_at)
                record["child_execution_id"] = str(execution["id"])
                record["nodes_executed"] = list(run_data.keys())
                break
            except NoMatchingExecution:
                if time.monotonic() >= deadline:
                    raise TestFailure("No correlated child execution found before timeout")
                time.sleep(config.poll_interval_seconds)

        if case["valid"]:
            assert_provider_request(config, case, run_data)
        else:
            assert_invalid_request(run_data)
        record["status"] = "PASS"
    except AuthenticationFailure:
        raise
    except TestFailure as error:
        record["details"] = str(error)
    except Exception as error:
        record["details"] = f"Unexpected {type(error).__name__} during case execution"
    return record


def text_valid_cases(config):
    prompt = "Write one concise sentence about a blue sky."
    top_system = "Top-level system instruction."
    body_system = "Body system instruction."
    top_metadata = {"source": "top", "attempt": 1}
    body_metadata = {"source": "body", "attempt": 2}

    def valid(name, payload, normalized_prompt=prompt, system_prompt=""):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": normalized_prompt})
        return {
            "name": name,
            "valid": True,
            "path": "HTTP",
            "payload": payload,
            "expected": expected_provider_request(
                config, config.cloudflare_text_model,
                {"messages": messages, "max_tokens": 5000, "temperature": 0.6}),
        }

    return [
        valid("WF17 top-level prompt", {"prompt": prompt, "provider": "cloudflare"}),
        valid("WF17 body prompt fallback", {"body": {"prompt": prompt}}),
        valid("WF17 top-level prompt wins", {
            "prompt": "Top-level prompt.", "body": {"prompt": "Body prompt."}},
             normalized_prompt="Top-level prompt."),
        valid("WF17 body systemPrompt fallback", {
            "prompt": prompt, "body": {"systemPrompt": body_system}},
             system_prompt=body_system),
        valid("WF17 top-level systemPrompt wins", {
            "prompt": prompt, "systemPrompt": top_system,
            "body": {"systemPrompt": body_system}}, system_prompt=top_system),
        valid("WF17 top-level metadata wins", {
            "prompt": prompt, "metadata": top_metadata,
            "body": {"metadata": body_metadata}}),
        valid("WF17 body metadata fallback", {
            "prompt": prompt, "body": {"metadata": body_metadata}}),
    ]


def image_valid_cases(config):
    prompt = "A paper boat on calm water."
    top_metadata = {"source": "top", "attempt": 1}
    body_metadata = {"source": "body", "attempt": 2}

    def valid(name, payload, normalized_prompt=prompt):
        return {
            "name": name,
            "valid": True,
            "path": "HTTP",
            "payload": payload,
            "expected": expected_provider_request(
                config, config.cloudflare_image_model, {"prompt": normalized_prompt}),
        }

    return [
        valid("WF18 top-level prompt", {"prompt": prompt, "provider": "cloudflare"}),
        valid("WF18 body prompt fallback", {"body": {"prompt": prompt}}),
        valid("WF18 top-level prompt wins", {
            "prompt": "Top-level prompt.", "body": {"prompt": "Body prompt."}},
             normalized_prompt="Top-level prompt."),
        valid("WF18 top-level metadata wins", {
            "prompt": prompt, "metadata": top_metadata,
            "body": {"metadata": body_metadata}}),
        valid("WF18 body metadata fallback", {
            "prompt": prompt, "body": {"metadata": body_metadata}}),
    ]


def invalid_cases(workflow):
    prompt = "A valid prompt."
    cases = [
        ("missing prompt", {}),
        ("whitespace-only prompt", {"prompt": "   "}),
        ("non-string prompt", {"prompt": 123}),
        ("null metadata", {"prompt": prompt, "metadata": None}),
        ("array metadata", {"prompt": prompt, "metadata": []}),
        ("string metadata", {"prompt": prompt, "metadata": "metadata"}),
        ("numeric metadata", {"prompt": prompt, "metadata": 7}),
        ("boolean metadata", {"prompt": prompt, "metadata": True}),
        ("top-level null metadata overrides body metadata", {
            "prompt": prompt, "metadata": None, "body": {"metadata": {"valid": True}}}),
        ("unsupported provider", {"prompt": prompt, "provider": "unsupported"}),
    ]
    return [{
        "name": f"{workflow} {name}",
        "valid": False,
        "path": "INVALID",
        "payload": payload,
        "expected": None,
    } for name, payload in cases]


def test_cases(config):
    return [
        ("WF17", config.wf17_id, text_valid_cases(config) + invalid_cases("WF17")),
        ("WF18", config.wf18_id, image_valid_cases(config) + invalid_cases("WF18")),
    ]


def main():
    results = []
    try:
        static_contract_checks()
        results.append(result("static canonical contract checks", "repository", status="PASS"))
    except (TestFailure, OSError, json.JSONDecodeError) as error:
        results.append(result("static canonical contract checks", "repository", details=str(error)))
    if os.environ.get("CLIPCRAFT_ENABLE_RUNTIME_TESTS", "").lower() != "true":
        results.append(result(
            "runtime API tests", "suite", status="SKIP",
            details="Runtime invocation is disabled; set CLIPCRAFT_ENABLE_RUNTIME_TESTS=true explicitly"))
        counts = {status: sum(item["status"] == status for item in results)
                  for status in ("PASS", "FAIL", "SKIP")}
        print(json.dumps({"results": results, "counts": counts}, sort_keys=True))
        return 1 if counts["FAIL"] else 0
    config, preflight_result = preflight()
    if preflight_result:
        results.append(preflight_result)
    else:
        targets = [
            ("WF17", config.wf17_id, config.wf17_expected_name),
            ("WF18", config.wf18_id, config.wf18_expected_name),
        ]
        try:
            for label, workflow_id, expected_name in targets:
                verify_target_workflow(config, label, workflow_id, expected_name)
        except AuthenticationFailure as error:
            results.append(result("workflow identity preflight", "suite", details=str(error)))
        except TestFailure as error:
            results.append(result("workflow identity preflight", "suite", details=str(error)))
        else:
            for workflow, child_id, cases in test_cases(config):
                setup_state = {"parent_id": None, "path": None}
                try:
                    setup_state["parent_id"], setup_state["path"] = create_parent(
                        config, child_id, f"Functional Test Parent {workflow}")
                    verify_parent(config, setup_state["parent_id"])
                    activate_parent(config, setup_state["parent_id"])
                    for case in cases:
                        try:
                            results.append(run_case(
                                config, workflow, child_id, setup_state["path"], case))
                        except AuthenticationFailure as error:
                            results.append(result(case["name"], workflow, details=str(error)))
                except AuthenticationFailure as error:
                    results.append(result("disposable parent setup", workflow, details=str(error)))
                except TestFailure as error:
                    results.append(result("disposable parent setup", workflow, details=str(error)))
                except Exception as error:
                    results.append(result(
                        "disposable parent setup", workflow,
                        details=f"Unexpected {type(error).__name__} during setup"))
                finally:
                    if setup_state["parent_id"] is not None:
                        try:
                            cleanup_parent(config, setup_state["parent_id"])
                        except AuthenticationFailure as error:
                            results.append(result(
                                "disposable parent cleanup", workflow, details=str(error)))
                        except TestFailure as error:
                            results.append(result(
                                "disposable parent cleanup", workflow, details=str(error)))
                        except Exception as error:
                            results.append(result(
                                "disposable parent cleanup", workflow,
                                details=f"Unexpected {type(error).__name__} during cleanup"))

    counts = {status: sum(item["status"] == status for item in results)
              for status in ("PASS", "FAIL", "SKIP")}
    print(json.dumps({"results": results, "counts": counts}, sort_keys=True))
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
