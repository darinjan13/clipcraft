# Pexels Stock Media (Photos + Clips) — Design

## Context

Cloudflare Workers AI free quota is exhausted and Gemini image generation
needs billing, so AI scene images are blocked. The user has a free Pexels
API key and chose full photos + video clips with per-scene AI search terms.

Hooks already present: registry `pexels` entry (`implemented=False`),
`PexelsAdapter` (`stock_media` + connection test), executor
`stock_media` matching with `model_id=None`, credential resolution and
stored-credential branches for pexels, frontend draft fields
(`visual_source`, `pexels_media_type`, `pexels_orientation`) with the
option currently disabled, and backend draft/preference validation for
those fields. Connection test (`test_pexels`) already works.

## Decisions (approved)

- Approach A: photos and clips in one cycle, per-video provider pick; no
  default switch, no fallback chains, no silent AI fallback per scene.
- Search terms: the AI-generated `imagePrompt` per scene, automatically.
- Orientation defaults to portrait (native full-bleed 9:16, no crop loss).

## 1. Architecture (4 units)

1. `PexelsStockExecution` (new backend service): searches `/v1/search`
   (photos) or `/videos/search` (clips) with the scene imagePrompt,
   `orientation=portrait`, small `per_page`; picks the first usable
   result. Photos download to the scene PNG path (existing saver flow);
   clips download the MP4 to the job dir. Auth via stored Pexels key
   through the existing credentials API (mirrors the Nvidia stored-only
   pattern; connection test already exists).
2. Registry: `pexels.implemented=True`; stock uses `model_id=None` as the
   executor already anticipates. Frontend enables the disabled Pexels
   option and maps `credential_source: 'stored'` for it (one-line mapping,
   same as Nvidia today).
3. Renderer: `render_segment` gains a clip branch — trim to scene
   duration, scale/crop to full-bleed 1080x1920 with the same cover math
   as stills, mute clip audio (narration is the soundtrack). Manifest
   scene entries carry the clip path; photo scenes flow untouched.
4. WF05: per-scene branch on `pexels_media_type` — photo path reuses
   today's save flow, clip path saves the MP4 and records it in the
   manifest. No upstream prompt changes.

## 2. Data flow

Script unchanged (imagePrompts double as queries) → WF05 per scene:
search Pexels portrait → photo ? download PNG : download MP4 → manifest
records type + path → renderer builds still segments and clip segments
uniformly → concat → captions / manifest / thumbnail unchanged. Fail
closed per scene: no usable result raises a clear error naming scene and
query.

## 3. Error handling

Existing taxonomy, no new codes where current ones fit: bad/revoked key
→ `invalid_credentials`, Pexels 429 → `rate_limited`, empty results →
`empty_response` surfaced as `PEXELS_NO_RESULT` with scene + query,
download/trim failures → `provider_error`, oversize files capped. Key
encrypted at rest, in-memory only at use, never logged.

## 4. Testing

Backend: stock search parsing (photo + video shapes, empty results,
HTTP errors normalized), download + clip trim coverage on the render
branch with small local fixtures (no network), registry availability
(unimplemented → unavailable; enabled → picker-listed), stored-key
credential resolution, WF05 branch routing. Full suite green except the
two known pre-existing credential-code failures. No network in tests;
Pexels responses use fixture-recorded shapes.

## 5. Verification gate (in order)

1. Connection test with the real key in Settings (auth + quota proof).
2. Full E2E video on Pexels photos, then frame check, per project rule.
3. Full E2E video on Pexels clips: motion verified by comparing two
   timestamps, audio confirmed narration-only. Portrait orientation
   asserted on downloaded assets in both runs.

## Out of scope

Imagen or other providers, automatic fallback chains, default-provider
switches, AI-image fallback per scene, frontend changes beyond enabling
the existing option + credential mapping, and any change to
Cloudflare/NVIDIA/Gemini behavior.
