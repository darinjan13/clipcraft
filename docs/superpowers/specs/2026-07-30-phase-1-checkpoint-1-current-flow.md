# Phase 1 Checkpoint 1: Current Local Application and Data Flow

## Purpose

Checkpoint 1 documents and tests the current single-user local system before
provider-security changes. It is a characterization of existing behavior, not
a credential migration or production behavior change.

## Observed Frontend Flow

- `frontend/src/features/videos/api/videoService.ts` sends requests to
  `VITE_API_BASE_URL`, defaulting to `http://127.0.0.1:8000`.
- The shared `request` helper adds `Content-Type: application/json` and does
  not use browser authentication, as expected for the single-user deployment.
- User operations currently call `GET /api/videos`, `POST /api/videos`,
  `GET/PATCH/DELETE /api/videos/{id}`, status, regeneration, duplication,
  cancellation, and media paths through the local FastAPI boundary.
- The model-capability endpoint is also called through the same local helper.

## Observed FastAPI Flow

- `backend/app/main.py` creates the app without browser authentication or an
  inbound callback endpoint.
- `/api/health` is public and returns only `{"status": "ok"}`.
- User routes intentionally accept requests without browser authentication.
  The legacy `user_id` field is not used as an ownership model and is not set
  on new jobs by FastAPI.
- Job routes first read by ID and then perform updates/deletes. Status reads may
  call n8n after the database lookup.
- Media routes check only whether a job ID exists, then serve a fixed filename
  from the UUID-scoped filesystem directory.

## Observed Supabase Flow

- `backend/app/clients.py::DatabaseClient` is the only application client for
  the backend REST calls.
- It authenticates every Supabase REST request with
  `SUPABASE_SERVICE_ROLE_KEY` in both `apikey` and `Authorization` headers.
- Reads and writes target `video_jobs`, `scenes`, `assets`, and
  `video_job_events` directly through `/rest/v1`.
- Job reads, updates, and deletes filter by job ID only; list reads filter out
  cancelled jobs.
- Because service-role access bypasses RLS, current application behavior is
  controlled by the backend service boundary rather than browser database
  access.

## Current Data Baseline

The live `public.video_jobs` table contains 42 rows. All 42 have null `user_id`;
there are zero UUID-valued owner strings. Phase 1 preserves this legacy
nullable text field for compatibility and does not convert, remove, repurpose,
or use it for ownership.

## Checkpoint Tests

`backend/tests/test_checkpoint_1_current_flow.py` characterizes these facts by
checking that local routes are callable without browser authentication,
frontend requests do not inject browser credentials, and the database client
uses service-role REST headers.

These tests intentionally describe the current single-user boundary and should
be retained while provider-security checkpoints are added.
