# Phase 7 Checkpoint 1H: WF03 Live Claim-Path Reconciliation

## Final Status

**WF03_BLOCKED_RUNTIME**

The live WF03 claim path was reconciled to the approved fenced RPC and the
canonical claim normalizer. Repository and live focused checks passed. The
single disposable claim-to-WF04 probe verified the fenced claim and dispatch
sequence, but the execution-stop guard raced with WF17 and an internal
Cloudflare text attempt started. The probe was stopped, the disposable job was
cancelled, and no second probe or full production generation was attempted.

## Exact Live Root Cause

Before this checkpoint, live WF03 node `Claim Next Job` called:

```text
/rest/v1/rpc/claim_next_video_job
```

The live `Extract Job Info` and `Validate and Extract Claimed Job` path accepted
the legacy direct row shape and mapped missing values to null/default values.
The disposable Checkpoint 1G execution showed:

- `lease_token: null`
- `lease_expires_at: null`
- `attempt_number: 0`
- `pipeline_revision: 1`

WF03 then dispatched WF04 with incomplete lease context, and WF04 failed at
`Finalize Provider Failure` with `Bad request - please check your parameters`.

## Repository And Live Diff

Repository WF03 already contained the fenced claim URL, but its executable
normalization boundary was still the old field copier. Live WF03 differed in
four relevant source locations:

- Live claim URL: legacy RPC; repository: fenced RPC.
- Live claim body: `worker_id`; repository: `p_worker_id` and
  `p_lease_seconds=120`.
- Live disconnected `Extract Job Info`: legacy permissive copier; repository:
  an older fenced-only copier.
- Live executable `Validate and Extract Claimed Job`: copied snake_case fields
  and allowed null lease context; repository now contains the canonical
  validating normalizer.

The disconnected `Extract Job Info` node was not part of the executable claim
edge and was left untouched in the live import. No duplicate claim or dispatch
edge exists.

## Live Backup

Live WF03 was exported before import to:

`backups/phase-7-cutover/wf03-claim-reconciliation-2026-08-03T19-01-10-585Z`

The backup records workflow ID `1usjkGUZXjFpXZNU`, name `Video Job Queue
Worker`, active state `true`, 56 nodes, version
`94e2c8e6-74a6-4d53-be02-5bac3eb9dabb`, timestamp, and pre-import hash.

## Canonical Claim Contract

The executable `Validate and Extract Claimed Job` boundary now:

- accepts a direct fenced object, one-element array, or known `result`/`data`
  envelope;
- rejects ambiguous multiple-row responses;
- treats `{claimed:false}` as clean no-work;
- requires `claimed=true` and a job object;
- maps authoritative snake_case values exactly once;
- validates job UUID, lease UUID, lease expiry timestamp, positive attempt,
  positive pipeline revision, claimed worker, stage, and non-terminal status;
- emits `jobId`, `leaseToken`, `leaseExpiresAt`, `attemptNumber`,
  `pipelineRevision`, `claimedBy`, `workerId`, `nextStage`,
  `lastCompletedStage`, `status`, and `currentStep`;
- preserves the authoritative job payload needed by downstream stages;
- returns no item for malformed or incomplete claims and never fabricates
  identifiers or lease values.

## WF04 Dispatch Contract

WF03 continues to call WF04 ID `dWTF2UGXX3R73PDW` through the existing
`Call Generate Script` node. The dispatch edge remains:

```text
Claim Next Job -> Validate and Extract Claimed Job -> Call Generate Script
```

No WF04 validation or business logic was changed. The normalizer supplies the
camelCase lease fields required by WF04's stage context while preserving job
brief and provider/model snapshot fields when present.

## Static And Focused Tests

New focused tests:

`tests/test_wf03_claim_contract.py`

Test-first results:

- Before implementation: `3 failed, 5 passed`; failures reproduced the old
  no-output fenced claim and legacy null-context acceptance.
- After implementation: `8 passed`.
- Existing fenced-worker integration checks: `2 passed`.

Coverage includes direct, array-wrapped, nested, empty, malformed, ambiguous,
snake_case, invalid UUID, invalid timestamp, missing lease fields, routing,
single dispatch, exact WF04 target, and secret exclusion.

