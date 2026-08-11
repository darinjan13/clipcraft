# Milestone 4B.1 Evidence Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the read-only Milestone 4B.1 reconciler so transport, pagination, live-reference, operation-audit, retained-evidence, and artifact-generation claims are independently verifiable and fail closed.

**Architecture:** Keep two self-contained scripts. The validator first defines the new generation-envelope, retained-definition, sampled-read, operation-record, and live-reference contracts. The generator then validates configuration before requests, disables redirects, records successful GETs only, retains normalized pre/post definitions, builds all five documents under one generation identity, and atomically replaces the artifact set only after all temporary files are durable.

**Tech Stack:** Python standard library (`argparse`, `hashlib`, `ipaddress`, `json`, `os`, `tempfile`, `urllib`, `uuid`, `pathlib`)

---

### Task 1: Expand Offline Contract First

**Files:**
- Modify: `milestone4b1_validate.py`

- [ ] Add `--expected-generation-id`, UUID/hex validation, common evidence digest checks, recomputation of retained definition digests and parity runtime hashes, successful-operation record validation, sampled pagination claims, live canonical reference evidence checks, and secret/base-URL marker scans.
- [ ] Run `py milestone4b1_validate.py` and verify RED because current artifacts lack the generation envelope and retained evidence.

### Task 2: Harden Transport and Pagination

**Files:**
- Modify: `milestone4b1_reconcile.py`

- [ ] Replace import-time environment reads with validated configuration: no userinfo/query/fragment, HTTPS except loopback HTTP, nonempty API key, and a redirect handler that rejects every redirect.
- [ ] Record a request only after a 2xx JSON response validates, including path, encoded nonsecret query, status, origin identity hash, and `completed=true`.
- [ ] Validate listing/detail schemas, detect repeated cursors and duplicate workflow IDs, require detail IDs to match requested IDs, and preserve reconstructable traversal request records.
- [ ] Catch configuration, transport, HTTP, JSON/schema, pagination, and output failures; print a sanitized error that states existing artifacts remain last-valid and return nonzero.

### Task 3: Retain Live Evidence and Scope Claims

**Files:**
- Modify: `milestone4b1_reconcile.py`

- [ ] Retain canonical normalized preflight and postflight workflow-definition maps in runtime summary and derive all hashes from those exact maps without base URL or secrets.
- [ ] Compare the four approved references against corresponding live canonical caller definitions and report exact missing/unexpected/mismatched live reference evidence.
- [ ] Rename pre/post claims to sampled equality terms and state sequential-read limitations explicitly.
- [ ] Derive operation counts and prohibited-path findings from successful request records and scope all claims to this program invocation.

### Task 4: Atomic Five-Artifact Generation

**Files:**
- Modify: `milestone4b1_reconcile.py`

- [ ] Assign one UUID generation ID and one common evidence digest to all documents.
- [ ] Serialize all documents in memory, scan bytes for API key and base URL, write and fsync five sibling temporary files, then `os.replace` four evidence files and the report last.
- [ ] On pre-replacement failure remove only new temporary files; never remove or truncate last-valid artifacts.

### Task 5: Safe Verification

**Files:**
- Verify: `milestone4b1_reconcile.py`
- Verify: `milestone4b1_validate.py`
- Regenerate: `artifacts/milestone-4b1-*.json`

- [ ] Run `py -m py_compile milestone4b1_validate.py milestone4b1_reconcile.py` and require exit 0.
- [ ] Run `py milestone4b1_reconcile.py`, capture its printed generation ID, and require 35 sampled workflows, GET-only completed operations, and unchanged sampled pre/post evidence.
- [ ] Run `py milestone4b1_validate.py --expected-generation-id <captured-id>` and require `PASS`.

No broad test command, runtime mutation, execution, publication, activation, external provider, or non-n8n service is used. No commit is performed because this workspace is not a Git repository.
