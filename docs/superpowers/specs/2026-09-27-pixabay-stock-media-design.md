# Pixabay Stock Media — Design Spec

Date: 2026-09-27
Status: approved (approach A: mirror Pexels)
Branch: `feature/pixabay-stock-media`

## Objective

Add Pixabay as a second stock-media visual source, selectable per video,
with full photo / video / mix parity to the existing Pexels source. No
automatic fallback between providers in this spec.

## Context

- Pexels source exists (`visual_source='pexels'`, `pexels_media_type` photo |
  video | both) with backend service `pexels_stock.py`, signed internal
  endpoint, `ClipCraftStockExecute` custom node, WF05 stock branch, and
  frontend picker.
- Pixabay key is not yet available; the user will sign up (free, instant)
  and provide it before end-to-end verification.
- Lesson from production: pace provider calls, honor 429 with backoff, never
  hammer (Pexels Cloudflare-block incident).

## Pixabay API facts (verified 2026-09-27)

- Free key, instant, no approval for the default tier. Auth is a `key` query
  parameter only (no header alternative; redact from all logs).
- Images: `GET https://pixabay.com/api/` — `q` (max 100 chars),
  `image_type=photo`, `orientation=vertical` for portrait, `safesearch=true`,
  `per_page` 3–200.
- Videos: `GET https://pixabay.com/api/videos/` — `q` (max 100 chars),
  `video_type=film`, `safesearch=true`, **no orientation parameter**.
  Renditions per video: large / medium / small / tiny with url, width,
  height; `medium` is always present (usually 1920x1080).
- Rate limit: 100 requests / 60 seconds **per key**. 429 body is plain text
  ("API rate limit exceeded"). Response headers carry `X-RateLimit-*`.
- Terms: cache responses 24 hours, no systematic mass downloads, show
  attribution where results are displayed, download images to our server
  (videos may be embedded, storing recommended).

## Architecture (mirror Pexels)

1. **Provider + credentials.** `provider_id='pixabay'` in the provider
   registry with `SUPPORTED_PIXABAY_MEDIA_TYPES = {'photo', 'video', 'both'}`.
   Stored-credential only, reusing the existing credential components and
   encryption. Settings UI gains a Pixabay key field.
2. **Backend.** New `pixabay_stock.py` transport beside `pexels_stock.py`:
   search → select first suitable result (prefer portrait-ish video
   renditions for portrait jobs; landscape accepted and center-cropped at
   render, same as Pexels clips) → download to the job dir as
   `scene-NN.jpg` / `scene-NN.mp4`. New signed internal endpoint following
   the existing stock endpoint pattern. Single 429 backoff using the
   provider's own guidance, then fail fast with mapped error codes.
   Unknown `media_type` values are rejected at the boundary (same contract
   as the Pexels gate).
3. **Workflow.** WF05's stock branch switches provider by `visual_source`
   (`pexels` | `pixabay`). Scene tags, media routing, manifest building,
   and subtitle timing flow unchanged. No WF04 / WF06 / WF07 / WF08 changes.
4. **Frontend.** Pixabay appears as a visual-source card with the same
   photo / video / mix picker and portrait orientation. Stored-credential
   mapping reused.
5. **Compliance.** Minimal 24-hour search-response cache (terms requirement),
   local asset storage (already the pattern), and "via Pixabay" attribution
   in video metadata. One query per scene, sequential execution only.

## Non-goals

- No Pexels↔Pixabay automatic fallback (explicitly deferred).
- No other providers in this spec (each gets its own spec).
- No changes to TTS, rendering, captions, or error-handling paths.

## Verification

- Unit tests: transport selection, input validation, 429 mapping,
  unknown-media rejection.
- Node syntax checks for touched workflow JSON.
- E2E (blocked on key): one photo video + one mix video, verified by
  manifest mix, ASS tiling, and frame checks — same gate as Pexels.
