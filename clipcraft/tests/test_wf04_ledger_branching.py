import pytest

from tests.wf04_ledger_branch_harness import (
    CANONICAL_STATES,
    FAILED,
    INPUT_HASH_MISMATCH,
    INVALID_ITEM_KEY,
    LEASE_LOST,
    RUNNING,
    ROUTE_CACHED,
    ROUTE_INVALID_KEY,
    ROUTE_LEASE_LOST,
    ROUTE_MISMATCH,
    ROUTE_PROVIDER,
    ROUTE_RUNNING,
    ROUTE_UNKNOWN,
    ROUTE_UNSUPPORTED,
    RUNNING,
    STARTED,
    UNKNOWN_OUTCOME,
    RouterError,
    load_wf04_route_contract,
    normalize_begin_result,
)

VALID_UUID = "c0000000-0000-4000-8000-0000000000cc"


def _base(stage_run_id="a0000000-0000-4000-8000-0000000000aa"):
    return {"stage_run_id": stage_run_id, "state": STARTED}


def test_started_with_valid_run_token_proceeds_to_provider():
    branch = normalize_begin_result({** _base(), "run_token": VALID_UUID})
    assert branch.route == ROUTE_PROVIDER
    assert branch.run_token == VALID_UUID


def test_started_without_run_token_fails_before_provider():
    with pytest.raises(RouterError) as exc:
        normalize_begin_result(_base())
    assert "RUN_TOKEN_REQUIRED" in str(exc.value)


def test_cached_success_succeeds_without_run_token_and_preserves_output():
    branch = normalize_begin_result(
        {**_base(), "state": "CACHED_SUCCESS", "output": {"out": 1}}
    )
    assert branch.route == ROUTE_CACHED
    assert branch.cached_output == {"out": 1}
    assert branch.run_token is None


def test_cached_success_rejects_missing_output():
    with pytest.raises(RouterError) as exc:
        normalize_begin_result({**_base(), "state": "CACHED_SUCCESS"})
    assert "CACHED_OUTPUT_MISSING" in str(exc.value)


@pytest.mark.parametrize(
    "state,route",
    [
        (RUNNING, ROUTE_RUNNING),
        ("FAILED", "failure_previous"),
        (INPUT_HASH_MISMATCH, ROUTE_MISMATCH),
        (INVALID_ITEM_KEY, ROUTE_INVALID_KEY),
        (UNKNOWN_OUTCOME, ROUTE_UNKNOWN),
    ],
)
def test_non_started_states_stop_safely_without_run_token(state, route):
    branch = normalize_begin_result({**_base(), "state": state})
    assert branch.route == route
    assert branch.run_token is None
    assert branch.cached_output is None


def test_lease_lost_routes_to_safe_stop():
    branch = normalize_begin_result({"state": LEASE_LOST, "message": "stale"})
    assert branch.route == ROUTE_LEASE_LOST


def test_unrecognized_state_fails_closed():
    branch = normalize_begin_result({**_base(), "state": "SOME_NEW_STATE"})
    assert branch.route == ROUTE_UNSUPPORTED
    assert branch.run_token is None


def test_missing_state_fails_closed():
    branch = normalize_begin_result({**_base(), "state": None})
    assert branch.route == ROUTE_UNSUPPORTED


def test_blank_stage_run_id_raises():
    with pytest.raises(RouterError) as exc:
        normalize_begin_result({"state": STARTED, "stage_run_id": " ", "run_token": VALID_UUID})
    assert "STAGE_RUN_ID_REQUIRED" in str(exc.value)


def test_only_started_routes_to_provider():
    provider_states = {"STARTED"}
    for state in CANONICAL_STATES:
        routed = normalize_begin_result(
            {**_base(), "state": state,
             "run_token": VALID_UUID if state == "STARTED" else None,
             "output": {"out": 1} if state == "CACHED_SUCCESS" else None}
        ).route
        if state == "STARTED":
            assert routed == ROUTE_PROVIDER
        else:
            assert routed != ROUTE_PROVIDER


def test_no_run_token_fabricated_for_non_started():
    for state in CANONICAL_STATES - {"STARTED"}:
        result = {**_base(), "state": state,
                  "output": {"out": 1} if state == "CACHED_SUCCESS" else None}
        branch = normalize_begin_result(result)
        assert branch.run_token is None


def test_repo_workflow_routes_every_canonical_state_no_fallthrough():
    # RED: fails until the workflow JSON is edited to add the routing.
    assert load_wf04_route_contract() is True