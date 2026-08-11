# Duration-Aware Video Generation

## Goal

Make future video narration, captions, scene timing, manifest timing, and final
render duration align with the frontend-selected duration.

## Measured Baseline

The completed dream video requested 30 seconds but used a 54-word
`fullNarration`. Its `af_heart` WAV lasted 16.706757 seconds, or about 194
words per minute. WF07 and WF08 used six fixed five-second scenes while WF09
trimmed the result to the shorter audio stream with `-shortest`.

## Timing Contract

- Voice: `af_heart`, measured baseline: 194 words per minute.
- Target words: `round(requestedSeconds * 194 / 60)`.
- Script word range: target words +/- 8%.
- Audio acceptance range: requested duration +/- 10%.
- A 30-second request therefore targets 97 words, accepts 89-105 script
  words, and accepts 27-33 seconds of synthesized audio.

## Bounded Revision Flow

1. WF04 prompts for and validates the target narration word range.
2. WF06 synthesizes speech and measures the WAV with `ffprobe`.
3. If audio is in range, WF06 records the measured duration and continues.
4. If audio is outside range on attempt one, WF06 returns a structured
   revision request containing requested duration, measured duration, target
   word range, and current narration text.
5. WF04 revises the script once against that request, then WF06 synthesizes
   again.
6. If attempt two is outside range, the job fails with an explicit
   duration-validation error. No unbounded retries occur.

## Synchronized Timeline

After an accepted WAV, scene durations are allocated proportionally to each
scene narration word count. WF07 captions and WF08 manifest consume those
persisted scene durations. WF09 retains `-shortest` as a safety guard but
receives matched audio and visual durations in normal operation.

## Scope

Changes apply only to future jobs. Existing completed media is not modified.
