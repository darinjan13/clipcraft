# Pexels Stock Media (Photos + Clips) — Design

## Context

Cloudflare Workers AI free quota is exhausted and Gemini image generation
needs billing, so AI scene images are blocked. The user has a free Pexels
API key and chose full photos + video clips with per-scene AI search terms
and per-video provider choice.

Hooks already present: registry `pexels` entry (`implemented=False`),
`PexelsAdapter` (`stock_media` + working connection test), executor
`stock_media` matching with `model_id=None`, credential resolution and
stored-credential branches for pexels, frontend draft fields
(`visual_source`, `pexels_media_type`, `pexels_orientation`) with the
option currently disabled, backend draft/preference validation for those
fields, and the `ClipCraftImageExecute` custom node (signed internal
calls, PNG/JPEG handling).

Key finding during design: the image endpoint's contract is base64-only
with PNG/JPEG validation, so clips (MP4) cannot flow through it, and the
custom image node only forwards its declared properties. A dedicated
stock path is required.

## Decisions (approved)

- Approach A: photos and clips in one cycle, per-video provider pick; no
  default switch, no fallback chains, no silent AI fallback per scene.
- Search terms: the AI-generated `imagePrompt` per scene, automatically.
- Orientation defaults to portrait (native full-bleed 9:16, no crop loss).

## 1. Architecture (5 units)

1. Backend stock service + new hidden endpoint `POST
   /internal/ai/stock/execute` (same HMAC auth pattern as the image
   endpoint). It searches Pexels, downloads, and saves directly to
   `/data/jobs/{job}/` (shared volume), returning only metadata — no
   multi-megabyte base64 through n8n. Photos → `scene-XX.jpg`, clips →
   `scene-XX.mp4`.
2. New custom n8n node `ClipCraftStockExecute`: sends job / scene /
   media-type / orientation / query signed, returns saved-file metadata.
   Requires rebuilding the custom-nodes package + n8n image and
   recreating the container (DB volume persists; this rebuild has been
   done before).
3. Registry `pexels.implemented=True` (no models — the executor's
   `stock_media`/None path already anticipates this); stored-key
   credential via the existing credentials API; frontend enables the
   existing option with the stored-credential mapping (one line, same as
   Nvidia).
4. DB migration: nullable `scenes.local_clip_path` so clips are tracked
   like images.
5. Renderer: `render_segment` gains a clip branch — trim to scene
   duration, scale/crop to full-bleed 1080x1920 with the same cover math
   as stills, mute clip audio (narration is the soundtrack). WF05 branches
   per scene on `pexels_media_type`; WF08 manifest carries image or clip
   path per scene. Upstream prompts unchanged.

## 2. Data flow

Script unchanged (imagePrompts double as queries) → WF05 per scene:
pexels ? stock node (search portrait → save file server-side) : existing
AI flow → record path by media type → asset row → manifest records type
+ path → renderer builds still segments and clip segments uniformly →
concat → captions / manifest / thumbnail unchanged. Fail closed per
scene: no usable result raises `PEXELS_NO_RESULT` naming scene + query.

## 3. Error handling

Existing taxonomy, no new codes where current ones fit: bad/revoked key
→ `invalid_credentials`, Pexels 429 → `rate_limited`, empty results →
`empty_response` surfaced as `PEXELS_NO_RESULT` with scene + query,
download over cap or trim failure → `provider_error`, oversize guard on
downloads (clips get a bigger cap than the 4MB image one). Key encrypted
at rest, in-memory only at use, never logged.

## 4. Testing

Backend: stock search parsing (photo + video shapes, empty results,
HTTP errors normalized), download caps enforced, stock endpoint auth +
contract (mirroring the image-endpoint signed-request tests), registry
availability flip, stored-key credential resolution. Custom node: unit
tests for request building, response mapping, and error mapping
(mirroring the image-node test file). Renderer: clip branch on a local
ffmpeg-generated fixture (no network). Workflow JSON: structural
assertions on the new branch wiring. Full suite green except the two
known pre-existing credential-code failures. No network in tests;
Pexels responses use fixture-recorded shapes.

## 5. Verification gate (in order)

1. Migration applied + column confirmed live.
2. Connection test with the real key in Settings (auth + quota proof).
3. Full E2E video on Pexels photos, then frame check, per project rule.
4. Full E2E video on Pexels clips: motion verified by comparing two
   timestamps, audio confirmed narration-only. Portrait orientation
   asserted on saved assets in both runs.

## Out of scope

Imagen or other providers, automatic fallback chains, default-provider
switches, AI-image fallback per scene, frontend changes beyond enabling
the existing option + credential mapping, and any change to
Cloudflare/NVIDIA/Gemini behavior.
