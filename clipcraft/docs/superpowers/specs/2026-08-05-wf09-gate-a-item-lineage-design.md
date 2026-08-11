# WF09 Gate A Item-Lineage Reconciliation Design

## Root Cause

Gate A execution `38153` emitted one item through `Merge Stage Context`, then
stopped at `Stage Started?`. The deployed n8n runtime logged:

`Unknown filter parameter operator "boolean:equal"`

WF09's cloned If v2 node uses operation `equal`, omits the required filter
`combinator`, and omits canonical strict filter options. n8n treats the unknown
operator as false rather than throwing. The sole item was routed to false output
1, which the provider-free probe intentionally leaves disconnected. No later
node executed. The workflow saved as success, but webhook `lastNode` extraction
looked at empty output 0 and returned HTTP 500 `No item to return was found`.

## Scope

Change only WF09 `Stage Started?` filter parameters and the Gate A
probe/test/report artifacts required to verify item lineage. Preserve the two
approved graph edges, every other node and connection, renderer/status/asset
behavior, stage hashing, run-token semantics, and live identity/settings.

Do not begin ledger work, call external systems, create a production job, or
modify WF02-WF08/WF17/WF18.

## Canonical If Contract

`Stage Started?` must use the deployed If v2 filter schema:

```json
{
  "conditions": {
    "options": {
      "caseSensitive": true,
      "leftValue": "",
      "typeValidation": "strict",
      "version": 1
    },
    "conditions": [
      {
        "leftValue": "={{ $json.stageState === 'STARTED' }}",
        "rightValue": true,
        "operator": {
          "type": "boolean",
          "operation": "equals"
        }
      }
    ],
    "combinator": "and"
  },
  "options": {}
}
```

True output remains index 0 and false output remains index 1. No graph edge
changes are allowed in Checkpoint 1Q.

## Item Contract

The offline and live Gate A paths must prove one item at each boundary:

1. Probe input: fixed safe context.
2. Normalize: one item with job/stage/lease/attempt/revision and
   `stageHashInput`.
3. Hash: one item with lowercase 64-character `inputHash`.
4. Begin stub: one `STARTED` response item.
5. Merge Stage: one item with unchanged `runToken` and `inputHash`.
6. Stage Started: true output one item, false output zero items.
7. Reserve, Merge Attempt, Heartbeat, Merge Heartbeat: one item each.
8. Provider-free completion and Build Response: one item each preserving stage
   identity, run token, hash, attempt, and revision.
9. Finalize Boundary: exactly one input and one safe terminal item.

Native If supplies deterministic paired-item lineage for its input. Code-node
stubs must return n8n item arrays and preserve one-to-one input lineage; explicit
`pairedItem: { item: 0 }` is required where a stub constructs a fresh item.

## Tests

Before editing WF09:

- Add static tests for the exact canonical If schema.
- Add a native n8n 2.29.7 offline workflow harness using only Manual Trigger,
  Code, Crypto, and If nodes.
- Execute it through `n8n execute --rawOutput` without HTTP, provider, renderer,
  database, credentials, or production persistence.
- Assert per-node output counts and If branch counts from `runData`.
- Observe RED on current `boolean:equal` behavior.

After the minimal parameter fix, the same harness must pass with one item at
every boundary and one final terminal item. Static drift tests must prove only
the `Stage Started?` parameters changed from the live backup.

## Live Safety

- Confirm zero active jobs, leases, and relevant executions.
- Export and back up live WF09.
- Verify repository/live equality before the update except for the reviewed If
  parameter change.
- Update only WF09 and preserve ID, active state, node count, settings, static
  data, all edges, credentials, and renderer/status/asset behavior.

## Gate A

Run the provider-free Gate A probe exactly once after offline tests and live
scope verification pass. Gate A passes only if all mandatory output, lineage,
zero-call, cleanup, and quiescence conditions pass.

If it fails, mark `GATE_A_BLOCKED_ITEM_LINEAGE`, update the report, and stop
without Phase B. If it passes, mark `GATE_A_PASSED` and continue to the already
approved additive ledger reconciliation.
