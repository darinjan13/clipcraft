# Phase 7 Validation Runner: Checkpoint 1M

## Status

**BLOCKED at Checkpoint 1M**

The retained production job was inspected and reconciled using the deployed
lease policy. It was requeued once because its first lease had expired, then
reclaimed at the final allowed acquisition. The resumed run failed before WF04
could establish a stage run. The expired final lease was terminalized by the
same policy RPC. No new production job was created.

## Checkpoint Position

- Last completed checkpoint: 1K
- Prior checkpoint: 1L blocked during pre-flight before job creation
- Current checkpoint: 1M
- Next checkpoint: 1N, blocked pending the new dispatch failure
- Estimated remaining checkpoints: 1N through 1Q after the blocker is fixed

## Current Blocker

- Job ID: `1de38bd2-43e4-47c8-bcaf-0e4911425214`
- Exact workflow: `Video Job Queue Worker` / WF03
- Exact node: `Call Generate Script`
- Parent execution: `35667`
- Normalized error: `RUN_TOKEN_LOST`
- Execution status: `error`
- Last node: `Call Generate Script`
- Child WF04 execution: not retained/observed
- Stage-run record: none created

The worker successfully claimed the job and reached the Execute Workflow node,
but the WF04 dispatch failed with `RUN_TOKEN_LOST`. The job then remained in
`generating_script` until its final lease expired. This is the first new
blocker in Checkpoint 1M. The exact child-side origin of `RUN_TOKEN_LOST` was
not proven before the hard stop.

## Root Cause Evidence

- Before reconciliation, the job had `attempt_number=1`, `max_job_attempts=3`,
  `next_stage=generate_script`, and an expired lease.
- The live worker had no workflow invoking `reap_expired_video_job_leases`.
- Existing policy requires an expired attempt below the limit to be requeued,
  preserving its resume stage.
- One policy reaper call returned `reaped_count=1`, `failed_count=0`.
- The worker reclaimed the same job at acquisition `3/3`.
- Worker execution `35667` failed at `Call Generate Script` with
  `RUN_TOKEN_LOST`.
- No `job_stage_runs` row was created for the job.
- Supabase API logs recorded the fenced claim calls and a failed
  `fail_job_stage` request with HTTP 400.
- No provider call, image call, TTS call, caption call, manifest call, or
  renderer call occurred in this checkpoint.

## Lease And Job State

After the final policy-managed cleanup:

- Status: `failed`
- Current step: `failed`
- Progress: `5`
- Attempt number: `4` after the policy’s terminal failure transition
- Maximum job attempts: `3`
- Pipeline revision: `1`
- Claimed by: `null`
- Lease token: cleared and intentionally not recorded
- Lease expiry: `null`
- Heartbeat: `null`
- Failure class: `LEASE_EXPIRED_MAX_ATTEMPTS`
- Finished at: populated
- Active jobs: `0`
- Active leases: `0`
- Running n8n executions: `0`

The second policy call returned `reaped_count=0`, `failed_count=1`.

## Provider State

- Text mode: internal
- Image mode: internal
- Configured text provider/model: Cloudflare / current configured model
- Configured image provider/model: Cloudflare / current configured model
- Text provider calls: `0`
- Image provider calls: `0`
- HMAC provider requests: not reached
- Custom text node: not reached in this run
- Custom image node: not reached in this run
- Legacy branches: not reached

## Renderer State

- Renderer health: previously verified HTTP 200 on the internal network
- Configured render URL: `http://clipcraft-renderer:8088/render`
- Renderer invocation: `0`
- FFmpeg: not reached
- MP4: not created
- Thumbnail: not created

## Validation Results

No new job reached the following stages:

- WF04 lease validation and stage start
- WF17 text execution
- Structured output and word-count validation
- Scene persistence
- WF05/WF18 image execution
- TTS and audio duration
- Captions
- Render manifest
- Renderer and FFmpeg
- Preview/status persistence
- Activity timeline completion
- Snapshot verification
- Final MP4 inspection or output-quality review

## Tests And Reviews

Tests executed during Checkpoint 1M:

- Read-only Supabase RPC/function inspection: passed
- Read-only job/lease state verification: passed
- Read-only n8n execution inspection: passed
- Supabase API and Postgres log inspection: passed
- Final active-job/active-lease safety check: passed

Previously verified before this checkpoint:

- Workflow/Python suite: `131 passed`
- Custom-node suite: `29 passed`
- Focused WF17 request-ID tests: passed
- Frontend production build: passed
- Docker Compose validation: passed
- Backend suite: `261 passed, 1 failed`; the failure remains the known missing
  `clipcraft/supabase/migrations/009_video_job_configuration_snapshots.sql`

Security review:

- No credentials, prompts, provider bodies, image bytes, or base64 values were
  added to this report.
- Supabase advisors were read-only checked. Existing RLS-without-policy,
  mutable-search-path, exposed security-definer, unindexed-FK, and unused-index
  notices remain unresolved and were not changed.

Compatibility review:

- No workflow definition, provider mode, renderer contract, custom node, or
  schema code was changed in Checkpoint 1M.
- WF03 continued using `claim_next_video_job_fenced`.
- WF17 remained on live version
  `75ffd275-e66c-420e-9523-bdc92a622854`.

Deployment review:

- n8n remained healthy.
- Required workflows remained active.
- Credential count remained `1`.
- No deployment or container change was made.

Rollback readiness:

- No repository or workflow files were changed in Checkpoint 1M.
- No new backup was required.
- Existing WF17 backup and prior phase backups remain available.
- The only live state mutation was the deployed lease-policy RPC acting on the
  explicitly inspected retained job.

## Files And Live Changes

Files changed in this checkpoint:

- `clipcraft/docs/superpowers/reports/2026-08-04-phase-7-validation-runner-checkpoint-1m.md`

Workflows changed: none.

Reports written:

- This Checkpoint 1M report

Backups created: none.

Live changes applied:

- One policy-managed requeue of the expired retained lease
- One policy-managed terminal failure at the configured attempt limit
- No workflow, code, migration, credential, or provider configuration change

Repository changes: report only.

## Remaining Technical Debt

- The live worker has no scheduled invocation of the expired-lease reaper.
- `RUN_TOKEN_LOST` at WF03 `Call Generate Script` needs child-dispatch
  investigation before another production run.
- Backend migration-history drift remains unresolved.
- Existing Supabase advisor findings remain unresolved.
- Prior execution-data secret exposure remains a separate remediation item.

## Production Readiness

- Production readiness: `0%` for a complete integrated generation in this
  validation sequence; the pipeline has not produced a new complete video.
- Remaining production blocker: `RUN_TOKEN_LOST` during WF04 dispatch.
- Checkpoint 1N: do not start until the dispatch blocker is reconciled and
  pre-flight confirms zero active jobs and leases.
- Checkpoint 1O: not reached.
- Checkpoint 1P: not reached.
- Checkpoint 1Q: not reached.
- Pexels integration: **must not begin**.

Stop after Checkpoint 1M. Do not create another production job, retry the
failed job, skip to 1O/1P/1Q, or apply unrelated fixes.
