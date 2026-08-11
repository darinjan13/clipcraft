# ClipCraft AI — Shared Contract

## Job Statuses

```
queued → generating_script → script_ready → generating_images
  → generating_voice → building_captions → building_manifest
  → rendering → completed
```

Terminal states: `failed`, `cancelled`

## WF17/WF18 Canonical Provider Contract

WF17 and WF18 return a normalized object. The provider response is not exposed
to callers directly.

```json
{
  "success": true,
  "type": "text | image",
  "result": "text output",
  "imageBase64": "base64 output",
  "format": "png",
  "retryCount": 0,
  "timestamp": "2026-07-27T00:00:00Z",
  "context": {"jobId": "uuid", "sceneId": "uuid", "sceneIndex": 1},
  "_testCorrelationId": "optional-test-marker"
}
```

Text responses require `result`. Image responses require `imageBase64` and
`format`. `context` is optional and WF18 only emits verified caller fields.
Failures use `success: false` and an `error` object with `type`, `code`,
`message`, `retryable`, and `source`. Retry state is explicit and bounded at
two retries. `_testCorrelationId` is test-only and never enters provider data.

Older direct provider shapes such as `result.response`, `result.image`, and
`result.base64` are historical and must not be consumed by active callers.

## Brief JSON (`video_jobs.brief_json`)

```json
{
  "topic":         "string",
  "duration":      30 | 45 | 60 | 90,
  "sceneCount":    6..18,
  "language":      "string",
  "contentStyle":  "string",
  "visualStyle":   "string",
  "voiceTone":     "string",
  "captionStyle":  "string",
  "aspectRatio":   "9:16"
}
```

- `sceneCount` default: `ceil(duration / 5)`
- `aspectRatio` fixed: `"9:16"`

## Script JSON (`video_jobs.script_json`)

```json
{
  "title":         "string",
  "description":   "string",
  "hashtags":      ["#tag"],
  "fullNarration": "string",
  "scenes": [<scene_brief>]
}
```

Scene brief:
```json
{
  "index":          1..N,
  "narration":      "string (required)",
  "caption":        "string (short)",
  "imagePrompt":    "string (no logos/text/watermarks)",
  "durationSeconds":2..10,
  "motion":         "zoom_in",
  "transition":     "crossfade"
}
```

