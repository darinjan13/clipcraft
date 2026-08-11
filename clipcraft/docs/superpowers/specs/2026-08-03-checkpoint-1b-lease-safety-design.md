# Checkpoint 1B Lease Safety Design

## Goal

Add the four lease-safety capabilities required before WF04 can use
`claim_next_video_job_fenced`, without applying anything to production or
touching n8n workflows:

- bounded lease acquisitions through `max_job_attempts`;
- expired-lease reaping;
- explicit token-validated lease release;
- forward-only invariants for `attempt_number` and `pipeline_revision`.

Checkpoint 1B is one additive migration, paired with a guarded down migration,
and validated against a disposable PostgreSQL 17 database.

## Decisions

- Use an additive migration rather than reviving archived migration `004`.
- Set `max_job_attempts` default to `3`, matching the existing `max_retries`
  default of `2` when interpreted as two retries after the initial acquisition.
- Interpret `max_job_attempts` as the maximum number of lease acquisitions.
- On expiry, increment the acquisition count exactly once. If
  `next_attempt >= max_job_attempts`, fail the job with
  `failure_class = 'LEASE_EXPIRED_MAX_ATTEMPTS'`; otherwise requeue it.
- Keep `next_stage` nullable. A legacy job may not yet have a resume stage;
  fenced claim initializes it to `generate_script` when it first claims the
  job.
- Use an explicit next-stage argument for completed-stage release:

  ```sql
  release_video_job(
    p_job_id uuid,
    p_lease_token uuid,
    p_outcome text,
    p_next_stage text default null
  )
  ```

- `completed_stage` requires a valid `p_next_stage` from:
  `generate_script`, `generate_images`, `generate_voice`, `build_captions`,
  `build_manifest`, `render`, or `completed`.
- `requeue` clears the lease and returns the job to `queued` without advancing
  `next_stage`; a non-null `p_next_stage` is rejected for this outcome.
- Stale or mismatched release tokens raise `LEASE_LOST`; they never silently
  no-op.
- New functions are executable only by `service_role`. The legacy
  `claim_next_video_job(worker_id text)` function is not changed.

## Migration Behavior

### Attempt limits

Add `video_jobs.max_job_attempts integer` with default `3`. Existing historical
rows must not be backfilled based on assumptions. The migration therefore uses
the existing nullable columns safely while adding forward-only validation:

- set the default for new rows;
- add non-negative checks as appropriate;
- use `NOT VALID` checks where required so existing legacy nulls are not
  retroactively rejected while future inserts and updates are constrained;
- update fenced claim and reaper paths so a job cannot be acquired beyond its
  configured maximum.

### Expired lease reaper

Create `reap_expired_video_job_leases(p_batch_size integer default 100)`.

The function selects nonterminal jobs with expired leases using
`FOR UPDATE SKIP LOCKED`, bounded by `p_batch_size`. Each selected row is
processed once in the transaction:

- increment `attempt_number`;
- clear `lease_token`, `lease_expires_at`, and `heartbeat_at`;
- fail at or above the acquisition limit with
  `LEASE_EXPIRED_MAX_ATTEMPTS`;
- otherwise set `status = 'queued'` and preserve the resume stage.

Return a JSON summary containing reaped and failed counts.

### Explicit release

Create `release_video_job` with row locking and token validation. It must reject
terminal jobs or invalid outcomes, and must validate the current lease token
before changing any state.

- `completed_stage`: capture the current stage as
  `coalesce(next_stage, current_step)`, set that value as
  `last_completed_stage`, set `next_stage = p_next_stage`, clear the lease
  fields, and either mark the job completed when `p_next_stage = 'completed'`
  or return it to the queued state for the explicit next stage.
- `requeue`: clear lease fields, set `status = 'queued'`, and preserve the
  current resume stage.

No hidden stage progression will be inferred: the caller supplies the next
stage explicitly, and the current stage is captured from the row before the
update.

## Rollback

The down migration must refuse to run while any nonterminal fenced lease exists.
After the guard passes, it removes the new RPCs, indexes, attempt-limit
constraint/column, and any forward-only constraints introduced by Checkpoint
1B. It must preserve Checkpoint 1A and legacy objects that it did not create.

Rollback will be tested on the ephemeral database both with an active lease
(must refuse) and after leases are terminalized or cleared (must succeed).

## Validation

Use a disposable `postgres:17` container and apply, in order:

1. Baseline migrations `001` through `003`.
2. `20260727134852_simple_processing_lifecycle.sql`.
3. `006_add_soft_delete.sql`.
4. Checkpoint 1A.
5. Checkpoint 1B.

Test cases:

- normal expired lease requeues and increments once;
- expired lease at `max_job_attempts - 1` fails with the required failure class;
- repeated/concurrent reaper selection cannot double-process the same row;
- claim cannot acquire beyond the configured maximum;
- `release_video_job` succeeds for both outcomes with a valid token;
- stale-token release fails with `LEASE_LOST` and leaves state unchanged;
- legacy claim remains callable and unchanged;
- Checkpoint 1A fenced claim remains available and service-role-only;
- rollback refuses with active fenced leases and succeeds after safe cleanup;
- the ephemeral container is removed after validation.

No production database, migration history, n8n workflow, provider mode, or real
video job is touched by this design or its planned validation.
