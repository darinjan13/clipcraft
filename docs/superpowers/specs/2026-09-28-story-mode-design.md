# Paste-a-Story Mode — Design Spec

Date: 2026-09-28
Status: approved (with mode toggle)
Branch: `feature/story-mode`

## Objective

Let the user paste a full story (e.g. a horror story found manually —
no Reddit API involved) and render it as a narrated video with visuals,
instead of having the AI invent a script from a short topic.

## UX: mode toggle

The generate form gains a mode selector with two options:

- **Creative** (default, current behavior): title + short topic prompt.
  AI writes the script.
- **Story**: title + large story textarea with a live character counter
  (cap ~3,000 chars ≈ 3–4 min of narration). The topic prompt is hidden;
  all other options (voice, visual source, captions, duration guide)
  stay exactly where they are.

One form, one submit button, no duplicated controls. The draft carries
`mode: 'creative' | 'story'` plus `story_text` (story mode only).

## Pipeline

1. **Brief** carries `mode` and `storyText`. Creative mode is byte-for-byte
   today's behavior.
2. **WF04 story branch.** One text call (Gemini fallback chain applies):
   split the story into narrated scenes — narration (verbatim chunk),
   caption, image prompt, media tag, transition. Hard rule: concatenated
   narrations must equal the pasted story exactly (no rewriting, no
   trimming). Video length = story length. The duration picker is hidden
   in story mode (replaced by a live length estimate); the pipeline
   overrides requested/min/max duration from the story's word count so
   narration range checks and audio tempo correction never fight the story.
3. **WF05 visual cascade, per scene.** Each scene tries the user's chosen
   source first; on quota/rate-limit errors only, it falls back along
   Cloudflare → Pexels → Pixabay. The asset record keeps the serving
   provider (already stored). Non-quota errors fail loudly per scene.
4. **Downstream unchanged.** TTS, chunked/punctuated subtitles, manifest,
   render, and transitions consume scenes exactly as today.

## Non-goals

- No Reddit/API fetching (user pastes manually).
- No cross-provider text fallback changes (already exists).
- No quota tracking; fallback relies on per-call 429/quota signals.
- No stories over the ~3,000-char cap (split into parts instead).

## Verification

- Unit: splitter/breakdown contract (concatenation == input), cascade
  advances on quota errors only, per-scene independence.
- E2E: one pasted horror story → completed video; narration matches the
  pasted text; mixed providers allowed across scenes; subtitles tile.
