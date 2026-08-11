# WF04 Local Timing Harness Report

## Run

Command:

```text
py -3 tests/wf04_timing_harness.py --runs 100 --seed 20260803
```

The harness is fully local. It uses an in-memory fake clock, provider, lease
store, and scene store. It does not import a network client, open a socket,
read credentials, invoke Docker or n8n, connect to Supabase, or call a real
provider. The repository WF04 JSON is read only to contract-check production
constants.

## Modeled Results

- Runs: `100`
- First-pass runs: `50`
- One-revision runs: `50`
- Provider calls: `150`
- Provider delay counts: `143` calls at `0.350s`; `7` calls at `4.207s`
- Modeled P50: `0.700s`
- Modeled P95: `4.207s`
- Modeled worst: `4.557s`
- Harness wall-clock runtime for this invocation: `0.070113s`

The provider-call count is `50 * 1 + 50 * 2 = 150`. The delay trace is a
deterministic quantile model based only on the retained measurements of P50
`350ms` and P95/worst `4.207s`; the unavailable raw provider trace was not
reconstructed.

Percentiles use nearest rank: sort the 100 modeled durations and select the
one-based element at `ceil(p * N)`. Therefore P50 is rank 50 and P95 is rank
95. Modeled duration comes only from the fake monotonic clock. Wall-clock
runtime is reported separately and is not used for lease sizing.

## Lease Decision

The safety margin was fixed before the run at `max(20% of modeled worst, 5s)`.
For the measured worst case:

```text
max(4.557s * 0.20, 5s) = 5s
4.557s + 5s = 9.557s
```

The `120s` lease comfortably exceeds both the modeled P95 plus margin and the
modeled worst plus margin. The lease duration is therefore **CONFIRMED for the
modeled local WF04 path** and is no longer provisional for that model.

## Path and Failure Coverage

The successful fixture runs validate prompt construction, contract-sourced
word bounds, one bounded revision, six structured scenes, in-memory insertion,
heartbeat, and finalization. Tests also cover malformed responses, failed
revision, begin/reserve/heartbeat/finalize lease errors, scene insertion
errors, and finalization errors, asserting that later operations do not run.
The repository test suite passes with `107 passed` using `py -3 -m pytest -q tests`.

## Scope Limitation

This result validates only the modeled local WF04 path. It does not validate
production provider network latency, n8n scheduling or queue contention,
Supabase latency, container scheduling, deployment overhead, or unobserved
provider-tail latency. No production workflow, migration, provider
configuration, n8n setting, Docker setting, or production data changed.
