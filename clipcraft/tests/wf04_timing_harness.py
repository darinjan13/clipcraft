"""Fully local WF04 timing model; never contacts external services."""

from __future__ import annotations

import math
import re
import random
import time
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class Wf04Contract:
    voice_words_per_minute: int
    minimum_word_ratio: float
    maximum_word_ratio: float
    minimum_scene_duration: int
    maximum_scene_duration: int


def normalize_scene_durations(scenes: list[dict[str, Any]], requested_duration: int) -> list[dict[str, Any]]:
    """Normalize scene durations to sum exactly to requested_duration.
    
    Mirrors the JS logic in WF04 Validate Output:
    - Proportional scaling with min floor of 2s
    - Largest-remainder rounding to exact total
    - Preserves 2-10s range when feasible (in-range = n*10 >= target >= n*2)
    - Allows exceeding 10s when scene count is too low to reach target within 10s cap
    """
    if not scenes or not isinstance(requested_duration, (int, float)) or requested_duration <= 0:
        return scenes
    
    n = len(scenes)
    min_per = 2
    max_per = 10
    
    # Current durations (already clamped to [2,10] in the JS)
    current = [max(min_per, int(s.get("durationSeconds", 0) or min_per)) for s in scenes]
    current_total = sum(current)
    
    if abs(current_total - requested_duration) <= 0.01:
        return scenes
    
    # Determine if we can fit within [min_per, max_per]
    in_range = n * max_per >= requested_duration and n * min_per <= requested_duration
    cap = max_per if in_range else float('inf')
    
    # Proportional scale
    scale = requested_duration / max(current_total, n * min_per)
    allocated = [max(min_per, min(cap, c * scale)) for c in current]
    
    # Largest-remainder rounding to exact total
    floored = [math.floor(d) for d in allocated]
    used = sum(floored)
    remainder = requested_duration - used
    
    # Distribute remainder by largest fractional parts
    by_frac = sorted([(d - math.floor(d), i) for i, d in enumerate(allocated)], reverse=True)
    for k in range(remainder):
        _, idx = by_frac[k % n]
        floored[idx] += 1
    
    # Apply back to scenes
    result = []
    for i, s in enumerate(scenes):
        result.append({**s, "durationSeconds": floored[i]})
    return result


def _workflow_source() -> str:
    return (Path(__file__).resolve().parents[1] / "workflows" / "04-generate-script-and-scenes.json").read_text(encoding="utf-8")


def load_wf04_contract() -> Wf04Contract:
    source = _workflow_source()
    required = (
        r"'Warm narrator': 140",
        r"'Studio neutral': 132",
        r"'Energetic guide': 132",
        r"Math\.floor\(targetWords \* 0\.98\)",
        r"Math\.ceil\(targetWords \* 1\.02\)",
        r"Math\.max\(2,Math\.min\(10,",
    )
    if any(re.search(pattern, source) is None for pattern in required):
        raise ContractError("WF04 production constants are missing or changed")
    return Wf04Contract(140, 0.98, 1.02, 2, 10)


def nearest_rank(values: list[float], percentile: float) -> float:
    if not values or not 0 < percentile <= 1:
        raise ValueError("nearest-rank input is invalid")
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


SCENE_NARRATIONS = [
    "Scene one narration. " * 7,
    "Scene one narration. " * 7,
    "Scene one narration. " * 8,
    "Scene one narration. " * 8,
    "Scene one narration. " * 8,
    "Scene one narration. " * 8,
]
SCENE_CAPTIONS = [f"Scene {name}." for name in ("one", "two", "three", "four", "five", "six")]
SCENE_PROMPTS = [f"Image {name}." for name in ("one", "two", "three", "four", "five", "six")]


class HarnessFailure(RuntimeError):
    def __init__(self, classification: str, event: str):
        super().__init__(classification)
        self.classification = classification
        self.event = event


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _script_fixture(valid: bool = True) -> dict[str, Any]:
    narrations = SCENE_NARRATIONS if valid else ["too short. "] * 6
    return {
        "title": "A local timing fixture",
        "description": "A deterministic local timing fixture.",
        "scenes": [
            {
                "index": index,
                "narration": narrations[index - 1],
                "caption": SCENE_CAPTIONS[index - 1],
                "imagePrompt": SCENE_PROMPTS[index - 1],
                "durationSeconds": 10,
                "motion": "zoom_in",
                "transition": "crossfade",
            }
            for index in range(1, 7)
        ],
    }


