# Duration-Aware Video Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep future generated narration and rendered video within 10% of the frontend-requested duration.

**Architecture:** WF04 calculates and validates a voice-aware narration word target. WF06 measures synthesized WAV duration and permits one structured script revision. Accepted audio duration drives persisted scene timing, captions, and the render manifest.

**Tech Stack:** n8n workflows, Cloudflare text generation, local Piper TTS, ffprobe, FFmpeg.

---

### Task 1: Add Duration-Aware Script Validation

**Files:**
- Modify: live WF04 `Generate Script and Scenes` (`dWTF2UGXX3R73PDW`)

- [ ] **Step 1: Add target word count to the script prompt**

Use `194` WPM for `af_heart` and calculate:

```js
const targetWords = Math.round(Number(brief.duration) * 194 / 60);
const minWords = Math.floor(targetWords * 0.92);
const maxWords = Math.ceil(targetWords * 1.08);
```

Instruct the model to produce `fullNarration` within that inclusive range.

- [ ] **Step 2: Validate full narration word count before saving**

Reject a script when its whitespace-delimited `fullNarration` count is outside
the computed range. Persist `targetWords`, `minWords`, and `maxWords` in the
script JSON for downstream validation.

### Task 2: Validate WAV Duration and Allow One Revision

**Files:**
- Modify: live WF06 `Generate Narration` (`UhWkv3GLHVSpWrMe`)
- Modify: live WF03 `Video Job Queue Worker` (`1usjkGUZXjFpXZNU`)

- [ ] **Step 1: Measure WAV duration using ffprobe after writing narration.wav**

For requested `duration`, accept WAV duration between `duration * 0.9` and
`duration * 1.1`.

- [ ] **Step 2: Produce structured out-of-range result**

Return `requestedDuration`, `measuredDuration`, `targetWords`, `minWords`,
`maxWords`, and attempt number when out of tolerance.

- [ ] **Step 3: Route first mismatch to WF04 revision once**

WF03 invokes WF04 with the structured duration revision request, then repeats
WF06. A second mismatch produces a duration-validation error and stops.

### Task 3: Synchronize Scene Timing

**Files:**
- Modify: live WF04 `Generate Script and Scenes` (`dWTF2UGXX3R73PDW`)
- Modify: live WF07 `Build Captions` (`dNgYGCqkbwr552EW`)
- Modify: live WF08 `Build Render Manifest` (`iik8qVHvgD9xWWjI`)

- [ ] **Step 1: Allocate scene durations after accepted audio**

Allocate the accepted WAV duration in proportion to each scene narration word
count. Adjust the final scene by the rounding remainder so scene durations sum
exactly to measured audio duration.

- [ ] **Step 2: Use the persisted durations in captions and manifest**

WF07 uses `scenes.duration_seconds` for subtitle timing. WF08 uses the same
stored durations in the render manifest.

### Task 4: Verify a New 30-Second Job

**Files:**
- Test: generated job assets under `/data/jobs/{jobId}`

- [ ] **Step 1: Submit one new frontend-equivalent 30-second request**

Use the existing frontend payload shape, then wait for completion.

- [ ] **Step 2: Verify duration synchronization**

Run `ffprobe` on `narration.wav` and `final.mp4`; both must be 27-33 seconds.
Confirm manifest scene durations sum to measured audio duration.
