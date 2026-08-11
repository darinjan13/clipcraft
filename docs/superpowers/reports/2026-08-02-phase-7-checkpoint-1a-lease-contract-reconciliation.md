# Phase 7 Checkpoint 1A: Lease Contract Reconciliation

## Final Status

**SAFE_TO_APPLY**

The live audit is complete and the additive reconciliation migration is prepared locally. It was applied and exercised against a disposable PostgreSQL 17 database, then rolled back successfully. It was not applied to the live database. No jobs, provider modes, or live workflows were changed by Checkpoint 1A.

## Read-Only Audit Coverage

Eight read-only audits were completed:

- Live Supabase schema audit.
- Migration-order review.
- RPC contract review.
- Workflow lease-contract review.
- Backward-compatibility review.
- Migration-safety review.
- Rollback review.
- Security review.

No audit agent edited files, applied SQL, imported workflows, restarted services, created jobs, or mutated the cancelled job.

## Live Schema Matrix

| Field/object | Repository expectation | Live state | Type/semantics | Workflow/backend use | Source |
|---|---|---|---|---|---|
| `claimed_by` | Worker identity | Exists | Legacy nullable text | Legacy worker and status paths | `001`/`002` live |
| `claimed_at` | Legacy claim timestamp | Exists | Legacy nullable timestamptz | Legacy worker/status paths | `002` live |
| `lease_token` | Fencing token | Missing | N/A | Required by staged workflows | `004`, not live |
| `lease_expires_at` | Lease expiry | Missing | N/A | Heartbeat/stage fences | `004`, not live |
| `heartbeat_at` | Lease heartbeat | Missing | N/A | Heartbeat fence | `004`, not live |
| `attempt_number` | Fenced acquisition count | Missing | N/A | Stage RPCs/workflows | `004`, not live |
| `pipeline_revision` | Revision fence | Missing | N/A | Stage input/finalization | `004`, not live |
| `next_stage` | Resume point | Missing | N/A | Queue/stage orchestration | `004`, not live |
| `last_completed_stage` | Durable resume metadata | Missing | N/A | Stage completion | `004`, not live |
| `failure_class` | Safe failure classification | Missing | N/A | Error handling/events | `004`/`005`, not live |
| `job_stage_runs` | Stage execution ledger | Missing | N/A | Begin/reserve/finalize/fail RPCs | `004`, not live |
| `regeneration_operations` | Regeneration ledger | Missing | N/A | Not required for this checkpoint | `004`, not live |

Live counts:

- `video_jobs`: 43.
- All 43 are `cancelled`.
- 42 retain legacy `claimed_by`/`claimed_at` metadata.
- No live fenced lease exists because the lease columns are absent.
- `scenes`: 66.
- `assets`: 66.
- `video_job_events`: 239.
- No active queue or stage job was found.

The known job `9edd0fa5-df56-42cb-96a6-4265e37db34d` remains cancelled. No MP4 exists.

## Migration Drift

Live migration history contains only timestamped migrations corresponding to provider credentials, provider test statuses, configuration snapshots, and application preferences. Repository migrations `001` through `006` are not represented in live history, although parts of their schema are present.

Migration `004_core_backend_foundation.sql` is unsafe to apply unchanged because it:

- Backfills legacy claims with synthetic lease state.
- Derives attempt history from legacy retry fields.
- Creates an overloaded claim RPC beside the legacy function.
- Changes uniqueness semantics for scenes.
- Assumes extension/function placement that differs by Supabase environment.
- Creates stage tables without the required explicit browser access posture.

Migration `005` also assumes lease columns that are absent live. The legacy migration runner applies historical migrations in an order that is not safe for this drifted production state.

## Canonical Contract

The reconciliation uses a distinct RPC name to avoid PostgREST overload ambiguity:

```text
public.claim_next_video_job_fenced(text, integer default 120) returns jsonb
```

Successful result:

