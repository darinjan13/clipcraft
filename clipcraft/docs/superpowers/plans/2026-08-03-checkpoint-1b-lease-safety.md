# Checkpoint 1B Lease Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and ephemerally validate the four lease-safety capabilities required before WF04 cutover, without changing production or n8n.

**Architecture:** Add one forward migration on top of Checkpoint 1A and one guarded rollback outside the active migration directory. The migration adds forward-only attempt invariants, a row-locking expired-lease reaper, and an explicit token-validated release RPC while preserving the legacy claim RPC and all Checkpoint 1A objects.

**Tech Stack:** PostgreSQL 17, Supabase SQL, Python `pytest` static contract tests, PowerShell/Docker ephemeral validation.

---

## Files

- Create: `supabase/migrations/20260803120000_checkpoint_1b_lease_safety_rpcs.sql`
  - Adds `max_job_attempts`, forward-only constraints, the reaper, the release RPC, and the updated fenced claim function.
- Create: `supabase/migrations_rollback/20260803120000_checkpoint_1b_lease_safety_rpcs.down.sql`
  - Guards active leases and removes only Checkpoint 1B objects.
- Modify: `tests/test_foundation_contracts.py`
  - Point existing archived migration and rollback constants at their actual archive paths and add static Checkpoint 1B contract assertions.
- Create: `tests/test_checkpoint_1b_ephemeral.ps1`
  - Optional reproducible Docker/`psql` integration harness for the disposable PostgreSQL 17 validation.
- Create: `docs/superpowers/reports/2026-08-03-checkpoint-1b-lease-safety.md`
  - Records commands, test outputs, rollback results, and the final recommendation.

## Task 1: Write Failing Contract Tests

**Files:**
- Modify: `tests/test_foundation_contracts.py`

- [ ] Add constants pointing at the active Checkpoint 1A file, the new Checkpoint 1B file, and both rollback files. Keep archived `004`/`005` references under `supabase/migrations_archive/` rather than restoring them to the active directory.
- [ ] Add tests that initially fail because the new migration does not exist:

```python
CHECKPOINT_1B = ROOT / "clipcraft" / "supabase" / "migrations" / "20260803120000_checkpoint_1b_lease_safety_rpcs.sql"
CHECKPOINT_1B_DOWN = ROOT / "clipcraft" / "supabase" / "migrations_rollback" / "20260803120000_checkpoint_1b_lease_safety_rpcs.down.sql"

def test_checkpoint_1b_declares_bounded_lease_safety_contract():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    assert "add column if not exists max_job_attempts integer" in sql
    assert "reap_expired_video_job_leases" in sql
    assert "release_video_job" in sql
    assert "lease_expired_max_attempts" in sql
    assert "for update skip locked" in sql
    assert "revoke all on function public.reap_expired_video_job_leases" in sql
    assert "revoke all on function public.release_video_job" in sql
    assert "create or replace function public.claim_next_video_job(" not in sql

def test_checkpoint_1b_has_forward_only_invariants_and_guarded_rollback():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    down = CHECKPOINT_1B_DOWN.read_text(encoding="utf-8").lower()
    assert "default 3" in sql
    assert "not valid" in sql
    assert "active_fenced_leases_exist" in down
    assert "drop function if exists public.reap_expired_video_job_leases" in down
    assert "drop function if exists public.release_video_job" in down
    assert "drop column if exists max_job_attempts" in down
```

- [ ] Run the focused tests and confirm they fail only because the new files and declarations are absent:

```powershell
pytest -q tests/test_foundation_contracts.py -k checkpoint_1b
```

Expected result: failures for missing Checkpoint 1B files.

## Task 2: Implement the Checkpoint 1B Migration

**Files:**
- Create: `supabase/migrations/20260803120000_checkpoint_1b_lease_safety_rpcs.sql`

