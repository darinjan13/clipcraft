# WF04 Fenced-Claim Cutover Design

## Scope

Plan the first production cutover from the legacy queue claim contract to
`claim_next_video_job_fenced`. This document does not modify or activate any
n8n workflow, create or claim a job, or change provider modes.

The cutover covers WF03 queue claiming, the WF04-WF09 stage context contract,
lease expiry handling, release semantics, and cancellation-safe late callbacks.
Active cancellation of an already-running n8n execution is explicitly out of
scope.

## Measured Latency Basis

The previously cited approximately 66-minute Gemini latency is unverified and
is removed from all lease planning.

Read-only retained n8n execution data showed:

- 19 successful WF17 executions: P50 350 ms, P95 4.207 s, worst 4.207 s.
- 11 internal provider-node executions: P50 363 ms, P95 4.111 s, worst 4.111 s.
- One retained external provider-node execution: 1.479 s.
- No successful full WF04 execution was retained.
- Nine recent WF04 runs failed before a long-running stage; observed causes
  included invalid job IDs, missing lease context, missing RPC/resource lookup,
  and earlier sandbox crypto errors.
- Backend Gemini timeout is 60 seconds and the internal custom-node timeout cap
  is 120 seconds. No explicit n8n execution timeout is configured in the local
  compose file.

The WF04 local timing harness confirmed that a 120-second lease provides
sufficient margin for the modeled local WF04 execution path using the retained
provider-latency quantile model. The 100-run harness measured modeled P50
`0.700s`, P95 `4.207s`, and worst `4.557s`, including 50 one-revision runs and
150 provider calls. With the fixed safety margin of `max(20% of modeled worst,
5s)`, the measured worst plus margin is `9.557s`; the 120-second lease is
confirmed for the current architecture under these modeled conditions.

This is not a measurement of production network latency, Supabase latency,
n8n scheduling or queue contention, container scheduling, deployment overhead,
or provider-tail latency beyond the retained measurements.

## Proposed Lease and Reaping Policy

- Use the confirmed `p_lease_seconds = 120`, matching the Checkpoint 1B default.
- Do not raise the current 900-second RPC ceiling without measured evidence.
- Use a new WF19-style Cron workflow as a reaper-only supervisor at a
  60-second interval.
- WF19 calls only `reap_expired_video_job_leases`; it does not heartbeat every
  lease.
- Reaping remains the dead-worker detector. A dead worker's 120-second lease
  expires and is reclaimed within approximately 2-3 minutes, depending on the
  schedule phase.
- A heartbeat-all-leases sweeper is rejected for this design because it would
  continuously extend dead leases and cannot distinguish a blocked active
  execution from a dead worker using current database fields.

## Current Workflow Map

### WF03 Queue Worker

The prepared repository WF03 contains these relevant nodes:

- `Queue Poller`: scheduled every 10 seconds.
- `Claim Next Job`: POSTs to `claim_next_video_job_fenced` with
  `p_worker_id` and `p_lease_seconds`.
- `Job Claimed`: tests for a claimed response.
- `Extract Job Info`: reads nested `job`, `lease_token`, `attempt_number`, and
  `pipeline_revision`, then maps them to the downstream context names
  `jobId`, `leaseToken`, `attemptNumber`, and `pipelineRevision`.
- `Call Generate Script`, `Call Generate Images`, `Call Generate Narration`,
  `Call Build Captions`, `Call Build Manifest`, and `Call Render Video`.
- Existing error reporting paths that preserve the lease context.

The live cutover must verify that the deployed WF03 version matches this
prepared response-shape handling before enabling it. The legacy claim contract
must remain available as the rollback path.

### WF04-WF09 Stage Workflows

Each stage currently contains the Checkpoint 1A stage lifecycle elements:

- `begin_job_stage`
- `reserve_stage_external_attempt`
- `heartbeat_video_job`
- `finalize_stage_success`
- stage-specific `fail_job_stage` paths where present

The expected explicit next-stage sequence is:

```text
generate_script -> generate_images -> generate_voice ->
build_captions -> build_manifest -> render -> completed
```

The cutover plan must verify that every stage receives and preserves the same
lease token, attempt number, pipeline revision, stage-run ID, and run token.
The plan must also identify where `release_video_job` is required. It must not
be added implicitly to a workflow without checking whether
`finalize_stage_success` already owns that state transition.

## Cancellation Data-Layer Contract

The current cancellation endpoint directly sets `status = 'cancelled'` and
`current_step = 'cancelled'` without clearing lease fields. Current late
callback behavior is not sufficient:

- `release_video_job` raises `JOB_TERMINAL` or `LEASE_LOST`.
- `heartbeat_video_job` raises `LEASE_LOST`.
- `finalize_stage_success` cannot update the cancelled job and raises
  `LEASE_LOST` after its transaction prevents partial mutation.
- The reaper excludes cancelled rows, leaving stale lease metadata behind.

Before WF04 cutover, the data-layer design must add an explicit non-error
cancelled outcome named `CANCELLED_NOOP`. Heartbeat, release, and finalization
use this uniform response envelope:

```json
{
  "ok": true,
  "status": "cancelled",
  "outcome": "CANCELLED_NOOP",
  "lease_expires_at": null
}
```

The envelope is returned without stage advancement:

- preserve `status = 'cancelled'`;
- clear `lease_token`, `lease_expires_at`, `heartbeat_at`, `claimed_by`, and
  `claimed_at` when a late lease callback observes cancellation;
- never advance `next_stage`, `last_completed_stage`, progress, or terminal
  output fields;
- make heartbeat return the explicit cancelled outcome without extending the
  lease;
- make release/finalization return the explicit cancelled outcome without
  resurrecting or advancing the job.

This does not stop the running n8n execution. Execution cancellation is a
separate future feature.

## Rollout Options

The implementation plan must compare:

1. **Feature-flagged rollout:** select legacy or fenced claim through an
   environment-controlled mode, preserving fast rollback without a migration.
2. **Parallel/shadow validation:** call or validate the fenced path without
   assigning work, then enable it after observed agreement.
3. **All-at-once cutover:** replace the live claim path after all workflow and
   data-layer checks pass.

The selected approach is a feature-flagged rollout with a controlled canary.
The claim mode flag should default to `legacy`; setting it to `fenced` enables
the new claim contract for the canary worker. Rollback is the reversible change
back to `legacy`, without rolling back the database migration. The exact flag
owner remains an open decision.

Because only one live WF03 worker is currently active, the canary should be a
disabled/manual clone of the worker. It can be invoked only through a separate
approved test procedure; the active production worker remains on the legacy
claim mode until the canary evidence is reviewed.

## Open Decisions

Open questions must be approved one at a time before implementation planning:

- Which exact live WF03 version is the deployable fenced-claim candidate? The
  current live version is `94e2c8e6-74a6-4d53-be02-5bac3eb9dabb` and still uses
  the legacy claim RPC; the repository copy contains the prepared fenced path.
- The existing `finalize_stage_success` boundary owns `release_video_job` for
  normal stage success. WF04-WF09 pass the lease token through and do not
  release independently.

## Safety Boundaries

Until the design is approved and implemented separately:

- Do not modify WF03-WF09.
- Do not create or claim a real job.
- Do not switch provider modes.
- Do not run migration repair.
- Do not activate WF19.
- Do not treat the unverified 66-minute figure as a lease requirement.
