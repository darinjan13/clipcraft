# Phase 7 WF09 And Ledger Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair WF09's fenced graph, pass mandatory Gate A without external calls, restore `begin_job_stage` through one additive migration, and permit at most one controlled production job after all gates pass.

**Architecture:** Phase A changes exactly two WF09 edges and validates them with static graph tests plus an isolated provider-free n8n probe. Gate A is a hard stop between workflow and database work. Phase B creates one additive function-replacement migration, adds transaction-rolled-back SQL contract probes, reconciles WF04 cached-success token handling, and reruns every gate before production.

**Tech Stack:** n8n 2.29.7 workflow JSON, n8n core Crypto v2, Node.js 22, Python 3.11/pytest, Supabase Postgres/PLpgSQL, Supabase MCP, Docker.

**Workspace Note:** `C:\Users\Administrator\Desktop\superpowers-test\clipcraft-ai` is not a Git repository. Steps that normally commit must instead record exact changed files and backups in the checkpoint report. Never initialize Git as part of this plan.

---

## File Map

- Modify: `clipcraft/workflows/09-render-video.json` - exactly two Phase A graph edges.
- Modify: `clipcraft/tests/test_workflow_integration.py` - WF09 reachability, drift, probe, and WF04 cached-state tests.
- Create: `clipcraft/scripts/controlled_wf09_graph_no_provider_probe.js` - isolated Gate A runtime probe.
- Reuse: `clipcraft/scripts/backup_stage_hashing_1o.js` - coherent pre-deployment workflow backup.
- Reuse: `clipcraft/scripts/import_stage_hashing_1o.js` - preflighted, rollback-capable live import that skips no-ops.
- Create via Supabase CLI: exactly one file matching `clipcraft/supabase/migrations/*_restore_begin_job_stage_contract.sql` - additive Phase B migration. The CLI owns the timestamp; do not invent it.
- Create: `clipcraft/supabase/tests/begin_job_stage_contract_probe.sql` - transaction-rolled-back SQL contract probe.
- Modify: `clipcraft/tests/test_foundation_contracts.py` - migration and SQL-probe contract tests.
- Create: `clipcraft/scripts/controlled_single_production_generation.js` - one-shot production gate runner.
- Create: `clipcraft/docs/superpowers/reports/2026-08-05-phase-7-checkpoint-1p-wf09-ledger-reconciliation.md` - Gate A, Phase B, and production evidence or first-blocker report.

---

### Task 1: Add Failing WF09 Graph Tests

**Files:**
- Modify: `clipcraft/tests/test_workflow_integration.py`
- Test: `clipcraft/tests/test_workflow_integration.py`

- [ ] **Step 1: Add exact graph contract tests**

Append tests with these assertions:

```python
def test_wf09_trigger_enters_fenced_stage_wrapper_without_bypass():
    data = workflow("09-render-video.json")
    edges = workflow_edges(data)

    assert data["connections"]["Workflow Trigger"]["main"] == [
        [{"node": "Normalize Stage Context", "type": "main", "index": 0}]
    ]
    assert path_exists(edges, "Workflow Trigger", "Validate Input")
    for required in (
        "Normalize Stage Context",
        "Hash Stage Input",
        "Begin Stage",
        "Merge Stage Context",
        "Stage Started?",
        "Reserve External Attempt",
        "Merge Attempt Context",
        "Heartbeat Stage Lease",
        "Merge Heartbeat Context",
    ):
        assert not path_exists(
            edges,
            "Workflow Trigger",
            "Validate Input",
            forbidden={required},
        ), f"WF09 bypasses required fenced node {required}"


def test_wf09_success_path_reaches_fenced_finalization():
    data = workflow("09-render-video.json")
    edges = workflow_edges(data)

    assert data["connections"]["Build Response"]["main"] == [
        [{"node": "Finalize Stage", "type": "main", "index": 0}]
    ]
    assert path_exists(edges, "Build Response", "Return Stage Result")
    assert "Return Stage Result" in edges["Finalize Stage"]


def test_wf09_cached_path_cannot_reach_renderer_or_finalization():
    edges = workflow_edges(workflow("09-render-video.json"))
    for target in ("Execute FFmpeg", "Finalize Stage", "Mark Completed"):
        assert not path_exists(edges, "Return Cached Stage", target)
```

- [ ] **Step 2: Add exact Phase A scope protection**

