# Flexible Duration and Third-Party TTS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Automatic duration a flexible minimum, add pre-generation Third-Party narration exports, and preserve Phase 8 behavior.

**Architecture:** Centralize duration ranges in backend/workflow-compatible configuration, persist the selected third-party export style with the job, and keep narration formatting outside canonical script JSON. WF04 estimates and validates narration duration, while WF06 persists actual automatic TTS duration as the timing authority.

**Tech Stack:** FastAPI/Pydantic, PostgreSQL migrations, n8n workflow JSON, React/TypeScript, pytest, Vitest.

---

### Task 1: Persist voice-source export settings

**Files:**
- Modify: `clipcraft/supabase/migrations/<new>_narration_export_style.sql`
- Modify: `backend/app/models.py`
- Modify: `backend/app/clients.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

- [ ] Write failing API tests for creation, regeneration, and duplication preserving `audio_mode` and `narration_export_style`.
- [ ] Run the focused tests and confirm they fail because the style is absent or not copied.
- [ ] Add the constrained column, draft field, database projection, creation snapshot, and copy behavior.
- [ ] Re-run focused tests and confirm they pass.

### Task 2: Add narration exporter and API contracts

**Files:**
- Create: `backend/app/services/narration_export.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api.py`
- Test: `backend/tests/test_narration_export.py`

- [ ] Write failing unit tests for clean and sparse expressive output without canonical narration mutation.
- [ ] Write failing API tests for stored-style downloads and explicit format override.
- [ ] Implement the exporter and route it through the existing narration endpoint.
- [ ] Re-run focused tests and confirm they pass.

### Task 3: Update Generate form and narration action

**Files:**
- Modify: `frontend/src/features/generate/components/GenerateForm.tsx`
- Modify: `frontend/src/features/videos/api/videoService.ts`
- Modify: `frontend/src/features/preview/components/RenderStatus.tsx`
- Test: relevant existing frontend test files or new colocated tests

- [ ] Write failing component tests for pre-submit Voice Source, conditional export style, automatic helper text, and download action.
- [ ] Implement only the compatible controls and existing download service wiring.
- [ ] Run focused tests and production build.

### Task 4: Centralize flexible duration validation

**Files:**
- Create: `backend/app/services/narration_duration.py` or existing shared configuration location after inspection
- Modify: `clipcraft/workflows/04-generate-script-and-scenes.json`
- Test: `backend/tests/test_narration_duration.py`
- Test: `clipcraft/tests/test_workflow_integration.py`

- [ ] Write failing range-boundary and revision-limit tests for all four duration choices.
- [ ] Implement duration estimation, flexible scene count, exactly two revisions, and structured terminal failure.
- [ ] Run focused backend and workflow tests.

### Task 5: Make automatic TTS duration authoritative

**Files:**
- Modify: `clipcraft/workflows/06-generate-narration.json`
- Modify: downstream workflow exports that derive scene/caption/manifest timing
- Test: `clipcraft/tests/test_workflow_integration.py`
- Test: `clipcraft/tests/test_foundation_contracts.py`

- [ ] Write failing workflow contract tests for persisted effective duration, safe correction bounds, and custom-audio authority.
- [ ] Implement WF06 duration persistence and downstream timing propagation.
- [ ] Run WF06 parity and timing contracts.

### Task 6: Full verification and release

**Files:**
- Modify: only files required by corrections found during verification

- [ ] Run backend, workflow, migration, frontend build, compose validation, and secret scan.
- [ ] Create one Automatic sample only through `POST /api/videos`; observe it to completion and record all timing metrics.
- [ ] Create disposable Third-Party jobs only through the public API; verify clean/expressive downloads and hard delete them through the public API.
- [ ] Inspect the worktree, remove diagnostics/media/runtime artifacts, commit logical changes, merge to `main`, push, and tag `v0.3.1-flexible-duration` only if every release gate passes.