class FakeProvider:
    def __init__(self, delays: list[float]):
        self.delays = list(delays)
        self.calls = 0
        self.clock: FakeClock | None = None
        self.invalid_calls: set[int] = set()
        self.malformed_calls: set[int] = set()

    def call(self) -> dict[str, Any]:
        self.calls += 1
        if self.clock is None:
            raise RuntimeError("FakeProvider requires a local clock")
        self.clock.advance(self.delays[self.calls - 1])
        if self.calls in self.malformed_calls:
            return {"unexpected": "shape"}
        return _script_fixture(valid=self.calls not in self.invalid_calls)


class InMemoryLeaseStore:
    def __init__(self, failure: str | None):
        self.failure = failure
        self.events: list[str] = []

    def _event(self, name: str, classification: str) -> None:
        self.events.append(name)
        if self.failure == name:
            raise HarnessFailure(classification, name)

    def begin(self) -> None:
        self._event("begin", "LEASE_BEGIN_FAILED")

    def reserve(self) -> None:
        self._event("reserve", "LEASE_RESERVE_FAILED")

    def heartbeat(self) -> None:
        self._event("heartbeat", "LEASE_HEARTBEAT_FAILED")

    def finalize(self) -> None:
        self._event("finalize", "LEASE_FINALIZE_FAILED")


class InMemorySceneStore:
    def __init__(self, failure: str | None):
        self.failure = failure
        self.rows: list[dict[str, Any]] = []

    def insert(self, rows: list[dict[str, Any]]) -> None:
        if self.failure == "scene_insert":
            raise HarnessFailure("SCENE_INSERT_FAILED", "scene_insert")
        self.rows.extend(rows)


@dataclass
class HarnessResult:
    job_id: str
    modeled_duration: float
    scenes: list[dict[str, Any]]
    revision_count: int
    provider_calls: int
    lease_events: list[str]
    failure_class: str | None
    failure_event: str | None
    scene_inserted: bool
    completed: bool


@dataclass
class LeaseDecision:
    modeled_worst: float
    margin: float
    lease_seconds: int
    confirmed: bool


@dataclass
class Measurement:
    run_count: int
    revision_runs: int
    provider_calls: int
    provider_delay_counts: dict[float, int]
    durations: list[float]
    wall_clock_seconds: float


def word_bounds(contract: Wf04Contract, requested_duration: int) -> tuple[int, int]:
    target = round(requested_duration * contract.voice_words_per_minute / 60)
    return (
        math.floor(target * contract.minimum_word_ratio),
        math.ceil(target * contract.maximum_word_ratio),
    )


def build_prompt(contract: Wf04Contract, requested_duration: int, scene_count: int) -> dict[str, int]:
    minimum, maximum = word_bounds(contract, requested_duration)
    return {
        "requested_duration": requested_duration,
        "scene_count": scene_count,
        "minimum_words": minimum,
        "maximum_words": maximum,
    }


def validate_script(script: dict[str, Any], contract: Wf04Contract, requested_duration: int) -> None:
    if not script.get("title") or not script.get("description") or not isinstance(script.get("scenes"), list):
        raise HarnessFailure("PROVIDER_RESPONSE_INVALID", "provider_validate")
    minimum, maximum = word_bounds(contract, requested_duration)
    narration = " ".join(str(scene.get("narration", "")) for scene in script["scenes"])
    words = len(narration.split())
    if not minimum <= words <= maximum:
        raise HarnessFailure("WORD_COUNT_INVALID", "word_count")
    if len(script["scenes"]) != 6:
        raise HarnessFailure("PROVIDER_RESPONSE_INVALID", "provider_validate")
    for expected_index, scene in enumerate(script["scenes"], start=1):
        if scene.get("index") != expected_index or not scene.get("caption") or not scene.get("imagePrompt"):
            raise HarnessFailure("PROVIDER_RESPONSE_INVALID", "provider_validate")
        if not contract.minimum_scene_duration <= scene.get("durationSeconds", 0) <= contract.maximum_scene_duration:
            raise HarnessFailure("PROVIDER_RESPONSE_INVALID", "provider_validate")
        if scene.get("motion") not in {"zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"}:
            raise HarnessFailure("PROVIDER_RESPONSE_INVALID", "provider_validate")
        if scene.get("transition") not in {"fade", "crossfade", "slide_left", "slide_right"}:
            raise HarnessFailure("PROVIDER_RESPONSE_INVALID", "provider_validate")


