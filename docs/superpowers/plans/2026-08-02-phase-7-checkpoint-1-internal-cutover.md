# Phase 7 Checkpoint 1 Internal Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the already-verified internal text and image branches the runtime defaults, then produce and verify exactly one complete video while preserving explicit legacy rollback.

**Architecture:** The primary agent alone changes `.env`, container runtime state, and production execution state. Read-only reviews establish deployment, compatibility, cost, security, rollback, and test gates before mutation. The cutover changes only environment-selected branches; workflow graphs, provider contracts, downstream media stages, and legacy branches remain intact.

**Tech Stack:** Docker Compose, n8n 2.29.7, Supabase/PostgREST, FastAPI, TTS, renderer/FFmpeg, Python pytest, Node custom-node tests, Vite.

---

### Task 1: Complete read-only pre-cutover gate

**Files:**
- Read: `clipcraft/.env`
- Read: `clipcraft/docker-compose.yml`
- Read: `clipcraft/workflows/17-ai-generate-text.json`
- Read: `clipcraft/workflows/18-ai-generate-image.json`
- Read: `clipcraft/workflows/03-video-job-worker.json`
- Read: `clipcraft/workflows/05-generate-scene-images.json`
- Read: `clipcraft/workflows/06-generate-narration.json`
- Read: `clipcraft/workflows/07-build-captions.json`
- Read: `clipcraft/workflows/08-build-render-manifest.json`
- Read: `clipcraft/workflows/09-render-video.json`

- [ ] Verify current mode source and runtime values are both `legacy`.
- [ ] Verify no active job and no running WF17/WF05/WF18/worker execution.
- [ ] Verify current live IDs, active states, node counts, credential references, workflow count, and credential count through authenticated API v1 or read-only SQLite fallback.
- [ ] Verify n8n, backend `/api/health`, renderer `/health`, and TTS `/health`.
- [ ] Stop if a job is active, live workflow identity differs, custom nodes are missing, SQLite is not healthy, or the API/full-pipeline contract is unexplained.

### Task 2: Create and verify a new pre-cutover backup

**Files:**
- Create: `clipcraft/backups/phase-7-cutover/<UTC-timestamp>/`
- Read-only source: current live workflow exports, SQLite database, Compose, environment configuration, custom-node package

- [ ] Export WF17, WF05, WF18, queue worker, and direct callers without printing secrets.
- [ ] Copy Compose configuration, protected environment configuration, SQLite using a consistent method, and custom-node package.
- [ ] Record workflow IDs, active states, node counts, credential references, timestamps, container image IDs, and encryption-key fingerprints only.
- [ ] Verify every backup file is non-empty and SQLite `PRAGMA integrity_check` returns `ok`.
- [ ] Stop if any backup artifact is missing or empty.

### Task 3: Audit and apply internal defaults

**Files:**
- Modify: `clipcraft/.env`
- Modify if needed: `clipcraft/.env.example`
- Read/validate: `clipcraft/docker-compose.yml`, workflow mode gates, startup/runtime environment

- [ ] Document precedence: `.env` → Compose interpolation → container environment → `$env.*` workflow gates.
- [ ] Set exactly `TEXT_EXECUTION_MODE=internal` and `IMAGE_EXECUTION_MODE=internal` in the approved environment source.
- [ ] Recreate only the n8n container required for the environment change, preserving volumes, SQLite, encryption key, workflows, credentials, executions, and custom nodes.
- [ ] Verify runtime modes are internal and health/count/active-state checks remain unchanged.
- [ ] Do not start a video until both pre-flight provider checks pass.

### Task 4: Run internal pre-flight probes

**Files:**
- Read-only workflow execution evidence and runtime logs

- [ ] Run one minimal WF17 internal request and verify custom text node, no legacy provider node, HMAC, normalized output, one provider call, and no secret/prompt leakage.
- [ ] Run one minimal WF18 internal request and verify custom image node, no legacy provider node, HMAC, BinaryData, imageBase64/MIME/filename, one provider call, and no secret/prompt/image leakage.
- [ ] Stop and report `CUTOVER_READY_BUT_QUOTA_BLOCKED` if quota exhaustion occurs; do not fall back to legacy.

### Task 5: Execute exactly one full video

**Files:**
- Create only the one requested video job through the existing public job path
- Read: Supabase job/stage/event/assets rows, n8n executions, `/data/jobs/<jobId>`, result/download endpoints

- [ ] Create one safe 20–30 second vertical job with approximately five scenes and record only the job ID/correlation IDs.
- [ ] Verify all six durable stages, internal text/image branch exclusivity, request IDs, asset persistence, TTS, captions, manifest, render, thumbnail, completion/status, result, and download responses.
- [ ] Verify FFprobe metadata for MP4 codec, resolution, orientation, duration, audio, and non-zero file size.
- [ ] Stop immediately on duplicate provider calls, quota exhaustion, contract drift, missing files, failed stages, or stale active-job behavior.

### Task 6: Perform rollback drill and restore internal defaults

**Files:**
- Modify temporarily: `clipcraft/.env`
- Read-only: workflow/runtime state and minimal branch-selection evidence

- [ ] Set both modes to `legacy`, recreate only required container, and verify WF17/WF18 legacy selection with no DB/workflow import.
- [ ] Restore both modes to `internal`, recreate only required container, and verify internal selection and active workflow identity.
- [ ] Confirm final state is internal/internal, with legacy branches and credentials retained.

### Task 7: Run final tests, reviews, and report

**Files:**
- Create: `docs/superpowers/reports/2026-08-02-phase-7-checkpoint-1-internal-provider-cutover.md`
- Update: `docs/superpowers/reports/2026-08-02-phase-5-checkpoint-6b-wf18-custom-image-integration.md`

- [ ] Run workflow validation, focused/full workflow tests, custom-node tests, backend tests, frontend build, Compose validation, health checks, SQLite integrity, source/export/runtime secret scans, security review, compatibility review, architecture review, output-quality review, and rollback review.
- [ ] Record backup, mode before/after, pre-flight evidence, one job ID, execution IDs, stage results, output metadata, call counts, rollback evidence, residual risks, and final modes.
- [ ] Set status to `INTERNAL_CUTOVER_COMPLETE` only if all hard-stop conditions remain clear; otherwise use the exact blocked/failed status.
