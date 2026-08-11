"""Checkpoint 1S: WF04 ledger-state branch router model.

Fully local; never contacts external services. Emulates the WF04
begin-stage/merge-context/route-state decision given a canonical
begin_job_stage result. Exactly one branch is produced per canonical state;
only STARTED routes to the provider. runToken is required only for STARTED;
cachedOutput only for CACHED_SUCCESS. Nothing is fabricated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STARTED = "STARTED"
CACHED_SUCCESS = "CACHED_SUCCESS"
RUNNING = "RUNNING"
FAILED = "FAILED"
INPUT_HASH_MISMATCH = "INPUT_HASH_MISMATCH"
INVALID_ITEM_KEY = "INVALID_ITEM_KEY"
UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"
LEASE_LOST = "LEASE_LOST"

CANONICAL_STATES = frozenset(
    {
        STARTED,
        CACHED_SUCCESS,
        RUNNING,
        FAILED,
        INPUT_HASH_MISMATCH,
        INVALID_ITEM_KEY,
        UNKNOWN_OUTCOME,
    }
)

ROUTE_PROVIDER = "provider"
ROUTE_CACHED = "cached"
ROUTE_RUNNING = "safe_stop_running"
ROUTE_FAILED = "failure_previous"
ROUTE_MISMATCH = "failure_mismatch"
ROUTE_INVALID_KEY = "failure_invalid_key"
ROUTE_UNKNOWN = "failure_unknown"
ROUTE_UNSUPPORTED = "failure_unsupported"
ROUTE_LEASE_LOST = "lease_lost"

NON_EXECUTABLE_ROUTES = frozenset(
    {
        ROUTE_CACHED,
        ROUTE_RUNNING,
        ROUTE_FAILED,
        ROUTE_MISMATCH,
        ROUTE_INVALID_KEY,
        ROUTE_UNKNOWN,
        ROUTE_UNSUPPORTED,
        ROUTE_LEASE_LOST,
    }
)

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.UNICODE,
)


class RouterError(ValueError):
    pass


@dataclass(frozen=True)
class Branch:
    route: str
    stage_state: str
    stage_run_id: str
    run_token: Any
    cached_output: Any
    reason: Any


def _is_valid_uuid(value: Any) -> bool:
    return isinstance(value, str) and UUID_RE.match(value) is not None


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _reason_for(result: dict[str, Any]) -> Any:
    reason = result.get("reason")
    if reason is not None:
        return reason
    error = result.get("error")
    if error is not None:
        return error
    return None


def normalize_begin_result(result: dict[str, Any]) -> Branch:
    """Produce exactly one Branch for one canonical begin_job_stage result.

    State-specific enforcement:
      STARTED        -> requires a valid run_token; stage_run_id required
      CACHED_SUCCESS -> requires output (cachedOutput); run_token NOT required
      RUNNING, FAILED, INPUT_HASH_MISMATCH, INVALID_ITEM_KEY, UNKNOWN_OUTCOME
                     -> stage_run_id required; run_token NOT required
      LEASE_LOST     -> error-shaped, routes to lease_lost (no provider)
      unrecognized / blank state -> fail closed (unsupported)
    """
    state = result.get("state")

    if state == LEASE_LOST:
        return Branch(
            ROUTE_LEASE_LOST,
            LEASE_LOST,
            "",
            None,
            None,
            result.get("details") or result.get("message") or "LEASE_LOST",
        )

    if not isinstance(state, str) or state not in CANONICAL_STATES:
        return Branch(
            ROUTE_UNSUPPORTED,
            state if isinstance(state, str) else "",
            "",
            None,
            None,
            {"state": state, "reason": "unrecognized_ledger_state"},
        )

    stage_run_id = result.get("stage_run_id")
    if _is_blank(stage_run_id):
        raise RouterError("STAGE_RUN_ID_REQUIRED")

    run_token = result.get("run_token")
    cached_output = result.get("output")
    reason = _reason_for(result)

    if state == STARTED:
        if not _is_valid_uuid(run_token):
            raise RouterError("RUN_TOKEN_REQUIRED")
        return Branch(
            ROUTE_PROVIDER, state, stage_run_id, run_token, None, reason,
        )

    if state == CACHED_SUCCESS:
        if cached_output is None:
            raise RouterError("CACHED_OUTPUT_MISSING")
        return Branch(
            ROUTE_CACHED, state, stage_run_id, None, cached_output, reason,
        )

    route_for_state = {
        RUNNING: ROUTE_RUNNING,
        FAILED: ROUTE_FAILED,
        INPUT_HASH_MISMATCH: ROUTE_MISMATCH,
        INVALID_ITEM_KEY: ROUTE_INVALID_KEY,
        UNKNOWN_OUTCOME: ROUTE_UNKNOWN,
    }
    return Branch(
        route_for_state[state],
        state,
        stage_run_id,
        None,
        None,
        reason or {"state": state, "reason": "non_executable_stage"},
    )


def _workflow_source() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "workflows"
        / "04-generate-script-and-scenes.json"
    ).read_text(encoding="utf-8")


def load_wf04_route_contract() -> bool:
    """Prove the repo WF04 JSON routes every canonical state with no fallthrough.

    Returns True when the workflow source contains the required branch markers,
    does not globally require run_token, and declares an explicit unsupported
    fail-closed marker. This mirrors the contract asserted by the tests; it
    does not execute the workflow.
    """
    source = _workflow_source()
    required = (
        "stageState: state",
        "stageRunId: stageRunId",
        "WF04_LEDGER_STATE_UNSUPPORTED",
        "'CACHED_SUCCESS'",
        "'RUNNING'",
        "'FAILED'",
        "'INPUT_HASH_MISMATCH'",
        "'INVALID_ITEM_KEY'",
        "'UNKNOWN_OUTCOME'",
        "'provider'",
        "'cached'",
        "'safe_stop_running'",
    )
    forbidden = (
        "if (typeof runToken !== 'string' "
        "|| !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i"
        ".test(runToken)) throw new Error('RUN_TOKEN_REQUIRED');",
    )
    return all(marker in source for marker in required) and all(
        marker not in source for marker in forbidden
    )