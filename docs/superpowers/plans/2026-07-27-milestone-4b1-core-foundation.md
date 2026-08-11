# Milestone 4B.1 Core Backend Architecture Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the approved repository-side lease, stage-ledger, idempotency, retry-boundary, regeneration-routing, and POSIX asset-identity foundations without publishing, activating, or executing workflows.

**Architecture:** Add one additive PostgreSQL migration containing fenced lease state, revisioned stage runs, regeneration operations, logical asset identity columns, and ownership-checked RPCs. Keep existing workflow JSON and WF17/WF18 contracts unchanged because publication and runtime activation are explicitly out of scope. Add a portable Python path layer that emits relative POSIX asset keys and derives container/native paths only at boundaries.

**Tech Stack:** PostgreSQL/Supabase SQL migrations, PL/pgSQL, Python 3, pytest.

---

### Task 1: Establish Failing Foundation Contract Tests

**Files:**
- Create: `clipcraft/tests/test_foundation_contracts.py`
- Test: `clipcraft/tests/test_foundation_contracts.py`

- [ ] **Step 1: Write failing assertions for migration objects and path API.**

Assert that migration `004_core_backend_foundation.sql` exists and contains the approved tables, columns, constraints, RPC names, ownership predicates, retry boundaries, regeneration modes, and canonical path identifiers. Assert the new path functions exist and reject traversal/coercion cases.

- [ ] **Step 2: Run the targeted test and verify it fails because the foundation is absent.**

Run: `py -3 -m pytest clipcraft/tests/test_foundation_contracts.py -q`

Expected: FAIL because the migration and new path API do not exist yet.

### Task 2: Implement Lease, Ledger, Revision, and Regeneration Schema

**Files:**
- Create: `clipcraft/supabase/migrations/004_core_backend_foundation.sql`
- Modify: `clipcraft/supabase/migrations/verify-migrations.sql`

- [ ] **Step 1: Add additive lease fields and constraints to `video_jobs`.**

Add `lease_token`, `lease_expires_at`, `heartbeat_at`, `attempt_number`, `max_job_attempts`, `available_at`, `pipeline_revision`, `current_revision`, `next_stage`, `last_completed_stage`, `failure_class`, and `cancel_requested`. Preserve existing rows with defaults and explicitly migrate `max_retries` semantics to total lease attempts without deleting legacy columns.

- [ ] **Step 2: Add revision-aware scene and logical asset fields.**

Add `scenes.pipeline_revision`; replace the old `(job_id, scene_index)` uniqueness constraint with `(job_id, pipeline_revision, scene_index)`. Add `assets.pipeline_revision`, `logical_key`, `stage_run_id`, `content_sha256`, `committed_at`, and a partial unique index for `(job_id, pipeline_revision, logical_key)`.

- [ ] **Step 3: Add `job_stage_runs` and `regeneration_operations`.**

Use `item_key text not null`, statuses `pending/running/unknown_outcome/succeeded/failed/abandoned`, immutable `input_hash`, ownership fields, side-effect phase, durable attempt counters, output/error JSON, and timestamps. Add operation statuses and explicit modes `SCENE_VISUAL`, `ALL_IMAGES`, `SCRIPT_CREATIVE`, `VIDEO_RENDER_ONLY`, `VIDEO_FULL_CREATIVE`.

- [ ] **Step 4: Add indexes, checks, comments, and restricted function defaults.**

Index queue availability, lease expiry, stage lookup, and operation lookup. Revoke default function execution from public/anonymous/authenticated roles for new internal RPCs; grant only the existing server execution role required by the repository contract.

- [ ] **Step 5: Extend `verify-migrations.sql` with foundation checks.**

Check foundation columns/tables/functions, uniqueness indexes, supported operation modes, and lease/stage status constraints without executing production mutations.

### Task 3: Implement Fenced Lease and Stage Lifecycle RPCs

