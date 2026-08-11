# Phase 7 Final Recovery

- **Date:** 2026-08-07
- **Project:** clipcraft-ai (live)
- **Status:** `PHASE_7_BLOCKED_PIPELINE`

## Objective
Restore the existing backend service exactly as declared by Docker Compose, verify
internal networking, run exactly one controlled provider-backed generation, and
record the outcome. Stop at the first new blocker.

## Phase A: Backend recovery

### Backend exit root cause
`clipcraft-backend` (image `python:3.11-slim`, working dir `/app`, cmd `sh -c "pip
install -q . && uvicorn app.main:app --host 0.0.0.0 --port 8000"`) had
`Status: exited`, `ExitCode: 255`, `OOMKilled: false`, `RestartCount: 0`, healthy
startup logs (`Application startup complete. Uvicorn running on 0.0.0.0:8000`)
prior to stopping. Exit 255 with no OOM and zero restarts indicates an external
stop/shutdown rather than a crash; configuration, environment, and mounts were
intact on the stopped container.

### Backend recovery
Started `clipcraft-backend` via `docker start` (no rebuild, no reconfiguration).
Container entered `running`, `ExitCode 0`, startup log clean. The backend is not
part of `clipcraft/docker-compose.yml` (that file defines only n8n/tts/renderer) and
carries no host port mapping (exposed via the `clipcraft` bridge network only).

### n8n-to-backend connectivity
- Host: no direct host route to the bridge (`8000` unroutable from Windows host) —
  expected; backend is internal-only.
- From inside `clipcraft-n8n`:
  - `clipcraft-backend` DNS resolves.
  - `GET http://clipcraft-backend:8000/api/health` → **HTTP 200** `{"status":"ok"}`.
  - `POST /internal/ai/text/execute` → reachable (returned 401/422 on
    probe/empty inputs; no provider call made during the check).

### Other services (verified)
- n8n: `/healthz` HTTP 200, healthy.
- renderer: `http://clipcraft-renderer:8088/health` → HTTP 200 `{"status":"ok"}`.
- TTS: `http://clipcraft-tts:8000/health` → HTTP 200
  `{"kokoro":true,"piper":true,"status":"ok"}`.
- Supabase: reachable (used for all job-state queries).

## Phase B (Existing job reconciliation)

Job `3f426c40-90da-48f7-b67d-9fc9eb21de67` from checkpoint 1U:
- status `generating_script`, attempt 1/3, lease expired (not active).
- Its `generate_script` stage run is **terminal `failed`** (`error_message`
  `Provider request failed after the maximum retry count`, non-retryable).
- `begin_job_stage` keys stage runs on `(job_id, pipeline_revision, stage,
  item_key)` — not attempt — and returns `FAILED` for any existing `failed` run,
  never overwriting it. Reaper/claim only bump `attempt_number` (revision stays 1),
  so a re-claim cannot re-run the failed stage.
- Conclusion: **the existing job cannot be retried safely**. It was preserved
  (no deletion, no manual lease/attempt/stage fabrication).

## Phase C (Controlled generation)

After confirming 0 active leases / 0 running stage runs / 0 claimable queued jobs,
exactly **one new** production job was created:

### Production job ID
`ca3a7507-e604-4113-8477-b3b81c5cca5e` (brief: 30s, 5-6 scenes, "history of the
solar system in five milestones", cloudflare text/image providers).

### Execution path
WF02 create (42537) → WF03 claim (42538) → WF04 (42539) → WF17 (42540) → WF03
polls (42541–42548). Job advanced `queued → generating_script` (progress 5).

## Provider calls
None. The internal backend endpoint was reached (`POST /internal/ai/text/execute`
HTTP **422 `AI_REQUEST_INVALID`**), but no Cloudflare provider request was ever sent.

## First blocker (WF17 internal route)

- Affected workflow: **WF17 `AI Generate Text`**, node **`Prepare Internal Request`**.
- Execution ID: **42540** (WF17), parent 42539 (WF04).
- Root cause: `Prepare Internal Request` (node
  `wf17-internal-prepare-0000-000000000012`) builds
  `prompt: String(input.prompt ?? source.prompt ?? body.prompt ?? '')`. The incoming
  item from `Text Execution Mode?` is `Build Request`'s output `{isValid, provider,
  url, headers, body:{messages,...}}`, which has **no top-level `prompt`** — the
  prompt lives inside `body.messages[0].content`. The `?? ''` fallback won and sent an
  **empty `prompt`** to the custom `ClipCraft Text Execute` node.
- The custom node forwarded to `clipcraft-backend:8000/internal/ai/text/execute`,
  which returned HTTP 422 `{"success":false,"status":"failed","error":{...code
  "AI_REQUEST_INVALID","message":"request is invalid","retryable":false,...}}`.
- `Adapt Internal Result` mapped it to `statusCode 400` non-retryable; `Evaluate
  Provider Result` → `PROVIDER_HTTP_ERROR "Cloudflare text provider did not return a
  valid response"`, and the `failure` stage run was recorded.
- Stage `generate_script` in `job_stage_runs` → **failed**,
  `error_json.message="Cloudflare text provider did not return a valid response"`,
  `_retryable:true`; job set `failure_class=provider` at attempt 1.
- Because `begin_job` treats that failed run as terminal (same job/revision/stage/item_key,
  never overwritten), re-claims/requeues cannot advance this job.

## Route outcome
- Scenes: not reached (blocked at generate_script provider stage).
- Images: not reached.
- TTS: not reached.
- Captions: not reached.
- Manifest: not reached.
- Renderer: not reached.
- MP4: not produced.
- Download: N/A (no output).
- Lease: expired naturally (0 active leases now); no manual lease mutation.

## Failure policy (Phase D)
- Stopped immediately at the first new blocker.
- Evidence preserved: job `ca3a...` and old job `3f426...` both intact (status
  `generating_script`, attempt 1, executed leases expired); execution 42540 and
  stage-run row preserved.
- Workflow/node/exec ID/normalized error/service recorded above. No workflow,
  migration, provider, or Docker configuration change was made (backend was merely
  started, not reconfigured). Do not begin Pexels.

## Tests
- `clipcraft/tests`: **180 passed**.
- `backend/tests` + n8n-factory: **261 passed**, 1 pre-existing unrelated failure
  (test points to `009_video_job_configuration_snapshots.sql`, which is not in the
  repo migration set — not introduced by this checkpoint).
- n8n-custom-nodes (`node --test test/*.test.js`): **29 passed**.
- `docker-compose config`: valid.

## First blocker
Interim: external backend stop (interrupted, recovered in Phase A). New/correctly
determined blocker for this period: WF17 `Prepare Internal Request` sends an **empty
prompt** to the internal text endpoint → HTTP 422 `AI_REQUEST_INVALID` → the script
stage cannot proceed. Affected service: workflow runner / internal AI text route.

## First blocker recurrence of the phase
The first actual Phase C blocker is the WF17 internal empty-prompt defect described
under "Blockers".

## Phase 7 status
**PHASE_7_BLOCKED_PIPELINE**

## Recommendation (next, non-automatic)
Repair `Prepare Internal Request` in WF17 to forward the prompt (e.g. read
`input.body.messages[0].content` or the trigger `prompt` field) so the internal
route receives a non-empty prompt, then, with leave, re-run one controlled
generation. No other change is required; the backend is healthy and reachable.