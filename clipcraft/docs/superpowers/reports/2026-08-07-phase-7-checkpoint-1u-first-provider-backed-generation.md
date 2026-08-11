# Phase 7 Checkpoint 1U: First Provider-Backed Production Generation

## Status

**FIRST_PROVIDER_BLOCKED**

The first, exactly-one, provider-backed production job was created and ran
naturally. The pipeline stopped at the `generate_script` stage (WF17 AI
Generate Script → `ClipCraft Text Execute` node) because the internal AI API
is unreachable: the `clipcraft-backend` container is `Exited (255)`, so the
custom node receives an HTTP 500 `AI_PROVIDER_UNAVAILABLE` /
`"internal API is unavailable"` on every retry, then exhausts its retry budget
and fails the stage. The checkpoint stops here; no MP4 was produced.

## Objective

Execute exactly ONE provider-backed, production video generation end-to-end
(the first live E2E through the real provider path), and observe the pipeline
naturally. Stop at the first blocker or successful MP4. Never create a second
job.

## Pre-flight (all PASS)

- n8n `/healthz` → 200.
- Renderer internal `/health` → `{"status":"ok"}`.
- TTS `/health` → 200 `{"kokoro":true,"piper":true}`.
- Supabase reachable; `clipcraft-backend:8000/api/health` → HTTP 200
  `{"status":"ok"}`.
- 0 active/queued jobs, 0 active leases, 0 running stage runs/executions.
- 15 workflows active; 1 credential (`ClipCraft Internal API`,
  `clipCraftInternalApi`).
- Provider/mode config (from `clipcraft/.env`): `TEXT_EXECUTION_MODE=internal`,
  `IMAGE_EXECUTION_MODE=internal`, `AI_TEXT_PROVIDER=cloudflare`,
  `AI_IMAGE_PROVIDER=cloudflare`, `CLOUDFLARE_TEXT_MODEL`/`CLOUDFLARE_IMAGE_MODEL`
  set, `TTS_BASE_URL=http://clipcraft-tts:8000`.

## Live workflow versions (recorded pre-run)

WF02 `UdY7u9pMHE6KrjFb` v5, WF03 `1usjkGUZXjFpXZNU` v38, WF04
`dWTF2UGXX3R73PDW` v58, WF05 `gazJuTcoSGqYdGze` v29, WF06 `UhWkv3GLHVSpWrMe`
v16, WF07 `dNgYGCqkbwr552EW` v10, WF08 `iik8qVHvgD9xWWjI` v9, WF09
`gqX0rJ1gqzHCNDso` v15, WF17 `17` v40 (activeVersion
`75ffd275-e66c-420e-9523-bdc92a622854`), WF18 `18` v16, WF15
`q92RjJtxMX48AYHv` v12, WF11 `wCuJOUfs242lrkO3` v2.

## Job created (exactly one)

`POST http://localhost:5680/webhook/videos/create` → HTTP 202
`{"success":true,"jobId":"3f426c40-90da-48f7-b67d-9fc9eb21de67","status":"queued"}`.

## Automated pipeline trace

- WF02 42358 create (success).
- WF03 42359 claim (lease acquired by `clipcraft-n8n`; job →
  `generating_script`, progress 5, attempt 1, pipeline_revision 1).
- WF04 42360 (success).
- WF17 42361 (`ClipCraft Text Execute` provider stage, success frame,
  mode=integrated; parent exec 42360 resumed).
- WF03 42362 poll.
- Stage `generate_script` (`job_stage_runs`) → `failed`, run_token
  `e8d5ab09-ec9b-4521-8ec8-bffc46ce86d9`, input_hash
  `0d565afdcfb15fb44cd2f01008518c70bad203922833ea4165c7319896c5398d`, error
  `Provider request failed after the maximum retry count`, started
  `20:42:49.635449+00`, completed `20:42:57.493972+00`.

## Blocker: internal AI API unavailable (root cause)

- The custom `ClipCraft Text Execute` node targets
  `http://clipcraft-backend:8000/internal/ai/text/execute`.
- `docker ps -a`: `clipcraft-backend` is **Exited (255)**, image
  `python:3.11-slim`. It is attached to the `clipcraft` network but has no IP
  endpoint while stopped.
- `docker inspect`/network: the running containers are `clipcraft-tts`,
  `clipcraft-n8n`, `clipcraft-renderer`; the backend container is present in
  network metadata but is not running (`Exited 255`).
- From inside the n8n container, `curl http://clipcraft-backend:8000/api/health`
  → `Name does not resolve` (Errno -2), and
  `curl -X POST http://clipcraft-backend:8000/internal/ai/text/execute -d '{}'`
  → same. This confirms the internal AI API is unreachable at the network/DNS
  level, not an application-level error.
- Node behavior: 3 retries, each HTTP 500
  `{"error":{"code":"AI_PROVIDER_UNAVAILABLE","message":"internal API is
  unavailable","retryable":true}}`, then exhausted. No provider-backed script
  result was produced.

## Investigation

- The internal AI mode is served by the FastAPI `clipcraft-backend` container,
  which is not part of `clipcraft/docker-compose.yml` (that file only defines
  n8n/tts/renderer). The backend container is a separate deployment that is
  currently stopped (`Exited 255`).
- Unknown-request probe (provider-free) still succeeded, confirming only the AI
  endpoints are down — the rest of the pipeline graph is intact.

## Stop Boundary

- **No provider-backed generation result** — the pipeline naturally reached the
  provider stage and stopped on the unreachable backend.
- The single job `3f426dfe-...` is left intact and not deleted (no retry; the
  stage run is already `failed` and the job-lease will expire naturally).
- No second job created; no workflow modified; no migration run; no provider or
  Docker configuration changed.

## Regression (this workspace)

- `clipcraft/tests`: **180 passed**.
- `backend/tests` + n8n-factory: **261 passed**, 1 pre-existing unrelated
  failure (a test points to `009_video_job_configuration_snapshots.sql`, which
  does not exist in the repo migration set — not introduced by this checkpoint).
- n8n-custom-nodes (`node --test test/*.test.js`): **29 passed**.
- `docker-compose config`: valid. (No frontend UI package exists in this
  workspace, so no separate frontend build ran.)

## Next

Re-verify `clipcraft-backend` is up and healthy on `clipcraft-backend:8000`
(the internal AI container), then re-run one production checkpoint-1V-style
job (or repair the backend deployment) to get the first successful
provider-backed generation. Ensure the backend is included in the compose
layout or that the internal AI mode targets the running service before the
next generation.