- [ ] Add `max_job_attempts integer`, set its default to `3`, and add a forward-only non-null/positive validation strategy that does not update existing legacy rows. Add forward-only `attempt_number` and `pipeline_revision` checks with defaults for future writes. Keep `next_stage` nullable.
- [ ] Preserve nullable historical values by using `NOT VALID` checks where a direct `SET NOT NULL` would reject existing rows. The fenced claim and reaper must normalize null attempt/revision/limit values before writing a touched row.
- [ ] Replace only `claim_next_video_job_fenced(text, integer)` and enforce the acquisition limit without modifying `claim_next_video_job(text)`. A row whose current attempt is already at the configured limit must be failed with a clear `LEASE_EXPIRED_MAX_ATTEMPTS` state rather than claimed again.
- [ ] Implement `reap_expired_video_job_leases(p_batch_size integer default 100)` with this exact transaction behavior:

```sql
for job in
  select *
  from public.video_jobs
  where lease_token is not null
    and lease_expires_at < now()
    and status not in ('completed', 'failed', 'cancelled')
  order by lease_expires_at asc
  limit greatest(1, least(p_batch_size, 1000))
  for update skip locked
loop
  next_attempt := coalesce(job.attempt_number, 0) + 1;
  if next_attempt >= coalesce(job.max_job_attempts, 3) then
    update public.video_jobs
    set attempt_number = next_attempt,
        status = 'failed',
        current_step = 'failed',
        failure_class = 'LEASE_EXPIRED_MAX_ATTEMPTS',
        error_message = 'LEASE_EXPIRED_MAX_ATTEMPTS',
        finished_at = now(),
        claimed_by = null,
        claimed_at = null,
        lease_token = null,
        lease_expires_at = null,
        heartbeat_at = null,
        updated_at = now()
    where id = job.id;
    failed_count := failed_count + 1;
  else
    update public.video_jobs
    set attempt_number = next_attempt,
        status = 'queued',
        current_step = coalesce(job.next_stage, job.current_step, 'queued'),
        claimed_by = null,
        claimed_at = null,
        lease_token = null,
        lease_expires_at = null,
        heartbeat_at = null,
        updated_at = now()
    where id = job.id;
    reaped_count := reaped_count + 1;
  end if;
end loop;
```

- [ ] Return `jsonb_build_object('reaped_count', reaped_count, 'failed_count', failed_count)` and grant execution only to `service_role` after revoking `public`, `anon`, and `authenticated`.
- [ ] Implement `release_video_job(uuid, uuid, text, text default null)` using `select ... for update`, exact lease-token equality, explicit outcome validation, and `LEASE_LOST` for stale/mismatched tokens. For `completed_stage`, capture `coalesce(next_stage, current_step)` into `last_completed_stage`, set `next_stage = p_next_stage`, set `current_step = p_next_stage`, clear the lease, and either set terminal `completed` or queue the supplied next stage. For `requeue`, reject a non-null next stage, preserve the current stage, clear the lease, and queue the job.
- [ ] Add the same service-role-only grants/revokes for `release_video_job`.

## Task 3: Implement Guarded Rollback

**Files:**
- Create: `supabase/migrations_rollback/20260803120000_checkpoint_1b_lease_safety_rpcs.down.sql`

- [ ] Add a guard that raises `ACTIVE_FENCED_LEASES_EXIST` if any nonterminal row has a non-null lease token.
- [ ] Drop only Checkpoint 1B functions, constraints, and `max_job_attempts`; do not drop Checkpoint 1A columns, `job_stage_runs`, fenced claim, heartbeat, or legacy claim objects.
- [ ] Drop only Checkpoint 1B indexes/constraints introduced by the migration.

## Task 4: Run Static Tests

**Files:**
- Modify: `tests/test_foundation_contracts.py`

- [ ] Run:

```powershell
pytest -q tests/test_foundation_contracts.py -k "checkpoint_1b or lease_reconciliation"
```

Expected result: all Checkpoint 1B and existing Checkpoint 1A contract tests pass.

- [ ] Run the complete static suite:

```powershell
pytest -q tests
```

