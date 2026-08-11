# Render Status Activity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Preview page's generic render state with a factual pipeline timeline and durable, sanitized activity history while keeping `video_jobs` canonical.

**Architecture:** A Supabase migration adds append-only `video_job_events`, transition logging, and an idempotent generic failure RPC. FastAPI reads the canonical job plus scene, asset, and event facts and returns one backward-compatible status response. The existing Preview route polls that response and renders a responsive timeline without changing generation logic in WF04, WF06, WF07, WF08, or WF09.

**Tech Stack:** PostgreSQL/Supabase, n8n workflow JSON, FastAPI/Pydantic/httpx, pytest, React 19, TypeScript, TanStack Query, Tailwind CSS, Vitest/Testing Library.

---

### Task 1: Lock the database and workflow contracts with failing tests

**Files:**
- Modify: `clipcraft/tests/test_foundation_contracts.py`
- Modify: `clipcraft/tests/test_workflow_integration.py`

- [ ] **Step 1: Add migration contract tests**

Assert that migration `005_video_job_events.sql` creates `video_job_events` with the approved columns, a `(job_id, created_at)` index, no mutable timestamp, safe metadata validation, and service-role-only writes. Assert that `persist_video_job_failure` locks the job, uses an idempotency key, ignores completed jobs, updates canonical failure fields, and appends one error event.

- [ ] **Step 2: Add workflow preservation and error-handler tests**

Snapshot the content-node parameters in WF04, WF06, WF07, WF08, and WF09. Assert WF14 accepts a generic context, calls `persist_video_job_failure`, and preserves the fenced `fail_job_stage` path when full lease context exists. Assert event logging failures are configured to continue rather than fail generation.

- [ ] **Step 3: Run focused tests and confirm RED**

Run:

```powershell
py -3 -m pytest clipcraft\tests\test_foundation_contracts.py clipcraft\tests\test_workflow_integration.py -q
```

Expected: failures for the missing migration, RPC, and generic WF14 path.

### Task 2: Add append-only events and generic failure persistence

**Files:**
- Create: `clipcraft/supabase/migrations/005_video_job_events.sql`
- Modify: `clipcraft/supabase/migrations/verify-migrations.sql`
- Modify: `clipcraft/supabase/run-migrations.sh`

- [ ] **Step 1: Create the event table**

Create `public.video_job_events` with `id`, `job_id`, `stage`, `event_type`, `level`, `message`, `progress`, `metadata jsonb`, and `created_at`. Add a nullable `idempotency_key` solely for duplicate suppression, a foreign key to `video_jobs`, checks for levels/progress/safe metadata shape, a unique partial index on `(job_id, idempotency_key)`, and an ordered `(job_id, created_at desc, id desc)` index.

- [ ] **Step 2: Enforce append-only behavior**

Revoke direct update/delete from browser roles and grant insert/select only where needed. Keep cascade deletion available for intentional job deletion; event rows never update canonical job state.

- [ ] **Step 3: Add safe event insertion**

Create a service-role RPC that validates allowed metadata keys and inserts with `ON CONFLICT DO NOTHING`. The approved keys are `attempt`, `maximum_attempts`, `actual_words`, `target_words`, `minimum_words`, `maximum_words`, `measured_duration`, `minimum_duration`, `maximum_duration`, `current`, `total`, `provider`, `workflow`, `execution_id`, `node`, and `http_status`.

- [ ] **Step 4: Add transition events**

Add an `AFTER INSERT OR UPDATE OF status, current_step, progress` trigger on `video_jobs`. It appends `job_created`, `stage_changed`, `job_completed`, or `job_failed` only when relevant canonical fields change. Trigger metadata remains empty and messages are fixed server-authored text.

- [ ] **Step 5: Add idempotent failure persistence**

Create `persist_video_job_failure(p_job_id, p_idempotency_key, p_stage, p_current_step, p_progress, p_error_code, p_user_message, p_metadata)`. Lock the job with `FOR UPDATE`; return unchanged for `completed`; return the existing result for a duplicate key; otherwise set `status='failed'`, preserve progress within `0..99`, write sanitized `error_message`, `last_error`, `failure_class`, `finished_at`, `updated_at`, clear lease ownership, and append one `level='error'`, `event_type='job_failed'` event.

- [ ] **Step 6: Register and verify the migration**

Add migration 005 to the runner and table/RPC/index checks to `verify-migrations.sql`.

- [ ] **Step 7: Run focused tests and confirm GREEN**

Run the Task 1 command. Expected: all migration contract tests pass.

