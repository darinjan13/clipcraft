# Phase 7 Checkpoint 1A Lease Contract Reconciliation

## Status

**CHECKPOINT_1A_VERIFIED_STOP_BEFORE_GENERATION**

The live Supabase lease/stage contract is present and matches the staged
workflow RPC signatures. The remaining compatibility gap found during audit
was the browser-role ACL on the legacy claim RPC. An ACL-only migration removed
that access while preserving service-role compatibility. No job was claimed,
created, retried, or modified.

## Audit

- Live `video_jobs`: `43` total, `0` active/non-terminal, `0` active fenced leases.
- The known cancelled job `9edd0fa5-df56-42cb-96a6-4265e37db34d` remains cancelled.
- `job_stage_runs` exists and currently contains no active stage run.
- Live lease columns exist: `lease_token`, `lease_expires_at`, `heartbeat_at`,
  `attempt_number`, `pipeline_revision`, `next_stage`,
  `last_completed_stage`, `failure_class`, and `max_job_attempts`.
- The lease-shape constraint is validated; forward-only attempt/revision/limit
  constraints are present as `NOT VALID`, matching the additive compatibility
  design.
- Active WF03 is unchanged: `Video Job Queue Worker`, ID
  `1usjkGUZXjFpXZNU`, version
  `94e2c8e6-74a6-4d53-be02-5bac3eb9dabb`.

## Change

Added `supabase/migrations/20260803140000_restrict_legacy_claim_rpc_acl.sql`:

- `claim_next_video_job(text)` remains executable by `service_role`.
- `anon` and `authenticated` can no longer execute the legacy claim RPC.
- The fenced claim and all stage lease RPCs remain service-role-only.
- No lease validation, token validation, attempt validation, or workflow graph
  was weakened or changed.

The migration was applied to the live database through the Supabase migration
operation and verified with `has_function_privilege`.

## Verification

Focused contract and workflow suites:

```text
tests/test_foundation_contracts.py tests/test_workflow_integration.py
57 passed
```

Full backend/workflow test directory:

```text
tests
108 passed
```

The new ACL test was observed failing before the migration file existed, then
passed after the smallest ACL-only migration was added.

Live privilege verification:

```text
legacy claim: service_role=true, anon=false, authenticated=false
fenced claim: service_role=true, anon=false
stage/reaper/release RPCs: service_role=true, anon=false, authenticated=false
```

## Security Review

The Supabase advisors still report pre-existing findings unrelated to this
checkpoint, including mutable search paths on legacy functions, public-schema
tables with RLS but no policies, and existing public security-definer helper
functions. The new fenced/stage functions have an empty search path and are not
browser-executable.

Live migration history remains drifted: the contract objects are present, but
the remote migration list contains only the pre-existing provider/configuration
migrations. This is recorded as a deployment-history follow-up and was not
repaired during this checkpoint.

## Stop Boundary

No video job was created. The cancelled job was not retried. No n8n workflow was
imported, activated, or modified. No provider mode, Docker setting, or
production data was changed. Phase 7 end-to-end generation remains blocked
until the lease contract and migration-history ownership are explicitly
accepted for the next checkpoint.
