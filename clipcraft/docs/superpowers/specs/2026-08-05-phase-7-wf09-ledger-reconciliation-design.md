# Phase 7 WF09 And Ledger Reconciliation Design

## Status

Approved design for two strictly separated phases:

1. Repair and verify WF09 graph reachability.
2. Only after mandatory Gate A passes, restore the `begin_job_stage` ledger
   contract with an additive migration.

No production job may be created until both phases and their post-change
validation pass.

## Goals

- Make the existing WF09 stage wrapper reachable from its workflow trigger.
- Make successful rendering reach fenced stage finalization.
- Preserve WF09 renderer, provider, asset, status, and live operational behavior.
- Prove stage context propagation without invoking a provider or renderer.
- Restore the approved stage-ledger begin semantics through an additive
  migration only.
- Preserve rollback boundaries and stop at the first new blocker.

## Non-Goals

- No effective-input hash redesign.
- No provider, renderer, asset, prompt, model, or adapter changes.
- No unrelated workflow repair.
- No regeneration or production retry.
- No mutation of the previously failed production job.
- No production generation before both phases pass.

## Current State

WF09 contains the intended stage wrapper:

`Normalize Stage Context -> Hash Stage Input -> Begin Stage -> Merge Stage Context -> Stage Started? -> Reserve External Attempt -> Merge Attempt Context -> Heartbeat Stage Lease -> Merge Heartbeat Context -> Validate Input`

The wrapper is currently bypassed because:

`Workflow Trigger -> Validate Input`

The successful render chain currently ends at `Build Response`, while
`Finalize Stage` has no incoming edge. Therefore the stage cannot be finalized
through the fenced RPC.

The active `begin_job_stage` function also differs from the approved contract:

- It does not validate non-empty item keys.
- It does not compare an existing row's `input_hash`.
- It creates a new run token for an existing running row.
- It does not return `UNKNOWN_OUTCOME` or terminal `FAILED` states.
- It does not refresh ownership fields on an eligible retry.
- Its cached-success response has no run token, while WF04 currently requires
  one before routing by state.

## Phase A: Minimal WF09 Graph Repair

### Allowed Changes

Exactly two executable graph edges may change:

1. Replace `Workflow Trigger -> Validate Input` with
   `Workflow Trigger -> Normalize Stage Context`.
2. Add `Build Response -> Finalize Stage`.

No node parameters, node identities, node code, credentials, settings, static
data, or other connections may change.

### Resulting Data Flow

Started path:

`Workflow Trigger -> Normalize -> Hash -> Begin -> Merge -> Stage Started? -> Reserve -> Merge Attempt -> Heartbeat -> Merge Heartbeat -> Validate -> existing render chain -> Build Response -> Finalize Stage -> Return Stage Result`

Cached-success path:

`Stage Started? -> Return Cached Stage`

The cached path must not invoke the renderer or finalization RPC.

### Phase A Tests

Tests must be written and observed failing before the workflow edit. They must
assert:

- Trigger reaches `Normalize Stage Context` and cannot bypass it.
- Normalize reaches Begin through `Hash Stage Input`.
- The started branch reaches reservation before `Validate Input`.
- `Validate Input` cannot be reached from the trigger without passing the
  reservation/heartbeat path.
- `Build Response` reaches `Finalize Stage`.
- `Finalize Stage` reaches `Return Stage Result`.
- The cached branch cannot reach renderer nodes.
- Every non-approved WF09 node, parameter, and connection remains equal to the
  pre-edit workflow.

### Provider-Free Phase A Probe

The probe will create a temporary inactive workflow, validate its audited node
set, activate it only for the controlled invocation, and delete it in `finally`.
It will reuse the reviewed live normalization/hash/context logic and use fixed
Code-node stubs for:

- `begin_job_stage`
- `reserve_stage_external_attempt`
- `heartbeat_video_job`
- render output
- finalization boundary capture

It will not include HTTP Request, Execute Workflow, provider, TTS, filesystem,
or renderer nodes.

The probe must prove:

- The workflow's stage-initialization boundary accepts a fixed audited
  `STARTED` response.
- The canonical run token reaches the finalization boundary unchanged.
- The canonical input hash reaches the finalization boundary unchanged.
- The workflow's stage-finalization boundary is reached exactly once with the
  expected fenced payload.
- Provider calls are `0`.
- Renderer invocations are `0`.
- Temporary workflow cleanup is verified by HTTP `404`.

### Live Deployment

- Confirm zero active jobs, leases, and running executions.
- Back up live WF09 under its existing ID.
- Verify live WF09 equals the reviewed pre-edit definition.
- Update only WF09.
- Preserve workflow ID, name, active state, settings, and static data.
- Verify the live executable graph differs only by the two approved edges.
- Run the provider-free Phase A probe.

## Mandatory Gate A

Phase B must not begin unless every condition passes:

