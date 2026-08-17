# Workflows

19 workflows implementing the AI video factory pipeline.

## Index

| # | File | Purpose | Trigger |
|---|------|---------|---------|
| 01 | `01-chat-message.json` | AI Video Chat — collect brief via conversation | Webhook |
| 02 | `02-create-video-job.json` | Create a new video job from brief | Webhook |
| 03 | `03-video-job-worker.json` | Queue poller — claims and processes jobs | Schedule |
| 04 | `04-generate-script-and-scenes.json` | Generate script + scenes via AI | Webhook |
| 05 | `05-generate-scene-images.json` | Generate scene images via AI | Webhook |
| 06 | `06-generate-narration.json` | Generate TTS narration audio | Webhook |
| 07 | `07-build-captions.json` | Build ASS subtitle file | Webhook |
| 08 | `08-build-render-manifest.json` | Build FFmpeg render manifest | Webhook |
| 09 | `09-render-video.json` | Execute FFmpeg video render | Webhook |
| 10 | `10-get-job-status.json` | Get current job status | Webhook |
| 11 | `11-get-video-result.json` | Get completed video result + download URLs | Webhook |
| 12 | `12-regenerate-scene.json` | Regenerate a single scene image | Webhook |
| 13 | `13-regenerate-video.json` | Regenerate entire video (full or partial) | Webhook |
| 14 | `14-error-handler.json` | Handle job errors with retry logic | Webhook |
| 15 | `15-download-asset.json` | Serve downloadable video/thumbnail/captions | Webhook |
| 16 | `16-resolve-asset-paths.json` | **Internal.** Resolve canonical asset paths | WorkflowTrigger |
| 17 | `17-ai-generate-text.json` | **Internal.** AI text generation (provider-abstracted) | WorkflowTrigger |
| 18 | `18-ai-generate-image.json` | **Internal.** AI image generation (provider-abstracted) | WorkflowTrigger |
| 19 | `19-reap-expired-leases.json` | Reaper — reclaims expired video job leases | Schedule (60s) |

## Calling Convention

- **Public webhooks** (WF01–WF15): Called via HTTP POST/GET to `http://clipcraft-n8n:5678/webhook/...`
- **Internal sub-workflows** (WF16–WF18): Called via n8n Execute Workflow node. No webhook. Provider-agnostic contracts.

## Provider Abstraction

WF17 and WF18 are the only workflows that call AI providers directly. All other workflows use Execute Workflow nodes to call them. To switch AI providers, update the Build Request code node in WF17/WF18 and set `AI_TEXT_PROVIDER` / `AI_IMAGE_PROVIDER` environment variable.

## Asset Paths

WF16 is the sole source of truth for local filesystem paths. It must produce identical output to the PostgreSQL `get_asset_path()` function and the Python `video-tools/asset_paths.py` module.
