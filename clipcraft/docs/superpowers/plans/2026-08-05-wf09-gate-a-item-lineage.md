# WF09 Gate A Item-Lineage Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Reproduce the WF09 zero-item failure offline under native n8n semantics, repair only the invalid `Stage Started?` filter schema, and rerun Gate A exactly once.

**Architecture:** A generated offline workflow uses the deployed n8n CLI and the same production nodes/stubs as Gate A, with no external-capable nodes. RED must show the If node routing the sole item to false output. The production fix changes only the If filter parameters. Live update and one Gate A retry occur only after native runtime and drift tests pass.

**Tech Stack:** n8n 2.29.7, n8n-nodes-base 2.29.6, Node.js, Docker, Python/pytest.

---

### Task 1: Add Native Runtime RED Harness

**Files:**
- Create: `clipcraft/scripts/wf09_gate_a_offline_runtime.js`
- Modify: `clipcraft/tests/test_workflow_integration.py`

- [ ] Add a static test requiring exact canonical If v2 schema with
  `combinator="and"`, strict options, and boolean operation `equals`.
- [ ] Add a Node harness that reads current WF09 nodes, builds an offline graph
  with Manual Trigger and a fixed Code input, then uses the same Normalize,
  Hash, Merge, If, attempt, heartbeat, completion, response, and final boundary
  contracts as the live probe.
- [ ] Restrict node types to Manual Trigger, Code, Crypto, and If; reject
  credentials, `$env`, HTTP, Execute Workflow, renderer, provider, and
  filesystem nodes.
- [ ] Every fresh Code stub item must return `[{json: {...}, pairedItem:{item:0}}]`.
- [ ] Execute through the deployed container with `n8n execute --rawOutput`,
  using a temporary workflow file and finite Docker timeout. Clean up the file
  in `finally`.
- [ ] Parse `resultData.runData` and report output counts for both If branches
  and every downstream node.
- [ ] Run the focused test and observe RED: runtime warning
  `boolean:equal`, true output count 0, false output count 1, no reserve/final
  node.

### Task 2: Apply Minimal If Schema Fix

**Files:**
- Modify: `clipcraft/workflows/09-render-video.json`
- Test: `clipcraft/tests/test_workflow_integration.py`

- [ ] Replace only `Stage Started?` parameters with the canonical schema from
  the design.
- [ ] Run the offline native harness and require one item on true output, zero
  on false output, one item at every later boundary, and one final item.
- [ ] Run focused item-lineage tests and the full integration suite.
- [ ] Mechanically compare against the current live backup and prove no node,
  edge, setting, static-data, renderer, status, or asset drift outside the If
  parameters.

### Task 3: Back Up And Update Live WF09

- [ ] Confirm active jobs, leases, and executions are zero.
- [ ] Create a new coherent timestamped backup set and record WF09 backup.
- [ ] Import through the rollback-capable importer; WF05-WF08 must be skipped
  and only WF09 may update.
- [ ] Verify live/repository executable equality, ID, active state, node count,
  settings, static data, graph edges, credentials, and no external behavior
  drift.

### Task 4: Run Gate A Once

- [ ] Run `controlled_wf09_graph_no_provider_probe.js` exactly once.
- [ ] Require `gateA`, finalization, token, hash, one-item, zero-provider,
  zero-renderer, cleanup, and quiescence conditions.
- [ ] If any condition fails, update the report with
  `GATE_A_BLOCKED_ITEM_LINEAGE` and stop.
- [ ] If all pass, update the report with `GATE_A_PASSED` and continue to Phase B
  from `2026-08-05-phase-7-wf09-ledger-reconciliation.md` Task 6.

### Task 5: Update Complete Report

- [ ] Append execution `38153`, runtime warning, exact missing-item source,
  before/after item contracts, files/nodes changed, tests, backup/live versions,
  Gate A result, call counts, cleanup, state, and whether Phase B began to
  `clipcraft/docs/superpowers/reports/2026-08-05-phase-7-checkpoint-1p-wf09-ledger-reconciliation.md`.
- [ ] Run final focused tests and request code review before claiming status.

## Stop Rules

Stop without Phase B if native n8n RED cannot reproduce the If branch loss, the
fix requires broader production changes, any external call occurs, live drift
exceeds the If parameters, Gate A fails, or quiescence cannot be proven.