Motion: `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `pan_up`, `pan_down`
Transition: `fade`, `crossfade`, `slide_left`, `slide_right`

## Render Manifest (`video_jobs.render_manifest`)

```json
{
  "jobId":    "uuid",
  "width":    1080,
  "height":   1920,
  "fps":      30,
  "audio":    "/data/jobs/{jobId}/narration.wav",
  "captions": "/data/jobs/{jobId}/captions.ass",
  "output":   "/data/jobs/{jobId}/final.mp4",
  "scenes": [
    {
      "image":      "/data/jobs/{jobId}/scene-01.png",
      "duration":   5,
      "motion":     "zoom_in",
      "transition": "crossfade",
      "caption":    "CAPTION TEXT"
    }
  ]
}
```

## Canonical Asset Map

Single source of truth shared across PostgreSQL, Python, and n8n (WF16). All three implementations must produce identical output.

| Asset Type | Pattern | `get_asset_path(job_id, type, ...)` |
|---|---|---|
| scene | `{jobId}/scene-{NN}.png` | `..., 'scene', 3)` → `/data/jobs/{uuid}/scene-03.png` |
| narration | `{jobId}/narration.wav` | `..., 'narration')` → `/data/jobs/{uuid}/narration.wav` |
| captions | `{jobId}/captions.ass` | `..., 'captions')` → `/data/jobs/{uuid}/captions.ass` |
| manifest | `{jobId}/render-manifest.json` | `..., 'manifest')` → `/data/jobs/{uuid}/render-manifest.json` |
| video | `{jobId}/final.mp4` | `..., 'video')` → `/data/jobs/{uuid}/final.mp4` |
| thumbnail | `{jobId}/thumbnail.jpg` | `..., 'thumbnail')` → `/data/jobs/{uuid}/thumbnail.jpg` |
| render_log | `{jobId}/render.log` | `..., 'render_log')` → `/data/jobs/{uuid}/render.log` |
| error_log | `{jobId}/error.log` | `..., 'error_log')` → `/data/jobs/{uuid}/error.log` |

Implementations:
- **PostgreSQL**: `003_asset_path_functions.sql` → `get_asset_path(job_id, asset_type, scene_index)`
- **Python**: `video-tools/asset_paths.py` → `get_asset_path(job_id, asset_type, scene_index)`
- **n8n**: WF16 resolve-asset-paths → Execute Workflow node

Tests at `tests/test_asset_paths.py` prove all three return identical results.

### RPC: `get_asset_url`

Returns a public download URL for downloadable assets (video, thumbnail, captions).

```
POST /rest/v1/rpc/get_asset_url
{ "job_id": "550e8400-e29b-41d4-a716-446655440000", "asset_type": "video" }
→ "/webhook/videos/download?jobId=550e8400-e29b-41d4-a716-446655440000&asset=video"
```<｜end▁of▁thinking｜>Now update the Local Files table to reference the function:

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="read">
<｜｜DSML｜｜parameter name="offset" string="false">82

The queue worker uses a PostgreSQL-level atomic claim via `claim_next_video_job(worker_id)`.

### `video_jobs` Claiming Columns

| Column | Type | Default | Purpose |
|--------|------|---------|---------|
| `priority` | integer | 0 | Higher values claimed first |
| `claimed_by` | text | null | Worker that claimed the job |
| `claimed_at` | timestamptz | null | When the job was claimed |
| `retry_count` | integer | 0 | Retry attempts so far |
| `max_retries` | integer | 2 | Max retries before giving up |
| `last_error` | text | null | Most recent error message |
| `started_at` | timestamptz | null | When processing first started |
| `finished_at` | timestamptz | null | When processing finished (any outcome) |

### Claim Flow

```
Worker Poller → POST /rest/v1/rpc/claim_next_video_job { worker_id }
  → FOR UPDATE SKIP LOCKED (atomically locks one row)
  → sets status='generating_script', claimed_by, claimed_at
  → returns the claimed job row or null if none available
  → IF null → wait for next poll cycle
  → IF claimed → run sub-workflows sequentially
```

### Error Handling

When a sub-workflow fails:
```
POST /rest/v1/rpc/handle_job_error { target_job_id, error_text }
  → increments retry_count
  → if retry_count < max_retries: resets status='queued', clears claimed_by
  → if retry_count >= max_retries: sets status='failed', sets finished_at