### Task 3: Extend WF14 without changing generation content logic

**Files:**
- Modify: `clipcraft/workflows/14-error-handler.json`

- [ ] **Step 1: Normalize leased and legacy failure inputs**

Extract only `jobId`, stage, safe code/message, attempt fields, safe execution identifiers, and optional fenced fields. Reject missing/invalid job IDs and replace unknown technical text with `VIDEO_GENERATION_FAILED` plus `Video generation could not be completed.`

- [ ] **Step 2: Preserve fenced stage failure reporting**

When all lease/run fields exist, continue calling `heartbeat_video_job` and `fail_job_stage`. Configure these bookkeeping calls so their own errors do not prevent generic terminal persistence.

- [ ] **Step 3: Always invoke generic persistence**

Call `persist_video_job_failure` with a deterministic key based on job ID plus safe execution ID, or job/stage/attempt when no execution ID exists. Pass only allowlisted metadata. Return an idempotent accepted/ignored result.

- [ ] **Step 4: Run workflow tests**

Run:

```powershell
py -3 -m pytest clipcraft\tests\test_workflow_integration.py -q
```

Expected: WF14 tests and content-node preservation tests pass.

### Task 4: Specify the expanded status API with failing tests

**Files:**
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Expand test fakes**

Add fake methods for job status facts, scene counts, asset facts, recent events, and generic failure persistence without exposing raw database rows.

- [ ] **Step 2: Add response contract tests**

Cover raw canonical statuses, display labels, timestamps, elapsed seconds, 60-second stale threshold, image counts, five asset booleans, safe errors, recent event ordering, and compatibility defaults for legacy rows.

- [ ] **Step 3: Add security and terminal-state tests**

Verify metadata is projected through an allowlist, URLs/paths/tokens/stacks never appear, a stale event cannot override canonical completed status, completed/failed records are never marked stale, and unknown error codes use a generic readable message.

- [ ] **Step 4: Add failure endpoint tests**

Test an internal service-authenticated endpoint or database-client method that calls the generic RPC, is idempotent, and cannot overwrite completed jobs.

- [ ] **Step 5: Run backend tests and confirm RED**

Run:

```powershell
py -3 -m pytest tests\test_api.py -q
```

Working directory: `backend`. Expected: failures for missing models/client methods/status assembly.

### Task 5: Implement canonical status assembly and safe failure input

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/clients.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add additive response models**

Define `ImageProgress`, `AssetCompletion`, `SafeVideoError`, `VideoJobEvent`, and the expanded `VideoStatusResponse`. Keep existing camelCase aliases accepted where legacy clients depend on them, while returning the approved snake_case status contract.

- [ ] **Step 2: Add narrow database reads**

Select canonical status/error/timestamp fields from `video_jobs`; count current scene statuses; query only asset types; query the latest bounded events in deterministic order. Never select local paths, prompts, provider payloads, credentials, or raw error JSON for this response.

- [ ] **Step 3: Assemble status from database facts**

Use `video_jobs.status` unchanged as `status`; derive `display_status`; calculate elapsed from `created_at` to `updated_at` for terminal records and to now for active records; mark active records stale at 60 seconds; derive images and assets; project safe events. Do not infer canonical status from events.

- [ ] **Step 4: Sanitize errors**

Map known duration/word-count codes to bounded user messages and expected/received/attempt facts. Unknown codes receive a generic message. Drop unapproved metadata keys and strings containing URLs, filesystem paths, bearer/token/secret markers, environment assignments, or stack traces.

- [ ] **Step 5: Add generic failure persistence entry point**

Expose the smallest service-only backend path needed by legacy workflow contexts, delegating atomically to `persist_video_job_failure`. Authenticate it with the existing internal webhook/service convention; reject browser calls and malformed metadata.

- [ ] **Step 6: Run backend tests**

Run the Task 4 command. Expected: all backend API tests pass.

### Task 6: Reconcile the one confirmed failed job

**Files:**
- Create: `clipcraft/supabase/reconcile/2026-07-28-duration-validation-job.sql`

- [ ] **Step 1: Write a one-job guarded reconciliation**

Call `persist_video_job_failure` only for `6c9b8f51-620c-4805-9c86-aad17228b286`, with stage `generating_script`, code `NARRATION_WORD_COUNT_OUT_OF_RANGE_AFTER_REVISION`, message `The generated narration was still too short after two attempts.`, progress `5`, and safe metadata `{actual_words:48, minimum_words:89, maximum_words:105, target_words:97, attempt:2, maximum_attempts:2}`.

