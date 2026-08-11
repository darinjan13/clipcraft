# Implementation Log

## 2026-07-27: WF17/WF18 Canonical Contract

- Replaced repository WF17 and WF18 definitions with the approved validation,
  bounded-retry, and normalized-response topology.
- Migrated WF01, WF03, WF04, WF05, and WF12 to consume canonical fields and
  route provider failures before persistence or file writes.
- Added WF18 context propagation for `jobId`, `sceneId`, and `sceneIndex`.
- Added static contract fixtures and repository workflow inspection to
  `functional_tests.py`.
- Completed caller safety fixes for WF03 JSON-safe error payloads, WF04
  response fan-in, WF05 pending-scene/per-item execution, and WF12 single-path
  regeneration execution.
- Runtime API and webhook execution remain disabled for this milestone.
- Static evidence: all seven modified workflow JSON files parse successfully;
  `py -3 -m py_compile functional_tests.py` passes; static contract checks pass.

## Remaining Risks

- Runtime n8n workflow IDs, active state, and deployed topology remain unknown.
- Nested-body WF18 context behavior has not been exercised against a live
  Execute Workflow node.
- n8n Execute Workflow and parallel side-effect scheduling require a runtime-
  approved integration pass.

## 2026-07-26: Milestone 2 Runtime Verification

- Authenticated through the documented public API using `X-N8N-API-KEY`.
- Exported live WF17/WF18 definitions before mutation to
  `artifacts/milestone-2-runtime-backup/`.
- Updated both live workflows with public `PUT /api/v1/workflows/{id}` and
  preserved their active state as `true`.
- Added the runtime-required `Workflow Trigger` `events: ["update"]` field to
  both canonical repository definitions after n8n rejected empty trigger
  parameters.
- Final live comparisons classified both WF17 and WF18 as
  `MATCHES_REPOSITORY`.
- Ran 11 approved validation-only cases through disposable public-API-created
  parent workflows. Every case returned the canonical validation error
  envelope and omitted `Call Provider API`, `Check Retry`, `Retry`, and
  `Increment Retry` from executed nodes.
- WF18 context normalization and `_testCorrelationId` preservation passed when
  the disposable parent unwrapped webhook `body` before Execute Workflow.
- Disposable parents were deactivated, deleted, and verified with HTTP 404.
- No Cloudflare or Supabase request was made.

### Timeout Recovery

- The timed-out runner used a 60-second polling deadline for each of 11 cases,
  exceeding the 600-second process limit, and searched only top-level trigger
  fields while webhook payloads were nested under `body`.
- Child executions completed successfully, but the parser never correlated
  them. The parent cleanup `finally` block could not run after process timeout.
- Added `milestone2_validation.py` with startup stale-parent cleanup, one
  parent per case, 20-second case bounds, a 300-second total bound, persisted
  parent state, signal/exit cleanup, nested marker extraction, and malformed
  execution handling.

## 2026-07-26: Milestone 3 Provider Checkpoint

- Preflight confirmed both live workflows matched the repository and remained
  active; no stale Milestone 3 disposable parents existed.
- One approved WF17 success-path case made exactly one Cloudflare request.
- Cloudflare returned a successful provider response, but WF17 failed in
  `Check Retry` before normalization because `$('Retry').all()` was evaluated
  before the `Retry` node had executed. n8n reported `Node 'Retry' hasn't been
  executed`.
- No WF18 provider request, failure test, retry test, or exhaustion test was
  attempted after this canonical defect was confirmed.
- The disposable WF17 parent was deactivated, deleted, and verified with
  HTTP 404. No Milestone 3 disposable parent remains.

## 2026-07-26: Milestone 3A Retry Repair Checkpoint

- Backed up the accepted live WF17/WF18 definitions before mutation.
- Replaced future-node retry inference with explicit item-level `retryCount`,
  `Prepare Provider Attempt`, `Evaluate Provider Result`, `Retryable Failure?`,
  and bounded `Increment Retry` flow.
- Published both workflows through public `PUT /api/v1/workflows/{id}` with
  HTTP 200; both remained active and matched repository source afterward.
- Validation regression passed for four cases with no provider or retry-node
  execution.
- One real WF17 success and one real WF18 success passed after repair; three
  real Cloudflare calls have been made cumulatively across Milestones 3 and 3A.
- Disposable retry stubs verified retry-one success, retry-two success, and
  retry exhaustion for both workflows.
- Retry stubs exposed a second defect: non-retryable failures currently set
  `retryExhausted` and normalize as `RETRY_EXHAUSTED` instead of `PROVIDER_ERROR`.
  No further mutation or provider call was made after this defect was found.

## 2026-07-26: Milestone 3B Non-Retryable Classification Fix

- Backed up the accepted Milestone 3A live definitions before mutation.
- Changed both evaluators to set exhaustion only when
  `!providerSuccess && retryableProvider && retryCount >= 2`.
- Published WF17 and WF18 with HTTP 200 and preserved active state.
- Static truth-table checks now cover success, retryable pre-exhaustion,
  retryable exhaustion, and non-retryable failure.
- Both non-retryable stub cases now return `PROVIDER_ERROR` with zero retries.
- The complete eight-case WF17/WF18 retry-stub matrix passes.
- Minimal validation regression passes for both workflows.
- No real Cloudflare calls were made during Milestone 3B.