```

### Sub-workflow Contracts

Every sub-workflow receives `{ "jobId": "..." }` and returns `{ "success": true, "jobId": "..." }`.

Worker → sub-workflow calls:
```
POST http://clipcraft-n8n:5678/webhook/video/generate-script    { jobId }
POST http://clipcraft-n8n:5678/webhook/video/generate-images    { jobId }
POST http://clipcraft-n8n:5678/webhook/video/generate-narration { jobId }
POST http://clipcraft-n8n:5678/webhook/video/build-captions     { jobId }
POST http://clipcraft-n8n:5678/webhook/video/build-manifest     { jobId }
POST http://clipcraft-n8n:5678/webhook/video/render             { jobId }
```

## API Endpoints

| Endpoint | Method | Auth | Port |
|----------|--------|------|------|
| /webhook/video-chat/message | POST | — | 5680 |
| /webhook/videos/create | POST | — | 5680 |
| /webhook/video/status | GET | — | 5680 |
| /webhook/video/result | GET | — | 5680 |
| /webhook/video/regenerate-scene | POST | — | 5680 |
| /webhook/video/regenerate | POST | — | 5680 |
| /webhook/video/error | POST | Internal | 5680 |
| /webhook/videos/download | GET | X-Internal-Api-Key header | 5680 |

## Get Video Result — `GET /webhook/video/result?jobId={uuid}`

Returns the completed video result and scene metadata.

### Response Codes

| Code | Condition |
|------|-----------|
| 200 | Completed result available |
| 404 | Job not found |
| 409 | Job exists but is not completed |
| 500 | Unexpected internal error |

### 200 Response

```json
{
  "jobId":        "uuid",
  "status":       "completed",
  "title":        "string",
  "description":  "string",
  "hashtags":     ["#tag"],
  "videoUrl":     "/webhook/videos/download?jobId=uuid&asset=video",
  "downloadUrl":  "/webhook/videos/download?jobId=uuid&asset=video&download=true",
  "thumbnailUrl": "/webhook/videos/download?jobId=uuid&asset=thumbnail",
  "captionsUrl":  "/webhook/videos/download?jobId=uuid&asset=captions",
  "script":       { },
  "scenes": [ <safe_scene> ]
}
```

### Safe Scene Fields

Only these fields are returned — no `local_image_path`, `image_url`, `image_prompt`, or filesystem paths:

| Field | Type | Source Column |
|-------|------|-------------|
| sceneIndex | int | `scene_index` |
| narration | string | `narration` |
| caption | string | `caption` |
| durationSeconds | number | `duration_seconds` |
| motion | string | `motion` |
| transition | string | `transition` |
| generationStatus | string | `generation_status` |

### 404 Response

```json
{ "found": false, "error": "Job not found" }
```

### 409 Response

```json
{ "jobId": "uuid", "status": "current_status", "progress": 0, "currentStep": "current_step", "error": "Video not yet completed" }
```

### 500 Response

```json
{ "error": "Internal server error" }
```

The 500 branch is a real connection path through `Valid Input? → Format 500 → Return 500`. Error messages never expose Supabase response data, environment variables, or filesystem paths.

All download URLs use relative paths — the frontend must prepend the appropriate origin. Authentication is via `X-Internal-Api-Key` header (never in URL query string).

## Authenticated Download — `GET /webhook/videos/download?jobId={uuid}&asset={type}`

Returns the file with correct MIME type and Content-Disposition.

| asset | filename | MIME |
|-------|----------|------|
| video | final.mp4 | video/mp4 |
| thumbnail | thumbnail.jpg | image/jpeg |
| captions | captions.ass | text/plain |

### Response Codes

| Code | Condition |
|------|-----------|
| 200 | File returned with binary stream |
| 400 | Invalid UUID, asset type, or path traversal detected |
| 401 | Missing or invalid `X-Internal-Api-Key` header |
| 404 | Job not found or file not found |

### Error Responses

- **400**: `{ "error": "Invalid job UUID" | "Invalid asset type..." | "path traversal rejected" }`
- **401**: `{ "error": "Invalid or missing API key" }`
- **404**: `{ "error": "Job not found" | "File not found: ..." }`

Authentication: `X-Internal-Api-Key` header matching `INTERNAL_API_KEY`.

### Browser Video Playback — Required Proxy

A browser `<video>` element **cannot** attach the `X-Internal-Api-Key` header to its `src` request. The frontend **must not** use the n8n download URL directly for video preview.

Instead, all asset downloads must go through a **server-side Next.js API route**:

```
Browser <video src="/api/video/proxy?jobId=...&asset=video">
  → Next.js server route handler
    → adds X-Internal-Api-Key header
      → n8n WF15 GET /webhook/videos/download
        → streams binary response
  → Next.js proxy streams response back to browser
