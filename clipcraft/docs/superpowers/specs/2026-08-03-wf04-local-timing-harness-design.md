# WF04 Local Timing Harness Design

## Goal

Measure the complete WF04 stage path locally, including validation, prompt
construction, one bounded word-count revision, scene insertion, and lease
bookkeeping, without contacting production, Supabase, n8n, or any provider.

## Isolation Boundary

The harness is a standalone Python test utility. It must not import a network
client, open a socket, invoke Docker, call n8n, read credentials, or connect to
Supabase. Provider calls, database operations, and lease operations are local
in-memory fakes. A safety test will inspect the harness source and exercise the
fake adapters to prove that no external boundary is used.

## Provider Latency Model

The repository retains summary measurements rather than the original raw
latency trace:

- P50: `350 ms`
- P95 and worst: `4.207 s`

The run uses a deterministic 150-call trace derived only from those measured
quantiles: 143 calls at `0.350 s` and 7 calls at `4.207 s`. There are 50
first-pass runs with one provider call each and 50 revision runs with two calls
each, for 150 calls total. The trace is seeded and recorded in the report so
the result is reproducible. This is an explicit quantile model, not a claim
that the unavailable raw distribution has been reconstructed.

## Simulated WF04 Path

Each run executes these local operations in order:

1. Validate a queued job request and its duration/scene-count inputs using
   constants extracted from the production WF04 workflow JSON and checked by a
   contract test.
2. Begin and reserve an in-memory stage lease.
3. Build the WF04 prompt using the same target-word and 92%-108% bounds used
   by the workflow.
4. Call the local provider fake and validate its structured script response.
5. Accept the first response when it satisfies the word-count bounds.
6. On designated revision runs, reject the first response, perform exactly one
   bounded revision call, and accept the valid response.
7. Insert the validated scenes into an in-memory repository.
8. Heartbeat and finalize the lease through the local lease fake.

The provider fake advances a monotonic simulated clock by the selected delay;
workflow bookkeeping and pure validation logic execute normally. No sleep is
used, so 100 runs remain fast while the reported duration is the modeled stage
duration.

## Measurement

The harness runs 100 deterministic cases. Fifty cases force one revision and
the other fifty take the accepted-first-response path. Provider delays follow
the fixed 150-call quantile trace. The report includes total runs, revision
runs, provider calls, modeled P50, modeled P95, modeled worst duration, and
actual harness wall-clock runtime as separate values.

Percentiles use the nearest-rank method. Durations are sorted ascending and
the value at one-based rank `ceil(p * N)` is selected. For 100 runs, P50 is
rank 50 and P95 is rank 95. The modeled duration is the fake monotonic clock
total for each run; wall-clock runtime is measured separately around the test
runner and is not used for lease sizing.

The lease safety margin is fixed before execution at 20% of the modeled worst
case, with a minimum margin of 5 seconds. The safety requirement is therefore
`120 >= modeled_worst * 1.20` and `120 >= modeled_worst + 5 seconds`. This
numeric rule is applied to the measured modeled duration without tuning after
the result is known.

Lease evaluation uses both checks:

- P95 must remain below 120 seconds with the fixed margin.
- The measured modeled worst case must remain below 120 seconds with the fixed
  20%/5-second margin.

If both pass, the cutover design marks `120 seconds` confirmed. Otherwise the
design proposes the smallest whole-second lease that satisfies the same fixed
margin rule and explains the calculation.

The conclusion validates only the modeled local WF04 path. It does not validate
production provider network latency, n8n scheduling or queue contention,
Supabase latency, container scheduling, deployment overhead, or unobserved
provider-tail latency.

## Failure-Path Coverage

Non-timing tests must cover malformed provider responses, a failed revision,
lease begin/reserve/heartbeat/finalize errors, scene insertion errors, and
finalization errors. Each test must assert the returned failure classification
and that no later stage operation occurs after the failure.

The structured fixture contains a 60-second job with six scenes. Each scene
has a one-based `index`, non-empty `narration`, `caption`, and `imagePrompt`, a
duration from the production contract, and valid `motion` and `transition`
values. The in-memory scene repository must assert six inserted rows, indexes
`1..6`, the exact job ID, preserved narration/caption/image prompt values,
and the validated duration/motion/transition fields.

Word-count bounds and related values must be loaded from the WF04 production
workflow source or verified against it by a contract assertion. The harness
must fail closed if the expected production constants cannot be found or do
not match the contract values; it may not silently maintain independent values.

## Files

- `tests/test_wf04_timing_harness.py`: unit and isolation tests.
- `tests/wf04_timing_harness.py`: standalone local harness and report output.
- `docs/superpowers/reports/2026-08-03-wf04-local-timing-report.md`: measured
  results and lease decision.

No production workflow, migration, provider configuration, n8n setting, Docker
setting, or production data may change as part of this checkpoint. The harness
may read the repository WF04 JSON as a local contract source only.