Extend the existing WF09 pre-cutover compatibility test so the only additional
connection differences permitted after the already-approved hash changes are:

```python
assert current["connections"]["Workflow Trigger"]["main"][0][0]["node"] == "Normalize Stage Context"
assert current["connections"]["Build Response"]["main"][0][0]["node"] == "Finalize Stage"

allowed_connection_drift = {"Normalize Stage Context", "Hash Stage Input", "Workflow Trigger", "Build Response"}
for source, outputs in backup["connections"].items():
    if source not in allowed_connection_drift:
        assert current["connections"][source] == outputs, f"unexpected Phase A connection drift: {source}"
```

The existing node comparison must continue proving that no node parameters or
node code changed.

- [ ] **Step 3: Run the focused tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.;clipcraft'; py -m pytest clipcraft/tests/test_workflow_integration.py -q -k "wf09_trigger or wf09_success_path or wf09_cached_path"
```

Expected: failures showing trigger target `Validate Input` and missing `Build Response` connection.

- [ ] **Step 4: Record the RED evidence**

Record test names and failure reasons in the checkpoint report draft. Do not
commit because this workspace has no Git repository.

---

### Task 2: Apply Exactly Two WF09 Edge Changes

**Files:**
- Modify: `clipcraft/workflows/09-render-video.json`
- Test: `clipcraft/tests/test_workflow_integration.py`

- [ ] **Step 1: Replace the trigger edge**

Change only this connection:

```json
"Workflow Trigger": {
  "main": [[{
    "node": "Normalize Stage Context",
    "type": "main",
    "index": 0
  }]]
}
```

- [ ] **Step 2: Add the finalization edge**

Add exactly:

```json
"Build Response": {
  "main": [[{
    "node": "Finalize Stage",
    "type": "main",
    "index": 0
  }]]
}
```

Do not alter any node, setting, metadata field, or other connection.

- [ ] **Step 3: Run focused tests and verify GREEN**

Run:

```powershell
$env:PYTHONPATH='.;clipcraft'; py -m pytest clipcraft/tests/test_workflow_integration.py -q -k "wf09"
```

Expected: all WF09 tests pass.

- [ ] **Step 4: Run the complete workflow integration suite**

Run:

```powershell
$env:PYTHONPATH='.;clipcraft'; py -m pytest clipcraft/tests/test_workflow_integration.py -q
```

Expected: all tests pass with no connection-drift failure.

- [ ] **Step 5: Review the exact scope mechanically**

Parse the current workflow and authoritative pre-cutover backup. Confirm every
node except the already-approved Normalize/Merge/Hash differences remains exact,
and connection differences are limited to:

```text
Normalize Stage Context
Hash Stage Input
Workflow Trigger
Build Response
```

Record the result in the report draft.

---

### Task 3: Build the Provider-Free WF09 Gate A Probe

**Files:**
- Create: `clipcraft/scripts/controlled_wf09_graph_no_provider_probe.js`
- Modify: `clipcraft/tests/test_workflow_integration.py`
- Test: `clipcraft/tests/test_workflow_integration.py`

- [ ] **Step 1: Add a failing probe source-contract test**

The test must read the new script and require all of these literal contracts:

```python
def test_wf09_provider_free_probe_covers_gate_a_without_external_nodes():
    source = (ROOT / "clipcraft" / "scripts" / "controlled_wf09_graph_no_provider_probe.js").read_text(encoding="utf-8")
    for name in (
        "Normalize Stage Context",
        "Hash Stage Input",
        "Merge Stage Context",
        "Stage Started?",
        "Merge Attempt Context",
        "Merge Heartbeat Context",
        "Finalize Boundary",
    ):
        assert name in source
    assert "runTokenMatches" in source
    assert "inputHashMatches" in source
    assert "finalizationCount" in source
    assert "providerCalls" in source
    assert "rendererInvocations" in source
    assert "providerCalls: 0" in source
    assert "rendererInvocations: 0" in source
    assert "validateProbeSafety(workflow)" in source
    assert "n8n-nodes-base.httpRequest" not in source
    assert "n8n-nodes-base.executeWorkflow" not in source
    assert "AbortController" in source
    assert "verify deletion" in source.lower() or "temporary workflow still exists" in source
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
$env:PYTHONPATH='.;clipcraft'; py -m pytest clipcraft/tests/test_workflow_integration.py -q -k "wf09_provider_free_probe"
```

Expected: failure because the probe script does not exist.

- [ ] **Step 3: Create the probe with an explicit safe node set**

The script must use this temporary graph and no other executable nodes:

```text
Webhook
-> Unwrap Probe Input
-> live Normalize Stage Context
-> live Hash Stage Input
-> Stub Begin Stage
-> live Merge Stage Context
-> live Stage Started?
-> Stub Reserve External Attempt
-> live Merge Attempt Context
-> Stub Heartbeat Stage Lease
-> live Merge Heartbeat Context
-> Stub Render Output
-> Stub Build Response
-> Finalize Boundary
```

Use fixed non-secret values:

```javascript
const expectedRunToken = '33333333-3333-4333-8333-333333333333';
const expectedStageRunId = '44444444-4444-4444-8444-444444444444';
const inputJobId = '11111111-1111-4111-8111-111111111111';
```

The stubs must return these exact contracts:

```javascript
const beginCode = `return [{json: {state: 'STARTED', stage_run_id: '${expectedStageRunId}', run_token: '${expectedRunToken}', output: null}}];`;
const reserveCode = "return [{json: {permitted: true, attempt_number: 1, remaining: 2}}];";
const heartbeatCode = "return [{json: {ok: true, cancel_requested: false}}];";
const renderCode = "const input = $json; return [{json: {...input, success: true, videoUrl: '/probe/video.mp4', thumbnailUrl: '/probe/thumb.jpg'}}];";
const buildResponseCode = "const input = $json; return [{json: {success: true, jobId: input.jobId, videoUrl: input.videoUrl, thumbnailUrl: input.thumbnailUrl, inputHash: input.inputHash, runToken: input.runToken}}];";
```

The final boundary must throw unless all checks pass:

```javascript
const finalizeCode = `
const items = $input.all();
if (items.length !== 1) throw new Error('FINALIZATION_INPUT_COUNT_INVALID');
const input = items[0].json;
const hashNodeInputHash = $('Hash Stage Input').first().json.inputHash;
const runTokenMatches = input.runToken === '${expectedRunToken}';
const inputHashMatches = typeof input.inputHash === 'string' && /^[0-9a-f]{64}$/.test(input.inputHash) && input.inputHash === hashNodeInputHash;
if (!runTokenMatches || !inputHashMatches) throw new Error('WF09_GATE_A_FAILED');
return [{json: {gateA: true, finalizationBoundaryReached: true, runTokenMatches, inputHash: input.inputHash, inputHashMatches}}];`;
```

`validateProbeSafety` must prove the complete temporary node/connection set has
no external-call-capable or renderer node and return structural
`providerCalls: 0` and `rendererInvocations: 0`. The host combines those
structural metrics with the single final-boundary result and reports
`finalizationCount: 1`. Do not trust counters hardcoded by a Code stub.

Safety requirements:

- Fetch live WF09 by ID `gqX0rJ1gqzHCNDso`.
- Compare reused live nodes to current local WF09 definitions before creation.
- Permit only Webhook, Code, Crypto, and If node types.
- Reject credentials.
- Pin every Code node's exact `jsCode` with host-side SHA-256.
- Use 10-second Docker and HTTP timeouts.
- Deactivate/delete in `finally` and verify HTTP `404`.
- Aggregate primary and cleanup failures.
- Never include an HTTP Request or Execute Workflow node.

- [ ] **Step 4: Run source tests and syntax checks**

Run:

```powershell
$env:PYTHONPATH='.;clipcraft'; py -m pytest clipcraft/tests/test_workflow_integration.py -q -k "wf09_provider_free_probe"
node --check clipcraft/scripts/controlled_wf09_graph_no_provider_probe.js
```

Expected: pass.

Do not execute the runtime probe until the reviewed live WF09 is updated.

---

### Task 4: Back Up And Deploy Only WF09

**Files:**
- Reuse: `clipcraft/scripts/backup_stage_hashing_1o.js`
- Reuse: `clipcraft/scripts/import_stage_hashing_1o.js`
- Update report draft with backup/version evidence.

- [ ] **Step 1: Verify quiescent state**

Use Supabase SQL:

```sql
select
  count(*) filter (where status in ('queued','running','processing')) as active_jobs,
  count(*) filter (where lease_expires_at > now()) as active_leases