```

### Next.js Route Handler (`app/api/video/proxy/route.ts`)

```ts
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const n8nUrl = new URL('http://clipcraft-n8n:5678/webhook/videos/download');
  n8nUrl.search = searchParams.toString();
  const res = await fetch(n8nUrl.toString(), {
    headers: { 'X-Internal-Api-Key': process.env.INTERNAL_API_KEY ?? '' },
  });
  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: {
      'Content-Type': res.headers.get('Content-Type') ?? 'application/octet-stream',
      'Content-Disposition': res.headers.get('Content-Disposition') ?? '',
      'Content-Length': res.headers.get('Content-Length') ?? '',
    },
  });
}
```

The Next.js route converts the relative WF11 download URLs (e.g., `/webhook/videos/download?jobId=x&asset=video`) into frontend-safe proxy URLs (`/api/video/proxy?jobId=x&asset=video`) that include the authentication header server-side.

## TTS

Service: `clipcraft-tts:8000`
POST `/tts` — `{ "text": "...", "voice": "af_heart", "language": "en" }`
Response: binary WAV audio

Backends (in order):
1. **Kokoro** — local neural TTS (primary)
2. **Piper** — local ONNX TTS (fallback)
3. If both fail, returns 500 error

Never uses gTTS, ElevenLabs, or any cloud TTS service.

## FFmpeg Render

Call: `python3 /opt/video-tools/render_video.py <job-uuid>`
Output: 1080×1920, 30fps, H.264, AAC, yuv420p
Renders real scene images — never placeholder/black video.

## Internal Workflows (WF16-WF18)

Sub-workflows called via Execute Workflow node (not webhook). No public endpoints. Provider-agnostic contracts.

### WF16: Resolve Asset Paths

Input: `{ jobId: "uuid", assetType: "scene", sceneIndex?: 1..999 }`
Output: `{ success: true, localPath: "/data/jobs/...", filename: "scene-03.png", jobId, assetType }` or `{ success: false, errors: [...] }`

Validates UUID and asset type against the canonical allowlist. Never accepts a raw filename or path. Two-digit scene numbering.

### WF17: AI Generate Text

Input: `{ prompt: "...", systemPrompt?: "..." }`
Output: `{ success: true, result: "response text" }` or `{ success: false, error: "...", retryable: true/false }`

Provider-agnostic. Routes via `$env.AI_TEXT_PROVIDER`. Currently implements Cloudflare only. Normalizes response into `{ success, result }` format. Temporary failures trigger up to 2 retries.

### WF18: AI Generate Image

Input: `{ prompt: "...", job_id?: "...", scene_index?: N }`
Output: `{ success: true, imageBase64: "...", format: "png" }` or `{ success: false, error: "...", retryable: true/false }`

Provider-agnostic. Routes via `$env.AI_IMAGE_PROVIDER`. Currently implements Cloudflare only. Returns normalized base64 image. Temporary failures trigger up to 2 retries.

## AI Provider Abstraction

AI calls use WF17 (text) or WF18 (image) instead of direct HTTP calls to AI providers.

| Env Variable | Default | Description |
|---|---|---|
| `AI_TEXT_PROVIDER` | `cloudflare` | Text generation provider routing |
| `AI_IMAGE_PROVIDER` | `cloudflare` | Image generation provider routing |

Workflows call sub-workflows via Execute Workflow node, which routes based on the provider env var. When adding a new provider:
1. Add a new `else if` branch in the Build Request code node of the relevant sub-workflow
2. Set the env var to the new provider name
3. Configure the new provider's API credentials as additional env vars

Cloudflare-specific credentials always remain available for backwards compatibility. No workflow outside WF17/WF18 should contain direct Cloudflare HTTP calls.

## Environment Variables

| Variable | Service | Purpose |
|----------|---------|---------|
| AI_TEXT_PROVIDER | n8n | Text generation provider |
| AI_IMAGE_PROVIDER | n8n | Image generation provider |
| CLOUDFLARE_ACCOUNT_ID | n8n | Cloudflare account ID |
| CLOUDFLARE_AI_TOKEN | n8n | Cloudflare API token |
| CLOUDFLARE_TEXT_MODEL | n8n | Cloudflare text model |
| CLOUDFLARE_IMAGE_MODEL | n8n | Cloudflare image model |
| SUPABASE_URL | n8n | Supabase project URL |
| SUPABASE_SERVICE_ROLE_KEY | n8n | Supabase service role key |
| INTERNAL_API_KEY | n8n | Internal webhook auth |
| TTS_BASE_URL | n8n | TTS service URL (default http://clipcraft-tts:8000) |

## Security

- Secrets only in environment variables (never in workflow JSON)
- Never expose `/data/jobs/` paths in public API responses
- UUID validation on all inputs
- Path traversal rejected in renderer and download endpoint
- Error messages sanitized (strip tokens)
- Download endpoint uses hardcoded filename allowlist — never accepts arbitrary paths
- Download endpoint requires `X-Internal-Api-Key` header authentication
- `INTERNAL_API_KEY` never embedded in client-side JavaScript