- [ ] **Step 2: Apply migration and reconciliation to the existing local Supabase instance**

Use the configured service connection. Do not insert, update, or delete any other `video_jobs` row.

- [ ] **Step 3: Query both validation records**

Confirm the failed job is terminal with exactly one idempotent error event and completed job `d794800c-8538-4314-bd0f-0aedf325a83c` remains completed.

### Task 7: Add frontend unit-test tooling and failing behavior tests

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/features/preview/pipeline.test.ts`
- Create: `frontend/src/features/preview/components/RenderStatus.test.tsx`

- [ ] **Step 1: Add Vitest and Testing Library**

Add `test: vitest run`, jsdom configuration, and jest-dom setup using the project package manager.

- [ ] **Step 2: Test pure pipeline behavior**

Cover fixed stage order, raw-stage mapping, 2-second visible polling, 15-second hidden polling, terminal stop, 60-second staleness, elapsed formatting, and legacy defaults.

- [ ] **Step 3: Test the panel**

Cover active image counts, completed presentation, the exact reconciled failure copy, collapsed/expanded activity events, asset facts, stale warning, mobile-safe wrapping classes, and absence of unsafe metadata.

- [ ] **Step 4: Run tests and confirm RED**

Run:

```powershell
npm test
```

Working directory: `frontend`. Expected: failures for missing pipeline types/helpers and new panel behavior.

### Task 8: Implement the expanded status client and timeline

**Files:**
- Modify: `frontend/src/features/videos/types.ts`
- Modify: `frontend/src/features/videos/api/videoService.ts`
- Create: `frontend/src/features/preview/pipeline.ts`
- Modify: `frontend/src/features/preview/pages/PreviewPage.tsx`
- Modify: `frontend/src/features/preview/components/RenderStatus.tsx`

- [ ] **Step 1: Add status contract types**

Model raw backend status as a string-compatible union, plus `display_status`, timestamps, image progress, asset facts, safe errors, and recent events. Keep the existing coarse `Video` type for Library/detail compatibility.

- [ ] **Step 2: Type `getVideoStatus`**

Return the expanded status response unchanged except for normal JSON validation/defaulting. Do not expose or translate internal paths.

- [ ] **Step 3: Add pure timeline helpers**

Define the six display stages and map canonical statuses to pending/active/completed/failed presentation. Use factual events/assets where present and explicit unavailable/legacy states rather than fabricated history.

- [ ] **Step 4: Split stable detail and status polling**

Keep `getVideo` for title/media. Add `videoKeys.status(videoId)` polling every 2 seconds while visible and active, every 15 seconds while hidden and active, and never for completed/failed. Refetch immediately on visibility return and refresh detail once when status becomes completed.

- [ ] **Step 5: Replace only `RenderStatus` internals**

Render overall exact progress, elapsed/last update, stale warning, vertical stage rail, image count, asset completion facts, native collapsed `<details>` activity, completed state, and sanitized failure state. Preserve the surrounding Preview layout and existing visual language.

- [ ] **Step 6: Run frontend tests and build**

Run:

```powershell
npm test
npm run build
```

Expected: tests pass and TypeScript/Vite production build succeeds.

### Task 9: End-to-end verification and requirement review

**Files:**
- Modify only if verification identifies a defect in files already listed.

- [ ] **Step 1: Run all automated suites**

```powershell
py -3 -m pytest -q
```

Working directory: `backend`.

```powershell
py -3 -m pytest clipcraft\tests -q
```

Working directory: repository root.

```powershell
npm test
npm run build
```

Working directory: `frontend`.

- [ ] **Step 2: Verify existing API records**

Call `GET /api/videos/{id}/status` for the completed and failed IDs. Confirm canonical terminal states, factual assets/images, durable events, readable error metadata, terminal polling eligibility, and no secrets/internal URLs.

- [ ] **Step 3: Verify controlled active fixtures**

Use mocked API responses only; do not create a generation job. Verify visible/hidden/terminal polling and responsive timeline behavior at narrow and desktop widths through the existing `/library/:videoId` route.

- [ ] **Step 4: Confirm scope preservation**

Compare WF04/WF06/WF07/WF08/WF09 content-node parameters with the regression snapshots. Confirm no other video job changed and no new job was created.

- [ ] **Step 5: Produce the final report**

Report migration, backend/frontend files, failure mechanism, event boundaries, API examples, stale threshold, polling behavior, both record verifications, test/build evidence, and explicit confirmation that no video job was created.