**Files:**
- Modify: `clipcraft/supabase/migrations/004_core_backend_foundation.sql`
- Test: `clipcraft/tests/test_foundation_contracts.py`

- [ ] **Step 1: Add atomic claim, heartbeat, release, cancellation, reclaim, and reaper RPCs.**

Use database `now()`, `FOR UPDATE SKIP LOCKED`, fresh UUID lease tokens, full ownership predicates including pipeline revision, and typed conflict exceptions. Ensure stale workers cannot heartbeat or finalize after expiry/reclaim.

- [ ] **Step 2: Add stage begin/reserve/finalize/fail RPCs.**

Make `(job_id, pipeline_revision, stage, item_key)` authoritative. Return cached success for matching completed work, reject input hash changes, reserve external attempts before calls, and finalize outputs/checkpoints only with the current lease/run token.

- [ ] **Step 3: Add regeneration enqueue RPC.**

Atomically authorize operation mode, allocate the next revision, invalidate only the approved artifacts, create the operation, and return existing operation state for a duplicate client request.

- [ ] **Step 4: Run contract tests and inspect SQL statically.**

Run: `py -3 -m pytest clipcraft/tests/test_foundation_contracts.py -q`

Expected: PASS for migration/RPC contract assertions.

### Task 4: Implement Canonical POSIX Asset Identity

**Files:**
- Modify: `clipcraft/video-tools/asset_paths.py`
- Modify: `clipcraft/tests/test_asset_paths.py`
- Modify: `clipcraft/supabase/migrations/004_core_backend_foundation.sql`

- [ ] **Step 1: Add `get_asset_key`, `get_container_path`, and `get_filesystem_path`.**

Canonicalize UUIDs to lowercase, enforce strict integer scene indexes, construct relative POSIX keys with `PurePosixPath`, derive `/data/jobs/...` container paths separately, and use resolved containment for native filesystem paths.

- [ ] **Step 2: Preserve `get_asset_path` compatibility.**

Keep returning the POSIX container path expected by existing workflow contracts while adding `asset_key` and `container_path` fields. Do not change workflow JSON or WF16 runtime behavior in this milestone.

- [ ] **Step 3: Add cross-platform/path-security tests and run them.**

Cover Windows separators, uppercase UUIDs, strict scene types, boundary indexes, traversal, drive/UNC paths, and asset-key round trips.

### Task 5: Generate Foundation Validation Artifacts

**Files:**
- Create: `milestone4b1_foundation_validate.py`
- Create: `artifacts/milestone-4b1-foundation-report.json`
- Create: `artifacts/milestone-4b1-lease-validation.json`
- Create: `artifacts/milestone-4b1-stage-ledger.json`
- Create: `artifacts/milestone-4b1-idempotency-validation.json`
- Create: `artifacts/milestone-4b1-retry-validation.json`
- Create: `artifacts/milestone-4b1-regeneration-validation.json`
- Create: `artifacts/milestone-4b1-path-validation.json`

- [ ] **Step 1: Add repository-only validation report generation.**

Parse migration and source modules, run only scoped tests, record no provider/renderer/TTS/Supabase runtime access, and report implementation status, checks, failures, and publication eligibility.

- [ ] **Step 2: Run scoped verification.**

Run: `py -3 -m py_compile milestone4b1_foundation_validate.py clipcraft/video-tools/asset_paths.py`

Run: `py -3 -m pytest clipcraft/tests/test_foundation_contracts.py clipcraft/tests/test_asset_paths.py -q`

Run: `py -3 milestone4b1_foundation_validate.py`

Expected: reports generated; no workflow/provider/runtime operation performed.

- [ ] **Step 3: Confirm publication eligibility remains gated.**

The final report must state that lease/ledger/path foundations are implemented, but previously blocked `PUBLISH_REPOSITORY` actions are not eligible until workflow source integration, authentication, parity publication, and activation gates are separately completed.
