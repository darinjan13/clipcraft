# Workflow Catalog

## Identifier Rules

The number in a filename or label such as WF17 is a repository/project label. The primary JSON for WF16-WF18 contains numeric top-level IDs `16`, `17`, and `18`, but public n8n imports may assign different IDs. Public workflow source files do not establish their eventual live n8n IDs. The functional suite therefore requires explicit runtime IDs and expected names.

Configuration discovery confirmed repository-derived values only: WF17 source ID `17`, name `AI Generate Text`; WF18 source ID `18`, name `AI Generate Image`. These are not verified local runtime IDs and must not be treated as authoritative for the local n8n instance. Once the local Public API key is available, discover the actual local runtime IDs from the configured n8n instance. The primary local base URL is discoverable as `http://localhost:5680` from `clipcraft/.env` and the `5680:5678` Compose mapping. No supported public n8n API key was found in the inspected local runtime configuration.

## Primary Workflow Inventory

| Label | Repository file | Exact source name | Trigger | Purpose | Source active flag |
|---|---|---|---|---|---|
| WF01 | `01-chat-message.json` | AI Video Chat Clarification | Webhook `POST video-chat/message` | Collect and clarify a brief, load chat history, persist chat state, and route toward generation | `false` in source |
| WF02 | `02-create-video-job.json` | Create AI Video Job | Webhook `POST videos/create` | Validate brief, create job ID, insert queued `video_jobs` row, return `202` | `false` in source |
| WF03 | `03-video-job-worker.json` | Video Job Queue Worker | Schedule every 10 seconds | Atomically claim queued jobs and invoke pipeline steps | `false` in source |
| WF04 | `04-generate-script-and-scenes.json` | Generate Script and Scenes | Webhook `POST video/generate-script` | Load brief, call text generation, persist script/scenes | `false` in source |
| WF05 | `05-generate-scene-images.json` | Generate Scene Images | Webhook `POST video/generate-images` | Generate scene images and persist asset state | `false` in source |
| WF06 | `06-generate-narration.json` | Generate Narration | Webhook `POST video/generate-narration` | Call local TTS and persist audio asset | `false` in source |
| WF07 | `07-build-captions.json` | Build Captions | Webhook `POST video/build-captions` | Generate ASS captions | `false` in source |
| WF08 | `08-build-render-manifest.json` | Build Render Manifest | Webhook `POST video/build-manifest` | Resolve asset paths and write render manifest | `false` in source |
| WF09 | `09-render-video.json` | Render AI Video | Webhook `POST video/render` | Run FFmpeg, insert video/thumbnail assets, mark completed | `false` in source |
| WF10 | `10-get-job-status.json` | Get AI Video Job Status | Webhook `GET video/status` | Return job status/progress and scene status | `false` in source |
| WF11 | `11-get-video-result.json` | Get AI Video Result | Webhook `GET video/result` | Return completed result and safe download URLs | `false` in source |
| WF12 | `12-regenerate-scene.json` | Regenerate Scene | Webhook `POST video/regenerate-scene` | Regenerate one image and update scene/job state | `false` in source |
| WF13 | `13-regenerate-video.json` | Regenerate Video | Webhook `POST video/regenerate` | Reset selected pipeline portions for full/partial regeneration | `false` in source |
| WF14 | `14-error-handler.json` | Video Factory Error Handler | Webhook `POST video/error` | Sanitize errors and invoke retry/failure RPC | `false` in source |
| WF15 | `15-download-asset.json` | Download Video Asset | Webhook `GET videos/download` | Authenticate and stream allowlisted files | `false` in source |
| WF16 | `16-resolve-asset-paths.json` | Resolve Asset Paths | Workflow Trigger | Return canonical safe local path and filename | `true` in source; backup state conflicts |
| WF17 | `17-ai-generate-text.json` | AI Generate Text | Workflow Trigger | Build and call Cloudflare text request, normalize response, retry | `true` in source; backup/live state conflicts |
| WF18 | `18-ai-generate-image.json` | AI Generate Image | Workflow Trigger | Build and call Cloudflare image request, normalize response, retry | `true` in source; backup/live state conflicts |

## Static Caller Relationships

The primary source contains these direct Execute Workflow references:

- WF01 → workflow ID `17`.
- WF04 → workflow ID `17`.
- WF05 → workflow ID `18`.
- WF12 → workflow ID `18`.

The documented architecture says WF08 should use WF16, but no current primary workflow reference to WF16 was found. WF03 instead calls downstream public webhook URLs for WF04-WF09 and WF14 using the internal `clipcraft-n8n:5678` hostname.

## Internal Workflow Contracts

The shared contract documents:

- WF16 input `{ jobId, assetType, sceneIndex? }` and safe path output.
- WF17 input `{ prompt, systemPrompt? }` and normalized text response.
- WF18 input `{ prompt, job_id?, scene_index? }` and normalized image response.

WF17 and WF18 now construct provider request objects through `Build Request`, route validation through `Validate Input` and `Handle Validation Error`, and emit the normalized response contract. Runtime workflow identity remains separate from repository source IDs.

Both workflow-trigger nodes include `parameters.events: ["update"]` because
the local n8n runtime rejects empty trigger parameters when workflows are
published through the documented public API.

## WF17 and WF18 Risks

- Runtime WF17/WF18 state was verified through the documented public API on 2026-07-26.
- Source callers hard-code numeric IDs.
- Retry state is explicitly carried in item-level `retryCount`; `Evaluate Provider Result` and `Increment Retry` implement a maximum of two retries without node-run history.
- Provider abstraction documentation says only WF17/WF18 call AI providers, but legacy trees contain direct Cloudflare calls.
- Live WF17/WF18 IDs were discovered by exact name as `17` and `18`; both remained active after alignment.

## Test Coverage

- Static workflow validation is reported in `clipcraft/workflow-validation-report.json` and `IMPLEMENTATION_REPORT.md`.
- Asset-path tests are present under `clipcraft/tests/`.
- Root `functional_tests.py` runs static contract checks by default; runtime API tests require explicit opt-in.
- Runtime validation coverage for WF17/WF18 invalid-input paths is verified; valid provider paths remain **UNKNOWN** by approval boundary.
