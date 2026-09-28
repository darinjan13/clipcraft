# Scene Transitions — Design Spec

Date: 2026-09-27
Status: approved (single-pass xfade chain)
Branch: `feature/scene-transitions`

## Objective

Make scene transitions actually render (today the renderer concatenates
with hard cuts and ignores the manifest `transition` field), and add one
new transition: blur dissolve.

## Facts (verified 2026-09-27)

- `render_video.py` joins per-scene segments with `concat -c copy`; no
  `xfade` anywhere. `transition` is validated (`fade`, `crossfade`,
  `slide_left`, `slide_right`) but never applied.
- WF04 emits free-form values (`crossfade`, `Fade`, `Cut`,
  `Fade to black`) — some outside the allowed set.
- video-tools is bind-mounted live; renderer changes need no rebuild.
- Narration audio is fixed-length; video total must equal it exactly
  (subtitle timing depends on it).

## Architecture (single-pass xfade chain)

1. **Renderer.** Normalize every segment (1080x1920, 30fps, yuv420p),
   chain ffmpeg `xfade` per scene boundary: `fade`, `dissolve`
   (= crossfade), `slideleft` / `slideright`, `hblur` (= blur dissolve,
   with `dissolve` fallback if the container ffmpeg lacks it — verify via
   `ffmpeg -h filter=xfade` before finalizing). One pass, uniform across
   photo/clip mixes.
2. **Duration compensation (renderer-internal).** Each xfade overlaps
   scenes by a constant 0.5s; the renderer extends scene visuals by the
   overlap so total video length still equals the narration length.
   Manifest durations and ASS timing are untouched.
3. **Constrained vocabulary.** WF04 Build Prompt lists exactly the 5 names
   (`fade`, `crossfade`, `slide_left`, `slide_right`, `blur_dissolve`).
   Renderer maps any other value to `crossfade` (never fail a render on
   a transition name). `ALLOWED_TRANSITIONS` gains `blur_dissolve` in
   `build_filters.py` and `validate_manifest.py`.

## Non-goals

- No per-video transition picker UI; AI chooses per scene as today.
- No variable transition durations (constant 0.5s).
- No cross-provider or audio-transition changes.

## Verification

- `render-test.sh` extended with all 5 transitions; frame extracted
  mid-transition proves each effect is visible (not a hard cut).
- One full E2E video (source chosen at runtime based on provider health):
  A/V durations match, all scenes present, transitions visible between
  scenes. Finished product or it does not count.
