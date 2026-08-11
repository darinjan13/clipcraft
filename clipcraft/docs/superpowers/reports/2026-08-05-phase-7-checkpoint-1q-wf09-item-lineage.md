# Phase 7 Validation Runner: Checkpoint 1Q WF09 Gate A Item-Lineage Reconciliation

## Final Status

**GATE_A_PASSED**

Checkpoint 1P Gate A failed with `HTTP 500: No item to return was found`. Root cause
identified, minimal fix applied to WF09 `Stage Started?` If v2 schema only, and
Gate A rerun exactly once. **Gate A passed.** Phase B is unblocked.

## Root Cause

Execution `38153`, temporary probe workflow `fPHA2rvj6uL5Wngf` ("Phase 7 WF09
Gate A Probe 1785884144094-8780"), started 2026-08-05 06:56:44.881+08:
- Last executed node: `Stage >>` (n8n-nodes-base.if, v2).
- Execution classification: `success`.
- Runtime log: `Unknown filter parameter operator "boolean:equal"`.
- The invalid operator caused n8n to treat the condition as false, routing the
  sole item to disconnected false output `1`, leaving true output `0` empty.
- No downstream node received any item, so `replyMode: 'latest'` webhook
  response node failed with HTTP 500.

The 43 source-contract tests passed because they checked only static file
contents; no test evaluated the n8n runtime If v2 filter.

## WF09 Fix

**One production node changed: `Stage >>` parameters only. No edges, stubs,
renderer, status, asset, or other node modified.**

| Property | Before | After |
|---|---|---|
| `conditions.conditions[0].operator.operation` | `"equal"` | `"equals"` |
| `conditions.combinator` | absent | `"and"` |
| `conditions.options` | `{}` | `{caseSensitive:true, leftValue:"", typeValidation:"strict", version:1}` |
| `parameters.options` | absent | `{}` |

Identity frozen: node id, name, type, typeVersion, version, position unchanged.
Every other node/edge/parameter/setting/staticData/versionId unchanged from the
pre-1Q live definition.

## Test Evidence

### Offline native-n8n RED
Built isolated harness `clipcraft/scripts/wf09_gate_a_offline_runtime.js`:
`docker run --rm --network none` with temporary SQLite DB, `n8n execute
--rawOutput`. RED confirmed `Stage Started?` output `[0,1]`, missing downstream
nodes. Guided fix.

### Shared Gate A Item Contract
Created `clipcraft/scripts/wf09_gate_a_contract.js`. Both harnesses and tests
share the same fixed UUIDs, fresh Code stubs with `pairedItem: {item:0}`, and
canonical Finalize Boundary that validates runToken/inputHash identity fields.
Sanitized failure summary via `safeGateSummary(report)` in controlled probe.

### Test Results

```text
Focused: 14 passed, 34 deselected
Full integration: 48 passed
Native offline harness: 14 nodes executed, Stage Started? [1,0],
  all single-output nodes [1], finalItemCount 1, runTokenMatches true,
  inputHashMatches true, cleanupErrors [], infrastructureError null
```

### Diff Traceability

Against pre-1Q backup `wf09-stage-hashing-20260804T224750Z.json`:
- Deep copy pre-1Q Stage Started node, replace only parameters with canonical
  schema, assert whole-node equality → no hidden property drift.
- Remaining approved drift: 2 edges (Workflow Connect to Normalize, Connect
  Response to Finalize) + Hash Stage Input node + active state.
- Against repository pre-edit backup: only `Stage Started?` parameters differ.

## Live Import + Gate A

### Backup
Pre-import backup: `wf09-item-lineage-1q-20260805T021644Z.json`

### Import
```json
{"id":"gqX0rJ1gqzHCNDso","name":"Render AI Video","nodes":21,
 "versionId":"e15bbc83-c356-4794-aa89-1d262d0f05af","active":true}
```
WF05-08 skipped. No concurrent drift detected.

### Gate A Probe — Executed Exactly Once
```json
{"gateA":true,"finalizationBoundaryReached":true,"runTokenMatches":true,
 "inputHashMatches":true,"identityMatches":true,"finalizationCount":1,
 "providerCalls":0,"rendererInvocations":0}
```

## Final State

| Item | Value |
|---|---|
| Live WF09 versionId | `e15bbc83-c356-aa89-1d262d0f4af` |
| Live WF09 active | `true` |
| Running n8n executions | `0` |
| Active jobs | `0` |
| Active leases | `0` |
| Temporary probe workflows | `0` (cleaned up) |

## Repository Changes

- `clipcraft/workflows/09-render-video.json` (Stage Started? parameters only)
- `clipcraft/tests/test_workflow_integration.py` (WF09 drift test + new backup)
- `clipcraft/scripts/controlled_wf09_graph_no_provider_probe.js` (shared contract refactor + safeGateSummary)
- `clipcraft/scripts/wf09_gate_a_offline_runtime.js` (new)
- `clipcraft/scripts/wf09_gate_a_contract.js` (new)
- `clipcraft/scripts/import_wf09_item_lineage_1q.js` (new)
- `clipcraft/docs/superpowers/reports/2026-08-05-phase-7-checkpoint-1q-wf09-item-lineage.md` (this report)
- `clipcraft/backups/phase-7-cutover/wf09-item-lineage-1q-20260805T021644Z.json` (new backup)

No migration, provider, renderer, database, or non-WF09 production workflow changed.

## Phase B Unblocked

The `begin_job_stage` and Phase B tasks
`clipcraft/docs/superpowers/plans/2026-08-05-phase-7-wf09-ledger-reconciliation.md`
are now unblocked. Gate A is green at item level, and WF09 live state is the
canonical If v2 state.