from public.video_jobs;
```

Use the n8n API to query `executions?status=running&limit=100`.

Expected: `active_jobs=0`, `active_leases=0`, `runningExecutions=0`. Stop if not.

- [ ] **Step 2: Run fresh local verification**

Run:

```powershell
$env:PYTHONPATH='.;clipcraft'; py -m pytest clipcraft/tests/test_workflow_integration.py -q
node --check clipcraft/scripts/controlled_wf09_graph_no_provider_probe.js
node --check clipcraft/scripts/backup_stage_hashing_1o.js
node --check clipcraft/scripts/import_stage_hashing_1o.js
```

Expected: all pass.

- [ ] **Step 3: Create a coherent live backup set**

Run from `clipcraft`:

```powershell
node scripts/backup_stage_hashing_1o.js
```

Expected: five same-timestamp backup paths and `{"backedUp":5}`. Record the
WF09 path. The importer requires exact backup/live equality.

- [ ] **Step 4: Import with no-op skipping**

Run:

```powershell
node scripts/import_stage_hashing_1o.js
```

Expected:

```text
WF05 skipped=true
WF06 skipped=true
WF07 skipped=true
WF08 skipped=true
WF09 skipped=false
```

Stop if any workflow other than WF09 mutates.

- [ ] **Step 5: Verify live scope**

Fetch live WF09 and prove:

```text
ID = gqX0rJ1gqzHCNDso
active = true
Workflow Trigger target = Normalize Stage Context
Build Response target = Finalize Stage
all non-approved nodes/connections/settings/staticData unchanged
```

---

### Task 5: Execute Provider-Free Gate A

**Files:**
- Execute: `clipcraft/scripts/controlled_wf09_graph_no_provider_probe.js`
- Create or update: `clipcraft/docs/superpowers/reports/2026-08-05-phase-7-checkpoint-1p-wf09-ledger-reconciliation.md`

- [ ] **Step 1: Run the provider-free runtime probe**

Run from `clipcraft`:

```powershell
node scripts/controlled_wf09_graph_no_provider_probe.js
```

Expected JSON:

```json
{
  "gateA": true,
  "runTokenMatches": true,
  "inputHashMatches": true,
  "finalizationCount": 1,
  "providerCalls": 0,
  "rendererInvocations": 0
}
```

- [ ] **Step 2: Verify cleanup and quiescence**

Verify temporary workflow lookup returns `404`. Re-run active job, active lease,
and running execution checks. Expected all zero.

- [ ] **Step 3: Complete the Gate A checklist**

Write explicit pass/fail evidence for every Gate A item from the design spec:

```text
graph repair verified
probe passed
stubbed STARTED accepted
finalization boundary reached once
runToken unchanged
inputHash unchanged
provider calls 0
renderer invocations 0
workflow drift none outside two edges
active jobs 0
active leases 0
running executions 0
```

- [ ] **Step 4: Enforce the hard stop**

If any item fails, finish the blocker report and stop. Do not create a migration
file, modify WF04, or call any migration tool.

Only a complete Gate A pass permits Task 6.

---

### Task 6: Add Failing Phase B Contract Tests

**Files:**
- Modify: `clipcraft/tests/test_foundation_contracts.py`
- Modify: `clipcraft/tests/test_workflow_integration.py`
- Create: `clipcraft/supabase/tests/begin_job_stage_contract_probe.sql`

- [ ] **Step 1: Add migration-discovery and contract assertions**

Add a helper that selects the one migration ending in
`_restore_begin_job_stage_contract.sql`, then assert its function body contains:

```python
for fragment in (
    "invalid_item_key",
    "input_hash_mismatch",
    "stage_row.status = 'succeeded'",
    "'cached_success'",
    "stage_row.status = 'unknown_outcome'",
    "'unknown_outcome'",
    "stage_row.status = 'running'",
    "'running'",
    "stage_row.status = 'failed'",
    "'_retryable'",
    "worker_id=p_worker_id",
    "lease_token=p_lease_token",
    "job_attempt_number=p_attempt_number",
):
    assert fragment in sql
