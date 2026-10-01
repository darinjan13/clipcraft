# Background Music (Phase 1: Local Library + Manual Pick) — Design Spec

Date: 2026-10-01
Status: approved (approach A, manual picker for story + creative)
Branch: `feature/background-music`

## Objective

Play a user-supplied music bed under the narration at a fixed low level.
Phase 1 covers local MP3 uploads + manual per-video picking for both
story and creative modes. AI-picked tracks arrive with the music-API
phase (separate spec).

## Context

- The `clipcraft_music` volume exists and is mounted but empty.
- Narration quality verdict (separate): the lousiness is the Piper
  `lessac-medium` voice itself (24kHz mono, flat prosody) plus broadcast
  loudnorm squash — a music bed masks some of this but does not fix the
  voice. Voice swap stays a separate decision.
- Render mux today: narration → loudnorm → AAC. Music joins before
  loudnorm so one mastering pass covers the mix.

## Design

1. **Library.** Settings page gains a music section: upload MP3/WAV
   (capped size, ffprobe-verified duration), list with durations, delete.
   Files persist in the music volume; metadata recorded alongside.
2. **Picker.** Generate form gains a music selector for BOTH modes:
   "No music" (default) or any uploaded track. Stored per video in the
   brief (`musicTrack`). No mood automation in this phase.
3. **Render mix.** The chosen track is trimmed/looped to narration
   length, mixed at a fixed low bed (~-22dB under voice) with short
   fade in/out, then the existing loudnorm + AAC chain masters the mix.
   Voice dominance is structural, not tuned per video.
4. **Phase 2 (separate spec):** music-API search as another library
   source + AI mood picking.

## Non-goals

- No ducking (constant bed only, per approved choice).
- No per-scene music changes or volume automation.
- No API integration in this phase.
- No voice-model change.

## Verification

- Unit: mix level math, loop/trim logic, upload validation.
- E2E: one video with an uploaded horror track → final MP4 contains
  two audio sources at the intended balance; one "No music" video
  renders exactly as before.
