# Phase 7 Checkpoint 1G: WF02 Syntax Reconciliation

## Final Status

**WF02_BLOCKED_RUNTIME**

The WF02 syntax defect was isolated and minimally corrected. Repository parser
and focused contract tests passed, and the live WF02 workflow was updated while
preserving its public and downstream contracts. The single controlled create
probe persisted one disposable row, but the live queue path invoked a separate
legacy WF03 claim path and WF04 then failed before provider execution. The
probe row was safely cancelled and no full production generation was attempted.

## Root Cause

The `Validate and Create Job` Code node returned an array containing an object:

```javascript
return [{ json: {
  // fields...
  brief: {
    // fields...
  }
}];
```

The `brief` object was closed, but the outer item object was not. The malformed
tail `}];` therefore caused n8n's parser to reject the closing array bracket.
The exact corrected tail is `}}];`.

- Broken workflow: WF02, `UdY7u9pMHE6KrjFb`
- Broken node: `Validate and Create Job`
- Failure execution: `34485`
- Parser error: `SyntaxError: Unexpected token ']'`
- Parser location: `evalmachine.<anonymous>:40`, at `}];`

The failure was parse-time JavaScript syntax, not expression interpolation,
JSON embedding, optional chaining, browser API usage, or runtime validation.

## Repository And Live Drift

Repository and live WF02 contained the same malformed Code node source before
the fix. Other drift was operational n8n metadata only: active state, active
version identifiers, timestamps, and API-managed fields. Node names, count,
webhook path, connections, insert payload, and credential references matched.

No prior working WF02 backup existed in the repository. The live export was
saved before import at:

`backups/phase-7-cutover/wf02-syntax-reconciliation-2026-08-03T18-15-18-763Z`

It contains `workflow.json` and `metadata.json` for workflow ID
`UdY7u9pMHE6KrjFb`, active state `true`, 5 nodes, version
`1bad1860-f16c-427e-954e-46992e26147d`, and the pre-import hash.

## Minimal Fix

Changed only the malformed WF02 Code node source in:

- `workflows/02-create-video-job.json`

The correction adds one closing brace. Validation fields, duration rules,
scene-count bounds, defaults, UUID generation, brief shape, status fields,
snapshot/session handling, insert payload, response shape, and downstream
connections were preserved. No other workflow, migration, provider mode,
renderer, TTS, or frontend file was changed for the fix.

## Static And Focused Validation

The new test file is:

`tests/test_wf02_create_contract.py`

Test-first evidence:

- Before the fix: `7 failed, 1 passed`, all failures traced to the expected
  `Unexpected token ']'` parser error.
- After the fix: `8 passed`.

The parser test extracts the Code node source and compiles it using Node's
`new Function('$json', source)`, matching the Code-node JavaScript compilation
boundary. Focused tests cover valid payloads, required-field errors, duration
validation, scene-count clamping, exact output shape, secret/credential
exclusion, colon-containing model IDs, extra provider/snapshot fields, and
downstream insert payload wiring.

WF02's current source does not accept provider/model or snapshot fields as part
of its persisted brief. The focused test confirms those extras are not silently
added to the existing contract rather than introducing new validation logic.

## Live Import

Before import:

- Active jobs: `0`
- Active leases: `0`
- Running WF02 executions: `0` (execution `34485` was historical `error` with a
  stopped timestamp)

The first PUT was rejected by n8n because the API payload included unsupported
settings properties; it caused no workflow mutation. The corrected PUT used
the existing API-compatible settings subset and succeeded.

Post-import:

- Workflow ID: `UdY7u9pMHE6KrjFb`, unchanged
- Name: `Create AI Video Job`, unchanged
- Active: `true`, preserved
- Node count: `5`, unchanged
- Webhook: `POST /webhook/videos/create`, unchanged
- Changed nodes: `Validate and Create Job` only
- Live parser compilation: passed
- Workflow count: `15`, unchanged
- Credential count: `1`, unchanged
- No missing-node warning observed

## Controlled Create Probe

Exactly one controlled create request was sent to the live WF02 boundary. No
second create request was sent.

- Probe channel: `phase7-checkpoint-1g-probe`
- Create execution: `34703`, success
- Disposable job ID: `96dd6a0e-13c7-48e2-bfa3-846a490f75fd`
- Persistence: succeeded
- Persisted status before cleanup: `generating_script`
- Persisted progress: `5`
- Persisted brief: 30 seconds, 6 scenes, English, exact probe fields
- Secrets/credential fields persisted: none

The create response itself was not used as the source of truth for cleanup;
Supabase confirmed the persisted row and its UUID.

## Controlled Probe Blocker

The disposable row was claimed by the live WF03 queue worker using the legacy
RPC:

```text
/rest/v1/rpc/claim_next_video_job
```

Read-only live inspection confirmed WF03 version
`94e2c8e6-74a6-4d53-be02-5bac3eb9dabb` still references the legacy claim path,
while the repository contract expects the fenced claim path. WF03 was not
modified in this checkpoint because it is outside scope.

Execution timeline:

1. WF02 create execution `34703` persisted the disposable row.
2. WF03 execution `34704` claimed the row through the legacy path and then
   failed at `Call Generate Script` with `Bad request - please check your
   parameters`.
3. WF04 execution `34705` failed at `Finalize Provider Failure` with the same
   `Bad request - please check your parameters` error.
4. No WF17 execution was created.
5. No provider call was started.
6. No image, TTS, caption, manifest, renderer, or media execution occurred.

## Cleanup

The existing `request_cancel_video_job` RPC was not present in the live schema
cache and returned `PGRST202`. Because the disposable row had no lease token,
it was cancelled with a guarded service-role update matching its ID, status,
and null lease state.

- Final status: `cancelled`
- Final step: `cancelled`
- Claimed worker: `null`
- Lease token: `null`
- Active jobs after cleanup: `0`
- Active leases after cleanup: `0`
- Historical production jobs: untouched

## Verification Results

Focused WF02 tests passed: `8 passed`.

The full workflow suite, backend/Python suite, custom-node suite, frontend
production build, Docker Compose validation, secret scans, and broader
compatibility/security reviews were intentionally not run after the controlled
probe exposed the out-of-scope live WF03/WF04 blocker. The checkpoint stopped
as required rather than broadening scope or masking the blocker.

Read-only compatibility review confirmed:

- Internal provider modes remained configured.
- WF03 claim drift exists in the live deployment and was not changed.
- No lease migration, renderer, TTS, frontend, WF17, or WF18 change was made.
- No provider quota or billing was consumed.
- No secret appeared in workflow source, probe payload, or captured output.

## Remaining Issues

- Reconcile live WF03 from legacy claim to the approved fenced claim path in a
  separate authorized checkpoint.
- Diagnose the live WF04 `Finalize Provider Failure` bad-request path after WF03
  reconciliation.
- Restore a verified cancellation RPC path or approved cleanup harness for
  future disposable probes.
- Do not create another full production job until these blockers are resolved
  and explicitly approved.

## Readiness

WF02 syntax is reconciled and its focused contract is verified. The system is
not ready for one new full end-to-end generation because live WF03/WF04 runtime
compatibility remains blocked.

## Follow-Up Reconciliation

Checkpoint 1H reconciled the live WF03 claim path, but its disposable probe
crossed into WF17 and attempted the internal Cloudflare text path before the
execution-stop guard took effect. The probe was stopped and cleaned up; no full
production generation was authorized or attempted.
