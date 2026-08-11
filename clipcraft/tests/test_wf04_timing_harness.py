import pytest
import ast
from pathlib import Path

from tests.wf04_timing_harness import (
    FakeProvider,
    SCENE_NARRATIONS,
    lease_decision,
    load_wf04_contract,
    measure_runs,
    nearest_rank,
    render_report,
    run_case,
)


def test_contract_constants_are_loaded_from_repository_workflow():
    contract = load_wf04_contract()
    assert contract.voice_words_per_minute == 194
    assert contract.minimum_word_ratio == 0.92
    assert contract.maximum_word_ratio == 1.08
    assert contract.minimum_scene_duration == 2
    assert contract.maximum_scene_duration == 10


def test_nearest_rank_uses_one_based_ceiling_rank():
    values = [4, 1, 3, 2]
    assert nearest_rank(values, 0.50) == 2
    assert nearest_rank(values, 0.95) == 4


def test_successful_revision_run_inserts_six_exact_scenes_and_finalizes():
    result = run_case(case_number=1, force_revision=True, provider=FakeProvider([0.35, 4.207]))
    assert result.revision_count == 1
    assert result.provider_calls == 2
    assert len(result.scenes) == 6
    assert [scene["index"] for scene in result.scenes] == list(range(1, 7))
    assert {scene["job_id"] for scene in result.scenes} == {result.job_id}
    assert [scene["narration"] for scene in result.scenes] == SCENE_NARRATIONS
    assert [scene["caption"] for scene in result.scenes] == [
        "Scene one.",
        "Scene two.",
        "Scene three.",
        "Scene four.",
        "Scene five.",
        "Scene six.",
    ]
    assert [scene["image_prompt"] for scene in result.scenes] == [
        "Image one.",
        "Image two.",
        "Image three.",
        "Image four.",
        "Image five.",
        "Image six.",
    ]
    assert all(2 <= scene["duration_seconds"] <= 10 for scene in result.scenes)
    assert all(scene["motion"] == "zoom_in" for scene in result.scenes)
    assert all(scene["transition"] == "crossfade" for scene in result.scenes)
    assert result.lease_events == ["begin", "reserve", "heartbeat", "finalize"]


@pytest.mark.parametrize(
    "failure,classification",
    [
        ("malformed_response", "PROVIDER_RESPONSE_INVALID"),
        ("failed_revision", "REVISION_FAILED"),
        ("begin", "LEASE_BEGIN_FAILED"),
        ("reserve", "LEASE_RESERVE_FAILED"),
        ("heartbeat", "LEASE_HEARTBEAT_FAILED"),
        ("scene_insert", "SCENE_INSERT_FAILED"),
        ("finalize", "LEASE_FINALIZE_FAILED"),
    ],
)
def test_failure_stops_later_operations(failure, classification):
    result = run_case(case_number=1, force_revision=True, failure=failure)
    assert result.failure_class == classification
    assert result.completed is False
    if failure in {"begin", "reserve", "heartbeat", "finalize"}:
        assert result.failure_event in result.lease_events
    if failure in {"scene_insert", "finalize"}:
        assert result.scene_inserted is (failure == "finalize")
    if failure in {"begin", "reserve", "heartbeat", "scene_insert"}:
        assert "finalize" not in result.lease_events


def test_measurement_runs_100_cases_with_150_provider_calls_and_50_revisions():
    measurement = measure_runs()
    assert measurement.run_count == 100
    assert measurement.revision_runs == 50
    assert measurement.provider_calls == 150
    assert measurement.provider_delay_counts == {0.350: 143, 4.207: 7}


def test_lease_decision_applies_fixed_twenty_percent_and_five_second_margin():
    assert lease_decision(modeled_worst=90.0, lease_seconds=120).confirmed is True
    assert lease_decision(modeled_worst=101.0, lease_seconds=120).confirmed is False


def test_report_separates_modeled_duration_from_wall_clock_runtime():
    report = render_report(measure_runs())
    assert "Modeled P50:" in report
    assert "Modeled P95:" in report
    assert "Modeled worst:" in report
    assert "Harness wall-clock runtime:" in report
    assert "150" in report


def test_harness_has_no_external_boundary_imports():
    source_path = Path(__file__).with_name("wf04_timing_harness.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = {
        node.names[0].name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    }
    assert imported.isdisjoint({"socket", "urllib", "requests", "subprocess", "supabase", "docker"})
