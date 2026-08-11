# Frontend Video Generation Design

## Goal

Make one request from the existing Generate page complete the existing ClipCraft pipeline and play from `/library/:videoId`, without replacing working workflows or services.

## Architecture

The existing React Generate page submits its current draft to `POST /api/videos`. FastAPI maps that draft to the live WF02 webhook, returns the created UUID, and the existing WF03 dispatcher claims the queued job. WF03 continues through the existing script, scene-image, narration, captions, manifest, and renderer workflows. The existing `/library/:videoId` route remains the Preview route.

Repairs are trace-driven and minimal: export WF02/WF03 first, run one 30-second frontend-created job, identify the first failing boundary, and change only that boundary. The proven WF05/WF18 Cloudflare path and renderer implementation remain unchanged unless execution demonstrates a required adapter defect.

## Contracts

- Frontend payload remains the existing `VideoDraft` shape.
- `POST /api/videos` remains `202` with the existing `Video` response and job UUID.
- Supported durations remain `30`, `45`, `60`, and `90` seconds.
- Job files remain under `/data/jobs/{jobId}` across n8n, FastAPI, and renderer containers.
- Preview remains `/library/:videoId` and uses backend media endpoints.
- No new service, schema, provider, queue, renderer, or frontend route is introduced.

## Verification

Use one new 30-second job submitted through the actual frontend. Capture the browser request, FastAPI response/logs, WF02/WF03/WF05/WF18 executions, Supabase state, all generated asset paths, renderer output metadata, backend media responses, Preview playback, and Library listing. Existing job `a350088f-94ae-41cb-91c3-48b73405c0f9` is not reused or mixed into the test.
