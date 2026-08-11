# Phase 7 Validation Runner: Checkpoint 1N Run-Token Propagation

## Final Status

**RUN_TOKEN_BLOCKED_RUNTIME**

The original `RUN_TOKEN_LOST` cause was reconciled in repository and live WF04,
but the deterministic no-provider probe exposed the next blocker immediately:
WF04 cannot execute its stage-context normalizer in the n8n sandbox because the
node uses a disallowed `require('crypto')` call. No production job was created,
no provider was called, and no lease was retained by the probe.

## Root Cause

The original production failure was caused by a disconnected WF04 stage-context
branch. `Workflow Trigger` connected directly to `Validate`, bypassing:

`Normalize Stage Context -> Begin Stage -> Merge Stage Context -> Stage Started?`

`Begin Stage` is the first run-token creator. The `begin_job_stage` response
contains the canonical field `run_token`. `Merge Stage Context` renames that
field to `runToken`. Because the stage branch was bypassed, `Merge Heartbeat
Context` never executed, and `Finalize Provider Failure` used null fallbacks
for `stageRunId` and `runToken`. The child then returned `RUN_TOKEN_LOST`.

Exact forensic chain:

- WF03 parent execution: `35667`
- WF03 node: `Call Generate Script`
- WF04 child execution: `35668`
- WF04 final node: `Finalize Provider Failure`
- Error: `RUN_TOKEN_LOST`
- WF04 executed nodes included `Validate`, `Load Job`, `Build Prompt`, and
  `Execute AI Text`, but not `Normalize Stage Context`, `Begin Stage`, or
  `Merge Stage Context`.
- `Load Job` returned only job fields.
- `Build Prompt` returned prompt/provider fields only.
- No canonical stage run token existed when failure finalization ran.

## Minimal Fix Applied

Only WF04 was changed:

- `Workflow Trigger` now enters `Normalize Stage Context`.
- `Merge Heartbeat Context` remains the sole path into `Validate`.
- `Merge Stage Context` validates `result.run_token` as a UUID and throws
  `RUN_TOKEN_REQUIRED` when absent.
- `Merge Attempt Context` rejects a missing `runToken`.
- `Merge Heartbeat Context` rejects a missing `runToken`.
- `Finalize Provider Failure` no longer uses null/default fallbacks for the
  fenced stage context; it reads the canonical `Merge Heartbeat Context`
  values directly.

The canonical contract is now:

- Created once by `begin_job_stage` as `run_token`.
- Renamed once to `runToken` by `Merge Stage Context`.
- Preserved through heartbeat, Execute Workflow, retries, revisions, and
  finalization.
- Missing values fail immediately with `RUN_TOKEN_REQUIRED`.
- No `unknown`, null, fabricated, or regenerated run-token fallback exists in
  the changed WF04 path.

## New Blocker

The deterministic no-provider probe reached the corrected stage-entry path and
failed at:

- Workflow: WF04 `Generate Script and Scenes`
- Node: `Normalize Stage Context`
- Runtime error: `Module 'crypto' is disallowed`
- HTTP result: `500`
- Provider calls: `0`

The node uses `const crypto = require('crypto')` to calculate `inputHash`.
n8n’s Code node sandbox rejects that module. This is a new runtime blocker
revealed after the run-token graph fix. No further fix was attempted in this
checkpoint.

## Deterministic Probe

Temporary probe:

`clipcraft/scripts/controlled_wf04_run_token_no_provider_probe.js`

The probe:

- Used a temporary webhook workflow.
- Stubbed only the `begin_job_stage` response with a fixed UUID-shaped token.
- Reused the live `Normalize Stage Context` and `Merge Stage Context` logic.
- Stopped before any provider or database call.
- Returned HTTP `500` at the sandbox module restriction.
- Cleaned up the temporary workflow in `finally`.

No production job, provider call, database stage run, or retained lease was
created by the probe.

## Tests

Fresh tests:

- Workflow integration tests after the graph and guard changes: `27 passed`
- Run-token deterministic probe: failed at the new `crypto` sandbox blocker

Previously verified:

- Full workflow/Python suite: `131 passed`
- Custom-node suite: `29 passed`
- Frontend production build: passed
- Docker Compose validation: passed
- Focused WF17 request-ID tests: passed

Backend suite remains the known `261 passed, 1 failed` result due to the missing
`clipcraft/supabase/migrations/009_video_job_configuration_snapshots.sql`.
The full post-fix suite was not rerun after the first new runtime blocker.

## Repository And Live State

Repository workflow changed:

- `clipcraft/workflows/04-generate-script-and-scenes.json`

Live WF04:

- Workflow ID: `dWTF2UGXX3R73PDW`
- Active: `true`
- Node count: `32`
- Active version: `8b435deb-6c30-4005-a386-7f7309554700`
- Trigger target: `Normalize Stage Context`
- Heartbeat context target: `Validate`

Backup created before import:

`clipcraft/backups/phase-7-cutover/wf04-run-token-reconciliation-20260803T211628Z.json`

Scripts added for this checkpoint:

- `clipcraft/scripts/backup_wf04_run_token_1n.js`
- `clipcraft/scripts/import_wf04_run_token_1n.js`
- `clipcraft/scripts/controlled_wf04_run_token_no_provider_probe.js`

## Safety And State

- New production job: none
- Active jobs: `0`
- Active leases: `0`
- Running n8n executions after probe cleanup: `0`
- Provider execution: none
- Renderer execution: none
- TTS/captions/manifest execution: none
- Database migrations: none
- Credential changes: none
- Provider modes: unchanged, internal
- WF03 lease contract: unchanged
- WF17 request-ID contract: unchanged

## Reviews

Security review:

- No credentials, prompts, provider bodies, image bytes, or tokens were written
  to the report.
- No provider or database production call was made by the probe.
- No new secret exposure was introduced by the workflow change.

Compatibility review:

- Only WF04 graph/context handling changed.
- WF03, WF17, WF18, provider adapters, renderer, TTS, snapshots, and database
  schema were not changed.
- Workflow identity, name, active state, and node count were preserved.

## Remaining Blockers

1. Replace the disallowed `require('crypto')` in WF04 `Normalize Stage Context`
   with an n8n-sandbox-compatible hashing path, or otherwise reconcile the
   runtime without weakening input hashing.
2. Rerun the deterministic no-provider run-token probe.
3. Rerun focused and full verification before any production generation.
4. Resolve the known backend migration-history drift separately.

Production readiness for the next generation remains blocked. Checkpoint 1O
and later checkpoints must not begin. Pexels integration must not begin.
