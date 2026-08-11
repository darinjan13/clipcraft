# Checkpoint 1R: Reconcile `begin_job_stage` ledger contract (Constrained Option A)

- **Date:** 2026-08-06
- **Project:** clipcraft-ai (live: `dpcytfpqhxpqufcsivkh`)
- **Scope gate:** Checkpoint 1Q approval → Phase B (begin_job_stage contract reconciliation) staged deployment.
- **Status:** Live applied, signature/security verified, provider-free ledger probes passed. No provider-backed/production generation run this deployment.

## Objective
Replace the additive `begin_job_stage` ledger contract (overwrite-on-rebegin, `<>` comparators) with the constrained Option A ledger contract: deterministic, additive, terminal-safe, fence-safe.

## Contract (applied, live)
- **STARTED** — new ledger row inserted (`status='running'`); exactly one fresh `run_token`.
- **CACHED_SUCCESS** — existing `succeeded` row + matching hash; returns `output`; no `run_token`.
- **RUNNING** — existing `running` row + matching hash; no new token, no ownership refresh (re-begin is idempotent).
- **FAILED** — existing `failed` row + matching hash; terminal, never overwritten; `error` returned.
- **INPUT_HASH_MISMATCH** — succeeded/running/failed row with differing hash; no output, no token.
- **INVALID_ITEM_KEY** — JSON return (not exception) for blank `p_item_key`; reserved solely for that case.
- **UNKNOWN_OUTCOME** — non-canonical row status.
- **LEASE_LOST** — exception: fence mismatch / expired lease / terminal video job / null lease / non-positive attempt / non-positive revision.
- Controlled validation exceptions before any mutation: `INVALID_STAGE`, `INVALID_INPUT_HASH`, `INVALID_WORKER_ID`.
- `is distinct from` null-safe fences; video_jobs locked before job_stage_runs (serializes concurrent begins).
- Signature preserved: `begin_job_stage(uuid, integer, text, text, text, text, uuid, integer) returns jsonb`.
- `CREATE OR REPLACE FUNCTION` only; no DROP, no new columns, no historical rewrites. service_role-only grants re-asserted.

## Pre-deployment checks
- Live target confirmed: `dpcytfpqhxpqufcsivkh.supabase.co`.
- Fresh pre-application source snapshot saved to `backups/pre-checkpoint-1r_begin_job_stage_20260806.sql`.
- Rollback path present: `migrations_rollback/20260805120000_reconcile_begin_job_stage_contract.down.sql`.
- No active work: 0 non-terminal jobs, 0 active leases, 0 expired leases, 0 `job_stage_runs`. (42 `claimed_by` texts are stale; no live lease token.)
- Live `begin_job_stage` pre-state = baseline (`<>` comparators, overwrite-on-rebegin) matching the local RED baseline.

## Applied
- `20260805120000_reconcile_begin_job_stage_contract.sql` (recorded in `schema_migrations` as `reconcile_begin_job_stage_contract`). Field name in this project: `migrations/20260805120000_...`.

## Post-apply verification
- Signature: `(uuid, integer, text, text, text, text, uuid, integer)` → `jsonb`; unchanged.
- `SECURITY DEFINER`: true; `search_path=''`; ACL = `postgres`, `service_role` only.
- `service_role` EXECUTE = true; `anon` = false; `authenticated` = false.
- Body markers present: INVALID_STAGE, INPUT_HASH_MISMATCH, INVALID_ITEM_KEY, CACHED_SUCCESS, FAILED, UNKNOWN_OUTCOME, all via `is distinct from`.
- RPC in `public` schema returning `jsonb` → PostgREST-exposed.
- No schema drift: no tables/columns altered; function-only change.
- Security advisor scan: no new advisories introduced by this change (begin_job_stage absent from mutable-search_path and anon/authenticated-SEC only-DEF advisories). Pre-existing advisories (unrelated): `rls_enabled_no_policy` on several tables, mutable search_path on legacy RPCs, writable `log_video_job_transition`/`prevent_video_job_event_mutations`. These are out of scope for 1R.

## Provider-free WF04 ledger probes (live, all within a rolled-back transaction)
All transactions rolled back (verified: 0 synthetic video_jobs, 0 probe job_stage_runs, 0 residue). Results:

| State | Result |
|---|---|
| STARTED | PASS — new row, one run_token, rowcount 1 |
| CACHED_SUCCESS | PASS — output returned, no run_token, row unchanged |
| RUNNING | PASS — run_token preserved, no refresh, no run_token in response |
| FAILED | PASS — terminal, error_json preserved, no run_token |
| INPUT_HASH_MISMATCH | PASS — no output, no run_token |
| INVALID_ITEM_KEY | PASS — JSON return, no row created |
| UNKNOWN_OUTCOME | PASS — no run_token |
| LEASE_LOST (terminal job) | PASS — LEASE_LOST raised |
| LEASE_LOST (fence mismatch) | PASS — LEASE_LOST raised |

Fixture notes: live `video_jobs` has a lease-shape CHECK (lease_token/lease_expires_at/heartbeat_at all-set-or all-null) and a `status` CHECK (uses `generating_images`, not `active`); fixture inserts honored both. No providers, no renderer, no TTS, no production video were invoked.

## Rollback path
If the migration is ever proven incorrect, apply `backups/pre-checkpoint-1r_begin_job_stage_20260806.sql` (or the `migrations_rollback` down file) to restore the pre-1R body. No data depends on the change (0 stage_runs), so rollback is trivial and safe. Rollback status: NO.

## Next checkpoint
Either proceed to Phase G (update WF04 to consume the new begin state/run_token/state branching in the Merge Stage Context) and continue toward the first provider-free end-to-end video; or stop. No provider-backed or production generation was started in this checkpoint.