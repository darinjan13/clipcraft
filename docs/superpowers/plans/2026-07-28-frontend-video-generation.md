# Frontend Video Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete one 30-second video submitted through the existing Generate page and verify playback from `/library/:videoId`.

**Architecture:** Trace the existing frontend-to-FastAPI-to-n8n path first, then repair only the first proven contract defect. Preserve the live WF05/WF18 Cloudflare path, shared `/data/jobs` volume, existing stage workflows, and renderer.

**Tech Stack:** React, TanStack Query, FastAPI, httpx, n8n, Supabase REST API, Docker, ffprobe.

---

### Task 1: Snapshot and baseline

**Files:**
- Create: `backups/pre-frontend-generation-wf02.json`
- Create: `backups/pre-frontend-generation-wf03.json`

- [ ] Export only WF02 `UdY7u9pMHE6KrjFb` and WF03 `1usjkGUZXjFpXZNU` from live n8n.
- [ ] Run the existing backend test suite and record the baseline count.
- [ ] Confirm the frontend, backend, n8n, renderer, and TTS services are running before the controlled request.

### Task 2: Trace the real Generate request

**Files:**
- Read: `frontend/src/features/generate/pages/GeneratePage.tsx`
- Read: `frontend/src/features/generate/components/GenerateForm.tsx`
- Read: `frontend/src/features/videos/api/videoService.ts`
- Read: `backend/app/main.py`
- Read: `backend/app/clients.py`

- [ ] Start the existing frontend and backend with their repository commands.
- [ ] Submit exactly one 30-second topic through the Generate page.
- [ ] Capture request JSON, response JSON/status, FastAPI logs, n8n execution IDs, and the created Supabase job UUID.
- [ ] Stop at the first failed boundary and write a failing regression test before changing application code.

### Task 3: Repair the first failing boundary

**Files:**
- Modify only the file or live workflow proven to fail in Task 2.
- Test: Add or update the narrowest existing test covering the failed contract.

- [ ] Reproduce the exact failure in a focused test or controlled execution.
- [ ] Apply the smallest compatible fix without changing the route, schema, provider, or renderer.
- [ ] Re-run the focused test and then the existing backend/workflow tests.
- [ ] Export any changed live workflow under `backups/pre-frontend-generation-<workflow>.json` before editing it.

### Task 4: Complete the single controlled job

**Files:**
- Modify only proven integration adapters.

- [ ] Verify WF03 claims one job and follows the existing deterministic claim path.
- [ ] Verify script, six-or-fewer scene rows appropriate to 30 seconds, narration, captions, manifest, and renderer stages.
- [ ] Skip only already-valid persisted outputs; do not regenerate valid assets.
- [ ] Verify `/data/jobs/{jobId}` is shared and every manifest path is container-visible.

### Task 5: Verify backend and frontend outputs

**Files:**
- Read: `frontend/src/features/preview/pages/PreviewPage.tsx`
- Read: `frontend/src/features/library/pages/LibraryPage.tsx`
- Modify only compatibility defects proven by the completed job.

- [ ] Verify completed status, MP4 range response, thumbnail response, ffprobe codec/resolution/duration, Preview playback, and Library listing.
- [ ] Confirm no duplicate job was created and no hardcoded demo media is used.
- [ ] Run the full relevant test suites and report exact workflow IDs, execution IDs, paths, sizes, status progression, and remaining cleanup.
