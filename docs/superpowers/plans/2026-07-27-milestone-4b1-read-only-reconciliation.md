# Milestone 4B.1 Read-Only Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate and offline-validate five truthful Milestone 4B.1 reconciliation artifacts using only fresh documented n8n API GET evidence.

**Architecture:** A standalone validator encodes the output contract and runs without credentials or network access. A standalone generator loads the canonical repository workflows and three authoritative 4A.1 inputs, captures complete preflight and postflight runtime snapshots through GET requests, derives parity/audit/candidate evidence in memory, and writes exactly five deterministic JSON document types.

**Tech Stack:** Python standard library (`json`, `hashlib`, `urllib.request`, `pathlib`, `datetime`, `re`, `os`)

---

### Task 1: Offline Structural Validator

**Files:**
- Create: `milestone4b1_validate.py`

- [ ] **Step 1: Define the five-artifact contract**

Define exact artifact names and assertions for JSON parsing, 18 canonical rows, action counts `10/7/1`, blocked publication counts, untouched WF16 candidates, exhaustive reference evidence, pre/post snapshot equality, operation counters, absence of placeholders, and preserved `DO_NOT_BEGIN` gate.

```python
ARTIFACT_NAMES = (
    "runtime-summary", "runtime-parity", "publication-report",
    "reference-validation", "report",
)
EXPECTED_ACTION_COUNTS = {
    "PUBLISH_REPOSITORY": 10,
    "KEEP_RUNTIME": 7,
    "MANUAL_REVIEW": 1,
}
```

- [ ] **Step 2: Run the validator before artifacts exist**

Run: `python milestone4b1_validate.py`

Expected: nonzero exit caused by a missing `artifacts/milestone-4b1-*.json` file, proving the requested artifacts do not yet satisfy the contract.

### Task 2: Read-Only Reconciliation Generator

**Files:**
- Create: `milestone4b1_reconcile.py`

- [ ] **Step 1: Implement a GET-only API boundary**

Use one request helper with no caller-selectable method. Paginate `/api/v1/workflows`, then GET every `/api/v1/workflows/{id}` definition for each snapshot.

```python
def api_get(path, query=None):
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "X-N8N-API-KEY": API_KEY},
        method="GET",
    )
```

- [ ] **Step 2: Build fresh snapshot evidence**

Capture preflight and postflight timestamps, workflow count, identity hash, summary digest, and full-definition digest. Compare ID sets, active states, and canonicalized full definitions exactly.

```python
unchanged = {
    "workflowIdsUnchanged": set(pre) == set(post),
    "activeStatesUnchanged": active_map(pre) == active_map(post),
    "fullDefinitionsUnchanged": digest(pre) == digest(post),
}
```

- [ ] **Step 3: Recompute canonical parity and approved outcomes**

For each of the 18 authoritative reconciliation rows, reload its current repository JSON, resolve the approved runtime IDs against the fresh preflight snapshot, compare all repository source fields except server-managed identity/revision and activation fields, and emit runtime identity/state, parity mismatches, approved state, gate evidence, result, and `mutationAttempted: false`.

- [ ] **Step 4: Audit every stored Execute Workflow node**

Inspect every workflow definition from the paginated snapshot. Resolve string/object workflow IDs, report caller and target identity/state/classification, missing targets, canonical targets, duplicate target names, copy/test/experimental flags, and compute directed cycles. Separately prove the four canonical repository references still target IDs `17` or `18`; a contradiction sets a stop condition without repair.

- [ ] **Step 5: Derive duplicate and orphan candidates**

Report exact canonical-name duplicates, active names whose `(COPY)`-normalized name is canonical, behavior-fingerprint groups, and workflows without incoming stored edges. Model canonical webhook, schedule, manual, queue, and utility entrypoint status so no canonical workflow is declared orphaned solely due to absent stored incoming edges. Treat all noncanonical findings as unresolved candidates.

- [ ] **Step 6: Write exactly five artifacts**

Write runtime summary, runtime parity, publication report, reference validation, and final report. The final status is `BLOCKED_BY_APPROVED_GATES`; success criteria identify ten forbidden publications and unresolved WF16/duplicate/orphan candidates. Include an operation audit with GET as the only allowed/observed method and every attempt counter equal to zero.

### Task 3: Safe Verification

**Files:**
- Verify: `milestone4b1_reconcile.py`
- Verify: `milestone4b1_validate.py`
- Verify: `artifacts/milestone-4b1-*.json`

- [ ] **Step 1: Compile both scripts**

Run: `python -m py_compile milestone4b1_validate.py milestone4b1_reconcile.py`

Expected: exit code 0 and no output.

- [ ] **Step 2: Run the generator**

Run: `python milestone4b1_reconcile.py`

Expected: JSON summary naming five written artifacts, GET-only operation counts, unchanged pre/post state, and truthful blocked status.

- [ ] **Step 3: Run offline validation**

Run: `python milestone4b1_validate.py`

Expected: JSON summary confirming five parsed artifacts, 18 workflows, action counts `10/7/1`, ten blocked and zero attempted publications, unchanged definitions/activation, and `DO_NOT_BEGIN`.

No commits are performed because the workspace is not a Git repository and the user prohibited commits.