```json
{
  "claimed": true,
  "lease_token": "uuid",
  "job": {
    "id": "uuid",
    "status": "generating_script",
    "current_step": "generating_script",
    "claimed_by": "clipcraft-n8n",
    "claimed_at": "timestamp",
    "lease_token": "uuid",
    "lease_expires_at": "timestamp",
    "heartbeat_at": "timestamp",
    "attempt_number": 1,
    "pipeline_revision": 1,
    "next_stage": "generate_script",
    "last_completed_stage": null,
    "failure_class": null
  }
}
```

No credentials, encrypted secrets, or unrestricted future job columns are returned.

The RPC selects only clean queued rows with null legacy claim fields, uses `FOR UPDATE SKIP LOCKED`, generates the lease token at acquisition time, increments `attempt_number` atomically, and sets the lease/heartbeat fields in one update. Historical claimed rows are not backfilled or reclaimed.

Fenced RPCs prepared:

- `heartbeat_video_job`.
- `begin_job_stage`.
- `reserve_stage_external_attempt`.
- `finalize_stage_success`.
- `fail_job_stage`.

Each validates job ID, worker ID, lease token, attempt number, pipeline revision, non-terminal status, and active lease. Stale tokens fail closed.

## Compatibility Boundary

WF03 is updated locally to call `claim_next_video_job_fenced` with `p_worker_id` and `p_lease_seconds`. The normalization boundary rejects incomplete claim results and does not fabricate lease tokens, attempt numbers, or revisions.

Legacy `claim_next_video_job(text)` remains a compatibility function but is not used by the staged worker. The reconciliation migration revokes its browser-role execution while retaining service-role compatibility until legacy callers are retired.

No provider execution mode, WF17 behavior, WF05/WF18 provider path, renderer behavior, frontend behavior, or legacy workflow was changed.

## Security and Rollback

Security findings:

- Existing legacy RPCs are broadly executable by browser roles and require privilege tightening.
- RLS is enabled on public tables but has no user-facing policies; new stage tables are service-role-only.
- Service-role keys remain the privileged worker boundary.
- Public status/download workflows require separate ownership review.
- Lease tokens are treated as bearer capabilities and are not returned to user-facing APIs.

Rollback posture:

- N8n backups are available under `clipcraft/backups/phase-7-cutover/20260801T184627Z/` and `clipcraft/backups/n8n-recovery/20260801-231151Z/`.
- No Supabase/Postgres snapshot was available in the workspace.
- The migration is additive and has no destructive historical backfill.
- No live migration was applied, so no database rollback was required.

## Verification

Passed locally:

- Reconciliation migration contract test.
- WF03 fenced claim contract test.
- Existing workflow integration tests relevant to the claim boundary.
- Existing custom-node tests remain unchanged.

Not completed because live deployment was intentionally not attempted:

- Live migration application.
- PostgREST schema-cache verification after deployment.
- Live claim fixture call.
- Live heartbeat/stage-fencing fixture.
- Controlled workflow lease probe.
- Full backend/frontend/custom-node regression after deployment.

## Application Gate

Before application, restore a database-capable execution path and verify:

1. No active jobs or stage executions.
2. A fresh schema/RPC backup is captured.
3. The migration runs transactionally with lock and statement timeouts.
4. PostgREST exposes the new RPC signature without overload ambiguity.
5. Service-role grants are correct and browser roles cannot execute internal RPCs.
6. A controlled queued fixture is used for one claim/heartbeat/stage-fence probe only.
7. The known cancelled job remains cancelled and untouched.

Do not create a video job or retry the cancelled job until those checks pass.

## Ephemeral Validation Addendum

The migration was tested in disposable container `clipcraft-lease-test` using PostgreSQL 17 with Supabase-role fixtures and repository baseline migrations `001` through `003`.

- Two cancelled stale legacy-claim rows were excluded by the fenced claim.
- A clean queued fixture received the full fenced contract.
- The legacy claim RPC still worked afterward.
- Legacy RPC ACL was unchanged before and after migration.
- A stage row was created, then the down migration removed it along with all new objects.
- The down migration was run twice successfully.
- The disposable container was removed.

Live application remains approval-gated and was not performed.