Record any failures before proceeding to database validation.

## Task 5: Validate on Disposable PostgreSQL 17

**Files:**
- Create: `tests/test_checkpoint_1b_ephemeral.ps1`

- [ ] Start a uniquely named disposable `postgres:17` container with a temporary password, wait for readiness, and always remove it in a `finally` block.
- [ ] Apply baseline migrations `001` through `003` from `supabase/migrations_archive/`, `20260727134852_simple_processing_lifecycle.sql`, `006_add_soft_delete.sql`, Checkpoint 1A, and Checkpoint 1B using `psql -v ON_ERROR_STOP=1`.
- [ ] Create service-role fixtures and seed isolated test jobs; do not connect to the production URL.
- [ ] Verify normal reaping: an expired nonterminal lease is requeued, lease fields are cleared, and `attempt_number` increments once.
- [ ] Verify max-attempt reaping: a job at `max_job_attempts - 1` becomes `failed` with `failure_class = 'LEASE_EXPIRED_MAX_ATTEMPTS'`, not queued.
- [ ] Verify repeated/concurrent reaping with two database sessions or two sequential calls: the same expired lease is processed once and the second call reports no additional work.
- [ ] Verify claim enforcement: a queued job already at its limit is atomically transitioned to `failed` with `failure_class = 'LEASE_EXPIRED_MAX_ATTEMPTS'`, the RPC returns `claimed = false` with that failure classification, and no acquisition exceeds the configured maximum.
- [ ] Verify release `requeue`: valid token clears all lease fields, returns the job to `queued`, and preserves `next_stage`.
- [ ] Verify release `completed_stage`: valid token records the prior stage, sets the explicit next stage, clears the lease, and leaves the job immediately claimable by `claim_next_video_job_fenced` for that new stage. Assert the subsequent claim returns the expected job/stage and a new lease token.
- [ ] Verify stale-token release raises `LEASE_LOST` and leaves status, stage, and lease token unchanged.
- [ ] Verify invalid outcome and invalid next-stage inputs fail without mutation.
- [ ] Verify legacy `claim_next_video_job(text)` still exists and can claim a separate legacy fixture. Verify Checkpoint 1A fenced claim remains callable by `service_role` and unavailable to `anon`/`authenticated`.
- [ ] Execute the Checkpoint 1B down migration with an active fenced lease and assert `ACTIVE_FENCED_LEASES_EXIST`.
- [ ] Clear/terminalize only disposable test leases, execute the down migration, and verify Checkpoint 1B functions, column, constraints, and indexes are removed while Checkpoint 1A fenced objects remain.
- [ ] Remove the disposable container and record the exact command outputs in the report.

## Task 6: Produce the Validation Report

**Files:**
- Create: `docs/superpowers/reports/2026-08-03-checkpoint-1b-lease-safety.md`

- [ ] Record the migration paths, default/attempt semantics, SQL validation results, failure-path results, post-release claimability result, rollback guard/result, and container teardown.
- [ ] Mark the recommendation `SAFE_TO_APPLY` only if static tests and all ephemeral cases pass. Otherwise mark `NEEDS_CHANGES_FIRST` with the exact failing case.
- [ ] Explicitly state that no production SQL, migration repair, n8n workflow, provider mode, or real job was touched and that the new RPCs have zero live callers until WF04 is separately updated.
- [ ] Separately report git tracking findings using read-only checks (`git rev-parse --show-toplevel`, parent-directory inspection, and `.git` discovery). Do not initialize Git or create files for Git tracking.

## Self-Review Checklist

- [ ] Confirm the plan covers every approved spec section: bounded attempts, reaping, explicit release, forward-only invariants, rollback guard, ephemeral validation, and no production changes.
- [ ] Confirm the added post-release claimability test is present.
- [ ] Confirm no task modifies WF04, another workflow, provider mode, migration history, or production state.
- [ ] Confirm no `TODO`, `TBD`, or unspecified behavior remains in the implementation steps.