```

Also assert the signature remains:

```text
(uuid, integer, text, text, text, text, uuid, integer) -> jsonb
```

- [ ] **Step 2: Add WF04 cached-success token tests**

Execute or inspect `Merge Stage Context` so tests require:

```text
CACHED_SUCCESS + null run_token -> accepted and routed cached
STARTED + null run_token -> RUN_TOKEN_REQUIRED
STARTED + valid UUID run_token -> accepted
```

The existing test-only Code execution helper may be extended to inject a
mocked `$()` node lookup map.

- [ ] **Step 3: Create the SQL probe file**

The file must start with `begin;`, use generated UUIDs inside one PL/pgSQL `do`
block, test all eight cases, and end with `rollback;`. It must contain no fixed
production job ID.

Use this structure:

```sql
begin;
do $$
declare
  probe_job_id uuid := gen_random_uuid();
  probe_lease uuid := gen_random_uuid();
  first_result jsonb;
  second_result jsonb;
  first_token uuid;
begin
  insert into public.video_jobs(
    id, topic, status, current_step, claimed_by, lease_token,
    lease_expires_at, attempt_number, pipeline_revision
  ) values (
    probe_job_id, 'phase-7-ledger-contract-probe', 'processing', 'probe',
    'phase-7-probe', probe_lease, now() + interval '5 minutes', 1, 1
  );

  first_result := public.begin_job_stage(
    probe_job_id, 1, 'probe_first', 'job', repeat('a', 64),
    'phase-7-probe', probe_lease, 1
  );
  assert first_result->>'state' = 'STARTED', 'first insert must START';
  first_token := (first_result->>'run_token')::uuid;

  second_result := public.begin_job_stage(
    probe_job_id, 1, 'probe_first', 'job', repeat('a', 64),
    'phase-7-probe', probe_lease, 1
  );
  assert second_result->>'state' = 'RUNNING', 'running duplicate must not restart';
  assert (second_result->>'run_token')::uuid = first_token, 'running token changed';

  begin
    perform public.begin_job_stage(
      probe_job_id, 1, 'probe_first', 'job', repeat('b', 64),
      'phase-7-probe', probe_lease, 1
    );
    raise exception 'EXPECTED_INPUT_HASH_MISMATCH';
  exception when others then
    assert sqlerrm = 'INPUT_HASH_MISMATCH', 'different hash was not rejected';
  end;

  insert into public.job_stage_runs(
    job_id,pipeline_revision,stage,item_key,input_hash,status,run_token,
    job_attempt_number,worker_id,lease_token,output_json
  ) values (
    probe_job_id,1,'probe_succeeded','job',repeat('c',64),'succeeded',
    gen_random_uuid(),1,'phase-7-probe',probe_lease,'{"cached":true}'::jsonb
  );
  second_result := public.begin_job_stage(
    probe_job_id,1,'probe_succeeded','job',repeat('c',64),
    'phase-7-probe',probe_lease,1
  );
  assert second_result->>'state' = 'CACHED_SUCCESS', 'succeeded row did not cache';
  assert second_result->'output' = '{"cached":true}'::jsonb, 'cached output changed';

  insert into public.job_stage_runs(
    job_id,pipeline_revision,stage,item_key,input_hash,status,run_token,
    job_attempt_number,worker_id,lease_token
  ) values (
    probe_job_id,1,'probe_unknown','job',repeat('d',64),'unknown_outcome',
    gen_random_uuid(),1,'phase-7-probe',probe_lease
  );
  second_result := public.begin_job_stage(
    probe_job_id,1,'probe_unknown','job',repeat('d',64),
    'phase-7-probe',probe_lease,1
  );
  assert second_result->>'state' = 'UNKNOWN_OUTCOME', 'unknown outcome restarted';

  insert into public.job_stage_runs(
    job_id,pipeline_revision,stage,item_key,input_hash,status,run_token,
    job_attempt_number,worker_id,lease_token,error_json
  ) values (
    probe_job_id,1,'probe_failed','job',repeat('e',64),'failed',
    gen_random_uuid(),1,'phase-7-probe',probe_lease,'{"_retryable":false}'::jsonb
  );
  second_result := public.begin_job_stage(
    probe_job_id,1,'probe_failed','job',repeat('e',64),
    'phase-7-probe',probe_lease,1
  );
  assert second_result->>'state' = 'FAILED', 'terminal failure restarted';

  insert into public.job_stage_runs(
    job_id,pipeline_revision,stage,item_key,input_hash,status,run_token,
    job_attempt_number,worker_id,lease_token,error_json
  ) values (
    probe_job_id,1,'probe_retry','job',repeat('f',64),'failed',
    gen_random_uuid(),0,'old-worker',gen_random_uuid(),'{"_retryable":true}'::jsonb
  );
  second_result := public.begin_job_stage(
    probe_job_id,1,'probe_retry','job',repeat('f',64),
    'phase-7-probe',probe_lease,1
  );
  assert second_result->>'state' = 'STARTED', 'retryable failure did not restart';
  select * into retry_row from public.job_stage_runs
  where job_id=probe_job_id and pipeline_revision=1 and stage='probe_retry' and item_key='job';
  assert retry_row.worker_id = 'phase-7-probe', 'retry worker ownership stale';
  assert retry_row.lease_token = probe_lease, 'retry lease ownership stale';
  assert retry_row.job_attempt_number = 1, 'retry attempt ownership stale';
  assert retry_row.error_json is null, 'retry error was not cleared';

  begin
    perform public.begin_job_stage(
      probe_job_id,1,'probe_blank','   ',repeat('0',64),
      'phase-7-probe',probe_lease,1
    );
    raise exception 'EXPECTED_INVALID_ITEM_KEY';
  exception when others then
    assert sqlerrm = 'INVALID_ITEM_KEY', 'blank item key was not rejected';
  end;