## Live Import

Only two executable live nodes changed:

- `Claim Next Job`
- `Validate and Extract Claimed Job`

Preserved:

- Workflow ID: `1usjkGUZXjFpXZNU`
- Name: `Video Job Queue Worker`
- Active state: `true`
- Node count: `56`
- Caller and schedule contracts
- WF04 target and dispatch edge
- Live-only operational metadata
- Disconnected legacy artifact node

Post-import live version: `ba436c34-8634-4d73-a64c-e21d33e61bc7`.
Workflow count remained `15`; credential count remained `1`.

## Disposable Probe

Exactly one new disposable create request was sent through WF02:

- Job ID: `db9710d5-1d12-4161-9481-4d976b1dd240`
- WF02 execution: `34982`, success
- WF03 execution: `34983`, cancelled by execution stop
- WF04 execution: `34984`, cancelled by execution stop
- WF17 execution: `34985`, success with normalized provider failure

Claim and lease evidence before cleanup:

- Claim path: fenced claim RPC
- Lease duration requested: `120` seconds
- Lease token: present and UUID-shaped
- Attempt number: `1`
- Pipeline revision: `1`
- Claimed worker: `clipcraft-n8n`
- Job stage: `generating_script`

The WF04 child was created and no `LEASE_CONTEXT_REQUIRED` error occurred.
The child trigger input was not durably captured before the stop race, so this
checkpoint does not claim independent proof of every WF04 input field beyond
the successful progression into WF17.

## Hard-Stop Provider Event

The stop guard did not win the race. WF17 execution `34985` reached:

- `Workflow Trigger`
- `Build Request`
- `Validate Input`
- `Prepare Provider Attempt`
- `Text Execution Mode?`
- `Prepare Internal Request`
- `ClipCraft Text Execute`
- normalized failure handling

The internal text request targeted Cloudflare and returned HTTP `400` as
`AI_EXECUTION_FAILED`; no valid provider result was returned. No image, TTS,
caption, manifest, renderer, or media stage ran.

This is a hard-stop violation of the intended no-provider probe boundary. The
WF17 execution data also contained provider request material, including an
authorization header, so this checkpoint records a security exposure in the
existing execution-data path. The secret value is intentionally omitted from
this report. WF17 was not modified in this checkpoint.

## Cleanup And Post-Run State

The parent and child executions were stopped. The disposable row was then
cleared with a guarded service-role update.

- Final job status: `cancelled`
- Final step: `cancelled`
- Claimed worker: `null`
- Lease token: `null`
- Active jobs: `0`
- Active leases: `0`
- Running executions: `0`
- Workflow count: `15`
- Credential count: `1`
- Cancelled historical jobs: untouched

## Verification And Reviews

Completed:

- Focused WF03 tests: `8 passed`
- Existing fenced-worker integration checks: `2 passed`
- Repository/live node-and-edge audit
- Live workflow backup and import verification
- Read-only lease and claim review
- Post-probe active-job and active-lease verification

Not run after the hard-stop provider event:

- Full workflow integration suite
- Full Python/backend suite
- Custom-node suite
- Frontend production build
- Docker Compose validation
- Secret scans
- Broader compatibility and security suites

No database migration, provider-mode change, WF04 business-logic change,
WF05-WF18 source change, renderer change, TTS change, or frontend change was
made. WF02 remains unchanged in this checkpoint.

## Remaining Issues

- The no-provider controlled probe mechanism is not safe enough for another
  attempt; execution stop must be made deterministic before probing again.
- The existing WF17 execution-data path exposed provider authorization material
  and requires a separate security remediation review.
- WF04's prior bad-request path requires a separate diagnosis if a future probe
  is authorized.
- Do not create another disposable or full production job until these issues
  are explicitly approved and resolved.

## Readiness

WF03's claim path and canonical normalization are reconciled in repository and
live workflow state. The system is **not ready** for a full end-to-end
generation because the controlled probe crossed into provider execution and
exposed a security/runtime blocker.

## Follow-Up Reconciliation

Checkpoint 1I preserved WF03 and did not create a job. It added WF17 safe
response classification and a deterministic no-provider harness. The prior
provider-executing probe remains recorded as a hard-stop event.
