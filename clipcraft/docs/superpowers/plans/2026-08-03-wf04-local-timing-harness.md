# WF04 Local Timing Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, fully local WF04 timing harness, run 100 modeled cases with 150 provider calls, and record whether the 120-second lease has the required margin.

**Architecture:** `tests/wf04_timing_harness.py` owns the local workflow model, in-memory lease/scene fakes, deterministic provider trace, percentile calculation, and CLI report generation. `tests/test_wf04_timing_harness.py` tests every behavior and isolation boundary. The report is generated only after the tests and 100-run measurement pass.

**Tech Stack:** Python 3.11 standard library, pytest, repository WF04 JSON as a read-only contract source.

---

### Task 1: Define the failing harness contract tests

**Files:**
- Create: `tests/test_wf04_timing_harness.py`
- Create: `tests/wf04_timing_harness.py`

- [ ] **Step 1: Write failing tests for contract extraction and percentile calculation**

Add tests that import `load_wf04_contract` and `nearest_rank`, then assert:

```python
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
```

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run: `py -3 -m pytest -q tests/test_wf04_timing_harness.py`

Expected: collection fails because `tests/wf04_timing_harness.py` does not yet define the imported API.

- [ ] **Step 3: Implement only the contract loader and percentile helper**

Define `Wf04Contract`, `load_wf04_contract()`, and `nearest_rank(values, percentile)` in `tests/wf04_timing_harness.py`. Read `workflows/04-generate-script-and-scenes.json` as text, require the exact production constants `194`, `0.92`, `1.08`, `2`, and `10`, and raise `ContractError` if any is absent. `nearest_rank` must sort a copy, calculate `ceil(percentile * len(values))`, and return that one-based element.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `py -3 -m pytest -q tests/test_wf04_timing_harness.py`

Expected: the two contract tests pass.

- [ ] **Step 5: Commit the contract slice**

```text
git add tests/test_wf04_timing_harness.py tests/wf04_timing_harness.py
git commit -m "test: define WF04 timing harness contract"
```

### Task 2: Add local workflow logic and failure-path coverage

**Files:**
- Modify: `tests/test_wf04_timing_harness.py`
- Modify: `tests/wf04_timing_harness.py`

- [ ] **Step 1: Add failing tests for successful fixtures and all required failures**

Add tests for:

```python
def test_successful_revision_run_inserts_six_exact_scenes_and_finalizes():
    result = run_case(case_number=1, force_revision=True, provider=FakeProvider([0.35, 4.207]))
    assert result.revision_count == 1
    assert len(result.scenes) == 6
    assert [scene["index"] for scene in result.scenes] == list(range(1, 7))
    assert {scene["job_id"] for scene in result.scenes} == {result.job_id}
    assert result.lease_events == ["begin", "reserve", "heartbeat", "finalize"]


@pytest.mark.parametrize("failure,classification", [
    ("malformed_response", "PROVIDER_RESPONSE_INVALID"),
    ("failed_revision", "REVISION_FAILED"),
    ("begin", "LEASE_BEGIN_FAILED"),
    ("reserve", "LEASE_RESERVE_FAILED"),
    ("heartbeat", "LEASE_HEARTBEAT_FAILED"),
    ("scene_insert", "SCENE_INSERT_FAILED"),
    ("finalize", "LEASE_FINALIZE_FAILED"),
])
def test_failure_stops_later_operations(failure, classification):
    result = run_case(case_number=1, force_revision=True, failure=failure)
    assert result.failure_class == classification
    assert result.lease_events.index(result.failure_event) < len(result.lease_events)
    assert result.completed is False
```

The fixture assertions must verify job ID, six one-based indexes, exact
narration/caption/image prompt values, duration bounds, and valid motion and
transition values. Failure tests must assert no scene insertion or finalize
occurs after an earlier failure.

- [ ] **Step 2: Run tests and verify they fail for missing workflow behavior**

Run: `py -3 -m pytest -q tests/test_wf04_timing_harness.py`

Expected: the new tests fail because the fake adapters and `run_case` do not exist.

- [ ] **Step 3: Implement the minimal local workflow model**

Implement these standard-library-only pieces in `tests/wf04_timing_harness.py`:

- `FakeClock` with `now` and `advance(seconds)`; it never sleeps.
- `FakeProvider` accepting a delay list and returning structured six-scene fixtures; configurable malformed first response and failed revision.
- `InMemoryLeaseStore` recording `begin`, `reserve`, `heartbeat`, and `finalize`, with one injected failure point.
- `InMemorySceneStore` recording inserted rows and one injected insertion failure.
- `build_prompt`, `validate_script`, `word_bounds`, and `run_case` using the loaded `Wf04Contract` values.
- `HarnessResult` containing modeled duration, job ID, scenes, revision count, provider call count, lease events, failure classification, and completion state.

