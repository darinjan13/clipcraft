# Checkpoint 1B Lease Safety Validation

Date: 2026-08-03

## Recommendation

SAFE_TO_APPLY for the Checkpoint 1B migration and rollback. The focused
contracts, full foundation contracts, and disposable PostgreSQL validation all
pass. The broader repository suite retains unrelated pre-existing failures
listed below.

## Commands And Results

Focused Checkpoint 1B contracts:

```text
pytest -q tests/test_foundation_contracts.py -k "checkpoint_1b or lease_reconciliation"
..............                                                           [100%]
14 passed, 17 deselected in 0.14s
```

Full foundation contracts:

```text
pytest -q tests/test_foundation_contracts.py
...............................                                          [100%]
31 passed in 0.24s
```

Disposable harness: `tests/test_checkpoint_1b_ephemeral.ps1`

```text
PASS psql select 1 readiness probe
EXPECTED FAIL video_jobs_attempt_number_forward_check
EXPECTED FAIL video_jobs_pipeline_revision_forward_check
EXPECTED FAIL video_jobs_max_job_attempts_forward_check
EXPECTED FAIL video_jobs_attempt_number_forward_check
EXPECTED FAIL video_jobs_pipeline_revision_forward_check
EXPECTED FAIL video_jobs_max_job_attempts_forward_check
PASS future forward checks reject null and invalid values
PASS normal expired lease reaping
PASS max-attempt expired lease failure
PASS repeated reaping processes one lease once
PASS concurrent reaper barrier lock granted
PASS concurrent reaper processes one lease once
PASS claim limit failure and normalization
PASS fenced claim normalizes and initializes legacy fields
PASS release requeue preserves stage and clears lease
PASS legacy nullable release normalizes fields and clears lease
PASS completed-stage release and immediate next-stage claim
EXPECTED FAIL LEASE_LOST
EXPECTED FAIL INVALID_RELEASE_OUTCOME
EXPECTED FAIL INVALID_NEXT_STAGE
PASS stale token and invalid input rejection
EXPECTED FAIL INVALID_LEASE_SECONDS
EXPECTED FAIL INVALID_BATCH_SIZE
EXPECTED FAIL INVALID_NEXT_STAGE
EXPECTED FAIL JOB_TERMINAL
PASS additional failure paths preserve full job state
EXPECTED FAIL LEASE_LOST
PASS expired release rejects token and preserves state
PASS legacy claim and fenced grants
EXPECTED FAIL ACTIVE_FENCED_LEASES_EXIST
PASS rollback guard refuses active fenced lease
PASS safe rollback preserves Checkpoint 1A objects
PASS all Checkpoint 1B ephemeral validation
PASS container removed and verified absent
```

Full repository suite:

```text
pytest -q tests
```

Collection stops on the known unrelated import failure:

```text
ModuleNotFoundError: No module named 'clipcraft'
tests/test_smoke_safety.py
```

The suite excluding only that collector failure produced:

```text
pytest -q tests --ignore=tests/test_smoke_safety.py
67 passed, 2 failed
```

The two failures are unrelated workflow contract failures:

- `test_content_generation_parameters_remain_stable_and_event_logging_is_non_blocking`
- `test_wf17_internal_attempts_have_valid_request_ids_without_caller_changes`

Neither workflow nor unrelated test code was modified.

## Migration Behavior

- `max_job_attempts` defaults to 3 for future writes without backfilling legacy NULLs.
- Forward-only `NOT VALID` checks constrain future attempt, revision, and limit values.
- Fenced claim enforces the maximum acquisition count, normalizes touched legacy rows, and returns an explicit approved job projection.
- Expired lease reaping uses bounded `FOR UPDATE SKIP LOCKED` batches, increments attempts once, normalizes touched legacy fields, clears leases, and either queues or fails jobs.
- Sequential and two-session concurrent reaper validation each processed one expired lease exactly once; the losing concurrent session reported zero additional work.
- Release validates the token and outcome, normalizes valid touched legacy rows, preserves explicit stage semantics, and clears all lease fields.

## Rollback

The guarded down migration rejected an active fenced lease with
`ACTIVE_FENCED_LEASES_EXIST`. After disposable cleanup it succeeded, removed
Checkpoint 1B functions, defaults, constraints, and limit column, and verified
that Checkpoint 1A lease columns, fenced indexes, `job_stage_runs`, legacy
claim, fenced claim, heartbeat, and service-role grants remained.
Rollback runs in one explicit transaction, takes an `ACCESS EXCLUSIVE` lock on
`public.video_jobs` before the active-lease guard, and keeps that lock through
all restoration and destructive drops.

## Safety Boundary

No production database, production URL, migration repair, n8n workflow,
provider mode, or real video job was touched. All SQL validation used a
uniquely named disposable local `postgres:17` container, which was removed and
verified absent. The new Checkpoint 1B RPCs have zero live production callers
until WF04 is separately updated. Local repository references and validation
harness calls are test artifacts, not live production callers.

## Git Tracking

The workspace is not inside a Git repository. `git rev-parse --show-toplevel`
returned:

```text
fatal: not a git repository (or any of the parent directories): .git
```

Read-only parent-directory inspection found no repository root for this
workspace, and `.git` discovery found no `.git` directory. Git initialization
was not performed.