end $$;
rollback;
```

Add `retry_row public.job_stage_runs;` to the declaration block shown above.

- [ ] **Step 4: Run Phase B tests and verify RED**

Run:

```powershell
$env:PYTHONPATH='.;clipcraft'; py -m pytest clipcraft/tests/test_foundation_contracts.py clipcraft/tests/test_workflow_integration.py -q -k "begin_job_stage or cached_success"
```

Expected: fail because the migration is absent and WF04 rejects cached success
without a token.

---

### Task 7: Create The Additive Migration

**Files:**
- Create via CLI: exactly one file matching `clipcraft/supabase/migrations/*_restore_begin_job_stage_contract.sql`
- Test: `clipcraft/tests/test_foundation_contracts.py`

- [ ] **Step 1: Discover the installed CLI interface**

Run from `clipcraft`:

```powershell
supabase --help
supabase migration --help
supabase migration new --help
```

If the CLI is unavailable, stop and report the missing dependency. Do not invent
a migration filename and do not apply remote DDL without the repository file.

- [ ] **Step 2: Generate the migration file**

Run:

```powershell
supabase migration new restore_begin_job_stage_contract
```

Use the exact path printed by the CLI for all following steps.

- [ ] **Step 3: Write the complete function replacement**

The migration must contain one `create or replace function
public.begin_job_stage(...) returns jsonb` with `language plpgsql security
definer set search_path = ''` and this decision order:

```plpgsql
if p_item_key is null or length(trim(p_item_key)) = 0 then
  raise exception 'INVALID_ITEM_KEY';
end if;

select * into job_row from public.video_jobs where id = p_job_id for update;
if not found
   or job_row.claimed_by <> p_worker_id
   or job_row.lease_token <> p_lease_token
   or job_row.attempt_number <> p_attempt_number
   or job_row.pipeline_revision <> p_pipeline_revision
   or job_row.lease_expires_at <= now()
   or job_row.status in ('completed','failed','cancelled') then
  raise exception 'LEASE_LOST';
end if;

select * into stage_row
from public.job_stage_runs
where job_id = p_job_id
  and pipeline_revision = p_pipeline_revision
  and stage = p_stage
  and item_key = p_item_key
for update;

if found then
  if stage_row.input_hash <> p_input_hash then
    raise exception 'INPUT_HASH_MISMATCH';
  end if;
  if stage_row.status = 'succeeded' then
    return jsonb_build_object('state','CACHED_SUCCESS','stage_run_id',stage_row.id,'output',stage_row.output_json);
  end if;
  if stage_row.status = 'unknown_outcome' then
    return jsonb_build_object('state','UNKNOWN_OUTCOME','stage_run_id',stage_row.id);
  end if;
  if stage_row.status = 'running' then
    return jsonb_build_object('state','RUNNING','stage_run_id',stage_row.id,'run_token',stage_row.run_token);
  end if;
  if stage_row.status = 'failed'
     and coalesce(stage_row.error_json->>'_retryable','false') <> 'true' then
    return jsonb_build_object('state','FAILED','stage_run_id',stage_row.id,'output',stage_row.error_json);
  end if;

  update public.job_stage_runs
  set status='running',
      run_token=pg_catalog.gen_random_uuid(),
      worker_id=p_worker_id,
      lease_token=p_lease_token,
      job_attempt_number=p_attempt_number,
      heartbeat_at=now(),
      error_json=null
  where id=stage_row.id
  returning * into stage_row;
else
  insert into public.job_stage_runs(
    job_id,pipeline_revision,stage,item_key,input_hash,status,run_token,
    job_attempt_number,worker_id,lease_token,started_at,heartbeat_at
  ) values (
    p_job_id,p_pipeline_revision,p_stage,p_item_key,p_input_hash,'running',
    pg_catalog.gen_random_uuid(),p_attempt_number,p_worker_id,p_lease_token,now(),now()
  ) returning * into stage_row;
end if;

return jsonb_build_object('state','STARTED','stage_run_id',stage_row.id,'run_token',stage_row.run_token);
```

Do not add tables, columns, policies, extensions, effective-input hashing, or
other function changes.

- [ ] **Step 4: Run static migration tests**

Run:

```powershell
$env:PYTHONPATH='.;clipcraft'; py -m pytest clipcraft/tests/test_foundation_contracts.py -q -k "begin_job_stage"
```

Expected: migration contract tests pass.

---

### Task 8: Reconcile WF04 Cached-Success Token Handling

**Files:**
- Modify: `clipcraft/workflows/04-generate-script-and-scenes.json`
- Test: `clipcraft/tests/test_workflow_integration.py`

- [ ] **Step 1: Implement state-aware token validation**

In top-level `Merge Stage Context`, replace unconditional token validation with:

```javascript
const {stageHashInput, ...context} = $('Hash Stage Input').first().json;
const result = $json;
const state = result.state;
const runToken = result.run_token;
if (state === 'STARTED' && (typeof runToken !== 'string' || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(runToken))) {
  throw new Error('RUN_TOKEN_REQUIRED');
}
return [{json: {...context, stageState: state, stageRunId: result.stage_run_id, runToken: runToken ?? null, cachedOutput: result.output}}];
```

Do not change provider paths or any other WF04 node.

- [ ] **Step 2: Run focused RED-to-GREEN tests**

Run:

```powershell
$env:PYTHONPATH='.;clipcraft'; py -m pytest clipcraft/tests/test_workflow_integration.py -q -k "cached_success or run_token"
```

Expected: all cached/start token tests pass.

- [ ] **Step 3: Back up and deploy only WF04 after Gate A remains true**

Before deployment, re-run Gate A state checks. Use the existing targeted WF04
backup/import scripts only after updating their post-import node-count
expectation if necessary. Preserve ID `dWTF2UGXX3R73PDW`, active state, settings,
and static data. Run the WF04 provider-free probe afterward.

If Gate A no longer passes, stop before migration application.

---

### Task 9: Apply And Verify The Ledger Migration

**Files:**
- Apply: CLI-generated `restore_begin_job_stage_contract.sql`
- Execute: `clipcraft/supabase/tests/begin_job_stage_contract_probe.sql`
- Update report.

- [ ] **Step 1: Reconfirm Gate A and migration preflight**

Required fresh evidence:

```text
active jobs 0
active leases 0
running executions 0
WF09 provider-free probe pass
WF04 provider-free probe pass
repository/live WF04 and WF09 equality pass
```

Use Supabase tools to list tables and migrations again. Stop on drift.

- [ ] **Step 2: Apply exactly one migration**

Read the CLI-generated migration file and call the Supabase migration tool with:

```text
name: restore_begin_job_stage_contract
query: exact migration file contents
```

Do not call raw SQL for DDL and do not edit the applied migration afterward.

- [ ] **Step 3: Execute the transaction-rolled-back SQL probe**

Read `clipcraft/supabase/tests/begin_job_stage_contract_probe.sql` and execute it
through the SQL tool. Expected: no assertion error and no persisted probe row
because the file ends with `rollback;`.

- [ ] **Step 4: Verify no probe data persisted**

Run:

```sql
select count(*) as probe_jobs
from public.video_jobs
where topic = 'phase-7-ledger-contract-probe';
```

Expected: `0`.

- [ ] **Step 5: Run Supabase advisors**

Run security and performance advisors. Record new findings separately from
pre-existing findings and include remediation links in the report. A new
security finding caused by this migration is a blocker.

- [ ] **Step 6: Verify migration history**

List migrations and confirm exactly one new
`restore_begin_job_stage_contract` entry.

---

### Task 10: Final Regression And Provider-Free Gates

**Files:**
- Test repository and live workflows.
- Update report.

- [ ] **Step 1: Run full ClipCraft tests**

```powershell
$env:PYTHONPATH='.;clipcraft'; py -m pytest clipcraft/tests -q
```

Expected: all pass.

- [ ] **Step 2: Run custom node tests**

```powershell
npm test
```

Working directory:
`clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft`

Expected: `29` tests pass.

- [ ] **Step 3: Run backend tests**

```powershell
py -m pytest -q
```

Working directory: `backend`.

Expected: no new failure. The known missing
`009_video_job_configuration_snapshots.sql` failure must be reported exactly if
still present; do not fix it in this scope.

- [ ] **Step 4: Run both provider-free probes**

```powershell
node scripts/controlled_wf04_run_token_no_provider_probe.js
node scripts/controlled_wf09_graph_no_provider_probe.js
```

Working directory: `clipcraft`.

Expected: both pass, provider calls `0`, renderer invocations `0`, temporary
workflows deleted.

- [ ] **Step 5: Re-run SQL contract probe and state checks**

Expected:

```text
SQL probe pass
probe rows 0
active jobs 0
active leases 0
running executions 0
```

- [ ] **Step 6: Final code review**

Request a final review covering exactly:

- Two-edge WF09 scope.
- Gate A evidence.
- Additive single-function migration.
- WF04 cached-state token handling.
- No effective-input hash redesign.
- No unrelated workflow or schema drift.

Fix Critical/Important findings before production.

---

### Task 11: Create At Most One Controlled Production Job

**Files:**
- Create: `clipcraft/scripts/controlled_single_production_generation.js`
- Update: checkpoint report.

- [ ] **Step 1: Add a one-shot runner safety contract test**

The script source test must require:

```text
preflight active jobs = 0
preflight active leases = 0
preflight running executions = 0
exactly one POST to /webhook/videos/create
no retry loop
fixed 30-second, 6-scene brief
terminal-state polling with finite timeout
first-blocker stop
no second create call
```

- [ ] **Step 2: Create the runner**

Use this exact creation payload:

```json
{
  "channelId": "default",
  "brief": {
    "topic": "How bees help plants grow",
    "duration": 30,
    "sceneCount": 6,
    "language": "English",
    "contentStyle": "educational",
    "visualStyle": "cinematic nature documentary",
    "voiceTone": "warm and clear",
    "captionStyle": "bold highlighted words"
  }
}
```

The runner must call `http://localhost:5680/webhook/videos/create` once, capture
the returned `jobId`, and poll read-only job/execution state with bounded waits.
It must never issue a second create request, retry the job, clear a lease,
delete a job, or mutate a failed job.

- [ ] **Step 3: Run final preflight**

All Task 10 gates must still pass immediately before creation. Stop if any
active job, lease, execution, workflow drift, migration drift, or advisor blocker
exists.

- [ ] **Step 4: Execute once**

Run:

```powershell
node scripts/controlled_single_production_generation.js
```

Stop at the first new blocker. Do not run the script again.

- [ ] **Step 5: Complete the report**

Record:

- Job ID and n8n execution IDs.
- Stage transitions and final status.
- Provider/renderer invocation counts.
- Lease and run-token state without recording token values.
- Output artifact metadata without binary/base64 content.
- Exact blocker if incomplete.
- Final active job/lease/execution counts.
- Confirmation that no second job was created.

Do not claim production success unless the job reaches `completed` and all
artifact/status checks pass.

---

## Stop Rules

Stop immediately and write the report when any of these occurs:

- Gate A condition fails.
- A workflow other than WF09 changes during Phase A.
- Renderer/provider invocation occurs during a provider-free probe.
- Migration scope expands beyond `begin_job_stage`.
- SQL probe persists fixture data.
- A new Supabase security issue is introduced.
- A provider, renderer, or workflow blocker appears during the single production
  job.
- Continuing would require a second production job.
- An unrelated architectural change is required.

Never retry the production creation step in this plan.