def run_case(
    case_number: int,
    force_revision: bool,
    provider: FakeProvider | None = None,
    failure: str | None = None,
) -> HarnessResult:
    contract = load_wf04_contract()
    clock = FakeClock()
    provider = provider or FakeProvider([0.350, 4.207])
    provider.clock = clock
    lease = InMemoryLeaseStore(failure)
    scenes = InMemorySceneStore(failure)
    job_id = f"timing-fixture-{case_number:03d}"
    revision_count = 0
    failure_class = None
    failure_event = None
    scene_inserted = False
    result_scenes: list[dict[str, Any]] = []

    if failure == "malformed_response":
        provider.malformed_calls.add(1)
    elif failure == "failed_revision":
        provider.malformed_calls.add(2)

    try:
        lease.begin()
        lease.reserve()
        build_prompt(contract, 60, 6)
        if force_revision:
            provider.invalid_calls.add(1)
        script = provider.call()
        try:
            validate_script(script, contract, 60)
        except HarnessFailure as error:
            if not force_revision or failure == "malformed_response":
                raise
            revision_count = 1
            script = provider.call()
            try:
                validate_script(script, contract, 60)
            except HarnessFailure as revision_error:
                raise HarnessFailure("REVISION_FAILED", "revision") from revision_error
        result_scenes = [
            dict(
                scene,
                job_id=job_id,
                image_prompt=scene["imagePrompt"],
                duration_seconds=scene["durationSeconds"],
            )
            for scene in script["scenes"]
        ]
        scenes.insert(result_scenes)
        scene_inserted = True
        lease.heartbeat()
        lease.finalize()
    except HarnessFailure as error:
        failure_class = error.classification
        failure_event = error.event

    return HarnessResult(
        job_id=job_id,
        modeled_duration=clock.now,
        scenes=scenes.rows,
        revision_count=revision_count,
        provider_calls=provider.calls,
        lease_events=lease.events,
        failure_class=failure_class,
        failure_event=failure_event,
        scene_inserted=scene_inserted,
        completed=failure_class is None,
    )


def lease_decision(modeled_worst: float, lease_seconds: int = 120) -> LeaseDecision:
    margin = max(modeled_worst * 0.20, 5.0)
    return LeaseDecision(
        modeled_worst=modeled_worst,
        margin=margin,
        lease_seconds=lease_seconds,
        confirmed=lease_seconds >= modeled_worst + margin,
    )


def measure_runs(runs: int = 100, seed: int = 20260803) -> Measurement:
    if runs != 100:
        raise ValueError("the timing protocol requires exactly 100 runs")
    trace = [0.350] * 143 + [4.207] * 7
    random.Random(seed).shuffle(trace)
    cursor = 0
    durations = []
    revisions = 0
    provider_calls = 0
    started = time.perf_counter()
    for case_number in range(1, runs + 1):
        force_revision = case_number <= 50
        call_count = 2 if force_revision else 1
        provider = FakeProvider(trace[cursor : cursor + call_count])
        cursor += call_count
        result = run_case(case_number, force_revision, provider)
        if not result.completed:
            raise RuntimeError(f"measurement case failed: {result.failure_class}")
        durations.append(result.modeled_duration)
        revisions += result.revision_count
        provider_calls += result.provider_calls
    return Measurement(
        run_count=runs,
        revision_runs=revisions,
        provider_calls=provider_calls,
        provider_delay_counts={0.350: trace.count(0.350), 4.207: trace.count(4.207)},
        durations=durations,
        wall_clock_seconds=time.perf_counter() - started,
    )


def render_report(measurement: Measurement) -> str:
    p50 = nearest_rank(measurement.durations, 0.50)
    p95 = nearest_rank(measurement.durations, 0.95)
    worst = max(measurement.durations)
    decision = lease_decision(worst)
    status = "CONFIRMED" if decision.confirmed else "NOT CONFIRMED"
    return "\n".join(
        [
            "WF04 local modeled timing harness",
            f"Runs: {measurement.run_count}",
            f"Revision runs: {measurement.revision_runs}",
            f"Provider calls: {measurement.provider_calls}",
            f"Provider delay counts: {measurement.provider_delay_counts}",
            "Percentile method: nearest rank, sorted values, rank ceil(p * N)",
            f"Modeled P50: {p50:.3f}s",
            f"Modeled P95: {p95:.3f}s",
            f"Modeled worst: {worst:.3f}s",
            f"Harness wall-clock runtime: {measurement.wall_clock_seconds:.6f}s",
            f"Safety margin: {decision.margin:.3f}s (max(20% of worst, 5s))",
            f"120-second lease: {status}",
            "Scope: validates only the modeled local WF04 path; it does not validate production network, n8n scheduling, Supabase, container scheduling, deployment overhead, or unobserved provider-tail latency.",
            "Isolation: no provider, database, n8n, Docker, credential, or network calls are used.",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the isolated local WF04 timing model")
    parser.add_argument("--runs", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()
    print(render_report(measure_runs(args.runs, args.seed)))


if __name__ == "__main__":
    main()
