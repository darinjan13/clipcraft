# Phase 7 Checkpoint 1A Self-Review

## Status

**SAFE_TO_APPLY**

The migration compatibility and rollback fixes are implemented locally and validated against a disposable PostgreSQL 17 container. No live Supabase database or production job was touched.

## Fixes Applied

- Removed the permission change against legacy `claim_next_video_job(text)`.
- Added `20260802140000_reconcile_job_leases_and_claim_contract.down.sql`.
- Down migration refuses to run when active fenced leases exist.
- Down migration removes fenced functions, stage ledger, indexes, lease columns, and only the new lease constraint.
- Legacy RPC permissions are not modified by either migration.

## Validation

Static contract tests passed:

- Reconciliation migration contract: `2 passed`.
- WF03 fenced-claim contract: `1 passed`.

Real ephemeral validation used `postgres:17` in disposable container `clipcraft-lease-test`:

- Loaded repository legacy baseline migrations `001`, `002`, and `003`.
- Added Supabase-role fixtures: `anon`, `authenticated`, and `service_role`.
- Inserted two cancelled stale legacy-claim rows and two clean queued fixtures.
- Applied the reconciliation migration successfully.
- Fenced claim selected only the clean queued fixture and returned a UUID lease, expiry, heartbeat, attempt `1`, and pipeline revision `1`.
- Both stale cancelled rows remained unchanged and unclaimed.
- Legacy `claim_next_video_job(text)` still executed and claimed the separate legacy fixture.
- Legacy RPC ACL was `<default>` before and after the up migration.
- Created a stage ledger row, terminalized the fixture in the disposable database, and applied the down migration successfully.
- Down migration removed the stage table, fenced functions, indexes, and added columns.
- Stale legacy rows remained intact after rollback.
- Down migration was run a second time successfully, confirming idempotent cleanup behavior.
- Disposable container was removed after validation.

## Next Step

Production application remains a separate approval-gated operation. Docker is now available for local validation; Supabase management authorization and migration-history reconciliation are still required for live deployment.
