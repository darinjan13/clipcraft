# Pexels Mix + Narration Subtitles — Design

## Context

Pexels photos and clips each work end to end, but `pexels_media_type` is
exclusive (photo XOR video) and on-screen text shows the short `caption`
field rather than the spoken narration. The user chose: AI-tagged mix per
scene, and chunked narration subtitles.

## Decisions (approved)

- Approach A: AI tags each scene photo/video; subtitles chunked from
  narration with proportional timing. No alternating fallback, no
  full-scene text blocks.

## 1. Subtitle chunking (WF07)

Per scene, split `narration` into chunks of at most ~42 characters on
word boundaries. Chunk duration = scene duration × chunk words ÷ scene
words; the last chunk absorbs rounding so chunks exactly fill the scene.
Keeps the Clean style (Arial 48, MarginV 290). The `caption` field stays
in the data untouched; caption-style variants (Bold/Minimal) remain
unimplemented and out of scope.

## 2. Media tags (WF04)

The script prompt asks the model to tag every scene
`"mediaType": "photo"|"video"` by what suits it. `Validate Output`
accepts both values, defaults missing/unknown tags to `photo`, and the
tags persist inside `script_json` (no schema change: the scenes table
has no media column). WF05 reads each scene's tag from `script_json` by
scene index at prepare time. Revision loop and word-count behavior
unchanged.

## 3. Mix plumbing (backend + WF05 + frontend)

Backend accepts `pexels_media_type: 'both'` in validation, snapshot, and
brief. WF05 resolves each scene's tag from `script_json` by scene index
and passes it as the stock call's media type when the job is `both`,
otherwise the job-level type; Record/Update already key off the
returned media type and need no changes. Frontend adds a "Mix photos &
videos" option. Renderer and manifest already branch per scene and need
no changes.

## 4. Error handling

Missing/invalid tags default to photo (never fail the job on tagging).
Empty narration keeps failing closed via the existing content-revision
loop. Pexels per-scene failures keep the existing fail-closed behavior
with scene + query in the message.

## 5. Testing

Backend: `both` accepted end to end in validation/snapshot/brief tests.
WF07: chunking unit coverage (word boundaries, durations sum exactly to
scene duration, last-chunk rounding) plus full-suite green except the two
known pre-existing failures. No network in tests.

## 6. Verification gate (in order)

1. Full E2E video on `both`: manifest contains at least one photo scene
   and one clip scene.
2. Subtitle events cover the full narration with one chunk visible per
   check, timing proportional; frame check shows a mid-narration phrase
   (not the old short caption).
3. Rendered mix plays: still segments and motion segments interleaved,
   narration-only audio.

## Out of scope

Caption-style variants, word-exact karaoke timing, AI fallback per
scene, changes to Cloudflare/NVIDIA/Gemini behavior.