- WF09 graph repair is verified locally and live.
- Provider-free probe passes.
- Stubbed stage initialization succeeds within the provider-free workflow
  probe.
- The stubbed stage-finalization boundary succeeds within the provider-free
  workflow probe.
- `runToken` reaches `Finalize Stage` unchanged.
- `inputHash` reaches `Finalize Stage` unchanged.
- Provider invocations are `0`.
- Renderer invocations are `0`.
- No workflow drift exists outside the two approved WF09 edges.
- Active jobs are `0`.
- Active leases are `0`.
- Running n8n executions are `0` after probe cleanup.

Gate A validates WF09 graph and context propagation without database mutation.
It does not claim that the current remote `begin_job_stage` implementation is
correct; real ledger semantics are the subject of Phase B SQL tests.

If any condition fails:

- Stop immediately.
- Preserve the WF09 backup and current live evidence.
- Write the checkpoint blocker report.
- Do not create or apply a database migration.
- Do not create a production job.

## Phase B: Additive Stage-Ledger Migration

### Migration Scope

Create one new additive migration that replaces only
`public.begin_job_stage` while preserving its public signature, grants, security
model, and callers.

The function must:

- Reject null or blank `p_item_key` with `INVALID_ITEM_KEY`.
- Validate the current job lease before stage mutation.
- Lock the authoritative stage row by
  `(job_id, pipeline_revision, stage, item_key)`.
- Raise `INPUT_HASH_MISMATCH` when an existing row's hash differs.
- Return `CACHED_SUCCESS` and existing output for succeeded rows.
- Return `UNKNOWN_OUTCOME` without starting work for unknown outcomes.
- Return `RUNNING` with the existing run token for running rows.
- Return terminal `FAILED` without restarting non-retryable failed rows.
- Restart only eligible rows with one new run token.
- Refresh `worker_id`, `lease_token`, `job_attempt_number`, and heartbeat fields
  on eligible retry.
- Insert new rows with explicit run token, ownership, start time, and heartbeat.

No generated IDs may be hardcoded in the migration.

### Workflow Compatibility

WF04 `Merge Stage Context` must require a valid run token for states that permit
work, especially `STARTED`, but allow `CACHED_SUCCESS` to route without a run
token because the cached response does not create one.

Other non-start states remain safe stops:

- `RUNNING`, `UNKNOWN_OUTCOME`, and `FAILED` must not reach provider, renderer,
  TTS, filesystem, or finalization side effects.
- Existing reconciliation errors may remain explicit if no automatic recovery
  contract is approved.

### Phase B Tests

Write failing tests before migration/workflow changes for:

- First insert returns `STARTED` with a run token and ownership.
- Existing succeeded row plus same hash returns `CACHED_SUCCESS`.
- Existing row plus different hash raises `INPUT_HASH_MISMATCH`.
- Existing running row returns `RUNNING` with the same token and no mutation.
- Existing unknown outcome returns `UNKNOWN_OUTCOME`.
- Existing non-retryable failure returns `FAILED`.
- Eligible retry refreshes ownership and creates one new token.
- Blank item key raises `INVALID_ITEM_KEY`.
- WF04 cached success does not require a run token.
- WF04 started work still requires a valid run token.

Use local database testing when available. Before remote DDL:

- List current tables/migrations.
- Confirm Gate A remains true.
- Apply the migration once through the migration tool.
- Run security and performance advisors after DDL.
- Run direct SQL contract probes without provider calls.

### Phase B Rollback

The migration report must include the prior function definition and a reviewed
rollback migration strategy. Do not mutate migration history or edit an applied
migration in place.

## Final Validation Gate

After Phase B:

- Run the full ClipCraft suite.
- Run custom n8n node tests.
- Run WF04 and WF09 provider-free probes.
- Re-run SQL stage-ledger contract probes.
- Confirm zero active jobs, leases, and executions.
- Confirm no provider or renderer invocation occurred during validation.
- Review repository/live workflow equality and migration state.

Only after every check passes may the runner create exactly one new controlled
production job.

If any new blocker appears:

- Stop immediately.
- Do not retry or create another production job.
- Preserve rollback boundaries and evidence.
- Produce a complete blocker report.

## Security And Observability

- Do not log API keys, service-role keys, lease tokens, credentials, prompts,
  provider bodies, or binary assets.
- Temporary probe workflows must contain no credentials and no external-call
  node types.
- Use finite Docker and HTTP timeouts.
- Verify temporary workflow deletion.
- Reports may include workflow IDs, execution IDs, version IDs, counts, error
  classes, and fixed non-secret test UUIDs.

## Success Criteria

The design is complete when:

- WF09's fenced wrapper and finalization are reachable with only two graph-edge
  changes.
- Gate A passes completely.
- The additive ledger migration restores the approved begin semantics.
- Workflow cached/running state handling remains side-effect safe.
- All tests and provider-free probes pass.
- No production job exists before the final gate.
- One controlled production job may proceed only after explicit evidence that
  all gates pass.
