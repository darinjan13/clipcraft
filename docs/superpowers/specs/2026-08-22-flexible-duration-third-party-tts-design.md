# Flexible Duration and Third-Party TTS Design

## Scope

Keep the existing ClipCraft UI and Phase 8 pipeline. Add a pre-generation voice-source choice, persist a clean or expressive narration-export preference for Third-Party TTS jobs, and replace Automatic mode's exact word-count contract with a configurable estimated-duration range.

## Product Flow

The Generate form keeps its current layout and settings. `Voice Source` is selected before submission:

- `Automatic`: retain the configured local TTS voice controls. The duration picker represents a minimum; helper text states that the final duration may be slightly longer depending on narration.
- `Third-Party TTS`: persist `audio_mode=custom_audio`; hide automatic-only voice controls and show `Narration Export Style` with `clean` as the default and `expressive` as the alternative.

The primary action remains Generate. Automatic jobs proceed normally. Third-Party jobs generate and persist the script, enter `awaiting_audio`, export narration, accept an uploaded WAV/MP3, and resume from image generation.

## Data Model and Export Boundary

Add `narration_export_style` to `video_jobs`, constrained to `clean|expressive` and defaulting to `clean`. Add it to the API draft, job projection, creation snapshot/copy behavior, and the generation brief only where workflow access requires it.

Canonical `script_json.scenes[].narration` remains provider-neutral spoken text. Add optional scene-level `delivery` metadata only when the generated scene supplies a supported, meaningful delivery cue. The narration exporter is a backend boundary:

- Clean joins canonical scene narration in order with no metadata.
- Expressive preserves that spoken text and adds a sparse, generic bracketed delivery cue only for valid scene-level delivery metadata.

No provider-specific ElevenLabs syntax, SSML, image prompts, JSON, or internal diagnostics is exported.

## Automatic Duration Contract

One shared configuration maps the selected minimum duration to an inclusive estimated-duration range: `30: 30-45`, `45: 45-65`, `60: 60-85`, and `90: 90-120` seconds. WF04 estimates spoken duration from narration words and calibrated voice WPM. It keeps word count as a diagnostic, validates JSON/schema/image prompts/repetition, permits a reasonable scene-count range, and accepts narration when the estimate is within its configured range.

The initial response plus at most two duration revisions are permitted. A third invalid response finalizes the job immediately with `NARRATION_DURATION_OUT_OF_RANGE` and safe duration diagnostics. No fourth model request, truncation, filler, or lease-expiry failure is allowed.

WF04 normalizes accepted scene durations deterministically only after acceptance, based on the estimated duration rather than an exact requested duration.

## Timing Authority

Automatic WF06 probes raw local-TTS audio. That duration becomes `effective_duration` when it is within the configured range. A verified duration within 0.5 seconds below the selected minimum is treated as materially at the minimum, preserving the actual verified duration without overstating it. If it is materially below the selected minimum, existing safe correction is used only as needed to reach that minimum. If it is above the maximum, correction is allowed only within the documented safe tempo threshold and the verified result must remain at or below the maximum; otherwise WF06 fails with a duration error. The corrected/probed duration is persisted and drives scene timing, captions, manifest, and render timeline.

Third-Party uploaded audio remains authoritative, is never duration-gated or time-stretched by the Automatic contract, and continues to drive `effective_duration`.

## Existing Workflow Synchronization

The active WF06 (`UhWkv3GLHVSpWrMe`) is operationally identical to the repository export after removing deployment metadata. The repository keeps its normal inactive, ID-free export convention. No synchronization content change is needed; focused WF06 contract tests establish parity before new behavior is added.

## Verification

Tests cover duration ranges, exactly two revisions, no fourth request, safe failure diagnostics, exporter output, pre-generation persistence and copy behavior, API narration downloads, frontend states, and existing custom-audio contracts. A public API Automatic sample must complete before release. Disposable Third-Party API jobs must reach `awaiting_audio`, return clean and expressive text, and be hard-deleted through the public API.