The first-pass response is valid for non-revision cases. Revision cases receive an invalid first response and a valid second response. Every error returns a classification and prevents subsequent operations.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `py -3 -m pytest -q tests/test_wf04_timing_harness.py`

Expected: all success, fixture, and failure-path tests pass.

- [ ] **Step 5: Commit the local workflow slice**

```text
git add tests/test_wf04_timing_harness.py tests/wf04_timing_harness.py
git commit -m "feat: model isolated WF04 stage execution"
```

### Task 3: Add deterministic 100-run measurement and lease decision

**Files:**
- Modify: `tests/test_wf04_timing_harness.py`
- Modify: `tests/wf04_timing_harness.py`

- [ ] **Step 1: Add failing tests for the 150-call trace and lease evaluation**

Add tests that assert:

```python
def test_measurement_runs_100_cases_with_150_provider_calls_and_50_revisions():
    measurement = measure_runs()
    assert measurement.run_count == 100
    assert measurement.revision_runs == 50
    assert measurement.provider_calls == 150
    assert measurement.provider_delay_counts == {0.350: 143, 4.207: 7}


def test_lease_decision_applies_fixed_twenty_percent_and_five_second_margin():
    assert lease_decision(modeled_worst=90.0, lease_seconds=120).confirmed is True
    assert lease_decision(modeled_worst=101.0, lease_seconds=120).confirmed is False
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `py -3 -m pytest -q tests/test_wf04_timing_harness.py`

Expected: measurement and lease-decision tests fail because those APIs are not implemented.

- [ ] **Step 3: Implement deterministic measurement and report serialization**

Implement `measure_runs()` with 50 first-pass and 50 revision cases. Use a seeded deterministic order containing exactly 143 `0.350` delays and 7 `4.207` delays across the 150 provider calls. Measure wall-clock runtime with `time.perf_counter()` around the loop, but calculate each result duration only from `FakeClock`.

Implement `lease_decision()` with the fixed pre-run rule: margin is `max(modeled_worst * 0.20, 5.0)`, and confirmation requires `120 >= modeled_worst + margin`. Implement `render_report(measurement)` with nearest-rank P50/P95, modeled worst, wall-clock seconds, provider counts, revision counts, safety margin, and limitations.

- [ ] **Step 4: Run the measurement tests and verify they pass**

Run: `py -3 -m pytest -q tests/test_wf04_timing_harness.py`

Expected: all harness tests pass, including exact 100/150/50 counts and lease calculations.

- [ ] **Step 5: Commit the measurement slice**

```text
git add tests/test_wf04_timing_harness.py tests/wf04_timing_harness.py
git commit -m "feat: measure modeled WF04 lease duration"
```

### Task 4: Run the harness and write the timing report

**Files:**
- Modify: `tests/wf04_timing_harness.py`
- Create: `docs/superpowers/reports/2026-08-03-wf04-local-timing-report.md`

- [ ] **Step 1: Run the standalone harness**

Run: `py -3 tests/wf04_timing_harness.py --runs 100 --seed 20260803`

Expected: stdout reports 100 runs, 50 revision runs, 150 provider calls, 143 calls at 0.350 seconds, 7 calls at 4.207 seconds, modeled P50/P95/worst, actual wall-clock runtime, and the lease decision.

- [ ] **Step 2: Capture the exact output in the report**

Write `docs/superpowers/reports/2026-08-03-wf04-local-timing-report.md` with the command, seed, counts, nearest-rank formula, modeled percentile values, modeled worst, wall-clock runtime, fixed margin calculation, final 120-second decision, fixture/insertion results, failure-path test result, and the explicit limitation that this does not validate production network, n8n scheduling, Supabase, containers, deployment, or unobserved provider tails.

- [ ] **Step 3: Run the full verification suite**

Run: `$env:PYTHONPATH='..'; py -3 -m pytest -q`

Expected: all existing and new tests pass, with no production workflow, migration, provider setting, Docker setting, n8n setting, or data changes.

- [ ] **Step 4: Inspect the final diff and status**

Run: `git diff --check` and `git status --short`.

Expected: no whitespace errors; only `tests/wf04_timing_harness.py`, `tests/test_wf04_timing_harness.py`, and `docs/superpowers/reports/2026-08-03-wf04-local-timing-report.md` are changed after the plan/design commits.

- [ ] **Step 5: Commit the report**

```text
git add tests/wf04_timing_harness.py tests/test_wf04_timing_harness.py docs/superpowers/reports/2026-08-03-wf04-local-timing-report.md
git commit -m "test: report local WF04 timing measurement"
```
