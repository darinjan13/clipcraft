# Phase 7 Checkpoint 1D: First Successful End-to-End Generation

## Final Status

**FIRST_GENERATION_FAILED**

Exactly one production test job was created. It did not reach provider or media
execution. No second job, retry, or cancelled-job retry was attempted.

## Job

- Job ID: `3a96dcfd-c541-4070-90d2-7fc0a58e807f`
- Creation response: HTTP `202`
- Creation status: `queued`
- Topic: simple educational topic about how bees help plants grow
- Requested duration: `30` seconds
- Requested scene count: `6` (application minimum for this duration)
- Execution modes: internal text and internal image

## Pre-Flight

Passed before creation:

- Backend, renderer, TTS, and n8n health checks returned HTTP `200`.
- No active job or lease existed.
- WF03-WF09, WF17, and WF18 were active.
- `TEXT_EXECUTION_MODE=internal`.
- `IMAGE_EXECUTION_MODE=internal`.
- Renderer endpoint resolved through `clipcraft-renderer:8088`.
- Custom text/image nodes were loaded.
- `ClipCraft Internal API` credential existed.
- Known cancelled job remained cancelled.

## Execution Timeline

The create workflow execution succeeded:

- Create workflow execution: `33586`
- Queue worker execution: `33587`, error
- WF04 execution: `33588`, error
- WF17 execution: `33589`, error

Observed sequence:

1. Job was created and queued.
2. Queue worker changed the job to `generating_script`.
3. WF04 started and reached `Execute AI Text`.
4. WF17 failed in `Prepare Provider Attempt` before the internal provider node.
5. WF04 and the queue worker failed through the child-workflow chain.

## Root Cause

WF17 execution `33589` failed with:

```text
Cannot read properties of undefined (reading 'randomUUID') [line 3]
```

This is an n8n Code node runtime incompatibility in `Prepare Provider Attempt`.
The failure occurred before `ClipCraft Text Execute`, before the backend
internal text endpoint, and before any provider call.

## Lease And Persistence State

At failure observation, the job had status `generating_script`, progress `5`,
and `claimed_by=clipcraft-n8n`, but no lease token, expiry, heartbeat, or
attempt increment was present. No stage ledger row had been created.

The job was terminalized with a guarded update for this exact job and state:

- Final status: `cancelled`
- Current step: `cancelled`
- Failure class: `internal_text_execution`
- Lease token: null
- Claimed worker: null
- Attempt number: `0`
- Pipeline revision: `1`
- Scenes: `0`
- Assets: `0`
- Stage runs: `0`

Post-run live state:

- Active jobs: `0`
- Active leases: `0`
- Known cancelled job: unchanged
- Workflow count: `15`
- Credential count: `1`

## Provider And Media Results

- Internal text provider call: not reached.
- Legacy text provider call: not reached.
- Internal image provider call: not reached.
- Legacy image provider call: not reached.
- Word-count validation: not reached.
- Revision: not reached.
- Scene persistence: not reached.
- TTS, captions, manifest, renderer, thumbnail, preview, and MP4: not reached.
- Duplicate provider calls: none observed.
- Provider secrets, HMAC material, prompts, image data, and raw provider
  responses: none observed in this failed path.

## Compatibility And Security Review

The failure is isolated to runtime JavaScript UUID generation. It does not
indicate lease-contract weakening, renderer drift, provider fallback, duplicate
billing, or a database persistence failure. The renderer reconciliation and
prior workflow/custom-node test evidence remain valid.

The failed path exposed no provider call or provider response. No workflow,
provider mode, migration, Docker configuration, or architecture change was
made during this checkpoint.

## Remaining Issues

- Replace the unavailable Code node `crypto.randomUUID` usage with the
  repository-approved runtime-compatible UUID generation path, then add or
  update a focused workflow contract test before another live attempt.
- Do not retry this cancelled job.
- Do not create a second job until the runtime fix is separately approved and
  verified.

## Production Readiness

The integrated architecture is **not ready** for first successful production
generation. The checkpoint stopped at the first failed stage as required.
