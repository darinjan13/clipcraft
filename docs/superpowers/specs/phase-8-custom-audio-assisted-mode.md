# Phase 8: Custom Audio / Assisted Voice Mode - Implementation Design

**Baseline**: v0.2.0-pipeline-stable  
**Status**: DESIGN ONLY - No implementation yet

---

## 1. Current Pipeline Summary

### Automatic Path (Current Behavior - Preserved)
```
Frontend Generate → POST /api/videos → Job queued
  → WF03 Queue Worker claims job
  → WF04 Generate Script (WF04) → status: script_ready
  → WF05 Generate Images → status: generating_images
  → WF06 Generate Narration (ClipCraft TTS) → status: generating_voice
  → WF07 Build Captions → status: building_captions
  → WF08 Build Manifest → status: building_manifest
  → WF09 Render → status: rendering
  → Completed
```

### Job Status Flow (Current)
```
queued → generating_script → script_ready → generating_images 
  → generating_voice → building_captions → building_manifest 
  → rendering → completed
```

---

## 2. Proposed Design

### Automatic Path (Unchanged)
Same as current - no user interaction required.

### Custom Audio Path (New)
```
Frontend Generate (voice_source=custom_audio) → POST /api/videos → Job queued
  → WF03 Queue Worker claims job
  → WF04 Generate Script → status: script_ready
  → **PAUSE: status: awaiting_audio** ← Job waits for user
  → Frontend shows narration.txt + upload UI
  → User downloads narration.txt, generates audio externally
  → User uploads MP3/WAV via POST /api/videos/{id}/audio
  → Backend validates audio, stores in job directory
  → User clicks "Continue Generation"
  → POST /api/videos/{id}/resume
  → Job status: resuming
  → WF03 re-claims job → WF06 (custom branch) → status: generating_voice
  → WF07 → WF08 → WF09 → Completed
```

---

## 3. Database Changes

### Migration Required: YES

**File**: `clipcraft/supabase/migrations/XXXX_custom_audio_mode.sql`

```sql
-- Add audio mode and custom audio fields to video_jobs
alter table public.video_jobs
  add column if not exists audio_mode text not null default 'automatic'
    check (audio_mode in ('automatic', 'custom_audio')),
  add column if not exists uploaded_audio_duration numeric(6,2),
  add column if not exists uploaded_audio_path text,
  add column if not exists uploaded_audio_mime_type text,
  add column if not exists uploaded_audio_file_size bigint;

-- Index for jobs awaiting audio
create index if not exists video_jobs_awaiting_audio_idx
  on public.video_jobs(id) where audio_mode = 'custom_audio' and status = 'awaiting_audio';

-- Add 'awaiting_audio' to status check constraint
alter table public.video_jobs
  drop constraint if exists video_jobs_status_check,
  add constraint video_jobs_status_check check (status in (
    'queued','generating_script','script_ready','awaiting_audio',
    'generating_images','generating_voice','building_captions',
    'building_manifest','rendering','completed','failed','cancelled'
  ));

-- Add 'narration_custom' asset type for uploaded audio
alter table public.assets
  drop constraint if exists assets_asset_type_check,
  add constraint assets_asset_type_check check (asset_type in (
    'image','audio','video','subtitle','thumbnail','other','narration_custom'
  ));
```

---

## 4. Backend Endpoints

### 4.1 Create Video (Extended)
**POST /api/videos** - Add `audio_mode` to VideoDraft

```typescript
// VideoDraft extended
audio_mode?: 'automatic' | 'custom_audio';  // default: 'automatic'
```

Validation: If `audio_mode === 'custom_audio'`, require `voice` field still (for reference).

### 4.2 Upload Custom Audio
**POST /api/videos/{video_id}/audio**

- **Auth**: Service-role (n8n) or user session (frontend via backend proxy)
- **Content-Type**: multipart/form-data
- **Body**: `audio` (file), `confirm` (boolean, optional - for immediate resume)

**Validation**:
1. Job exists
2. Job `audio_mode === 'custom_audio'`
3. Job `status === 'awaiting_audio'`
4. File is valid audio (ffprobe)
5. MIME type: audio/wav, audio/mpeg, audio/mp3
6. File size: ≤ 50MB
7. Duration > 0 (ffprobe)
8. Safe filename → store as `narration_custom.wav` in job directory

**Response**:
```json
{
  "ok": true,
  "job_id": "uuid",
  "uploaded_duration": 94.3,
  "target_duration": 90,
  "duration_ratio": 1.047,
  "path": "job_id/narration_custom.wav",
  "mime_type": "audio/wav",
  "file_size": 1234567
}
```

### 4.3 Resume Generation
**POST /api/videos/{video_id}/resume**

- **Auth**: Service-role or user session
- **Validation**:
  1. Job exists
  2. `audio_mode === 'custom_audio'`
  3. `status === 'awaiting_audio'`
  4. `uploaded_audio_path` is set
  4. Idempotent: if already `resuming` or past `awaiting_audio`, return current state

**Action**:
- Update job: `status = 'resuming'`, `next_stage = 'generate_voice'`
- Return job status

**Response**:
```json
{ "ok": true, "status": "resuming", "next_stage": "generate_voice" }
```

### 4.4 Get Job Status (Extended)
**GET /api/videos/{video_id}/status** - Include `audio_mode`, `uploaded_audio_duration` in response

---

## 5. Frontend Changes

### 5.1 GenerateForm.tsx
Add voice source selector before model selectors:

```tsx
// Voice Source
<label>
  <span className="mb-2 block text-xs font-medium text-white/55">Voice Source</span>
  <Select value={draft.audio_mode ?? 'automatic'} 
          onChange={(e) => setDraft({ audio_mode: e.target.value as 'automatic' | 'custom_audio' })}>
    <option value="automatic">Automatic (ClipCraft TTS)</option>
    <option value="custom_audio">Custom Audio (Upload your own)</option>
  </Select>
  <span className="mt-1.5 block text-[11px] text-white/40">
    Automatic: ClipCraft generates narration. Custom: Generate script first, then upload your own MP3/WAV (e.g., from ElevenLabs).
  </span>
</label>
```

### 5.2 GeneratePage.tsx
- Detect `status === 'awaiting_audio'` 
- Show waiting UI instead of progress spinner

### 5.3 Waiting UI Component (New)
**AwaitingAudioPanel.tsx**
```tsx
// When status === 'awaiting_audio'
<Panel>
  <h3>Script Ready - Waiting for Your Narration</h3>
  
  <div className="space-y-4">
    {/* Download narration.txt */}
    <Button variant="secondary" onClick={downloadNarrationTxt}>
      Download Narration Text
    </Button>
    
    {/* Upload Audio */}
    <div>
      <label className="block text-xs font-medium text-white/55 mb-2">
        Upload Narration (MP3/WAV)
      </label>
      <input type="file" accept="audio/wav,audio/mpeg,audio/mp3" 
             onChange={handleFileSelect} disabled={uploading} />
      {selectedFile && (
        <div className="mt-2 text-xs text-white/70">
          {selectedFile.name} • {formatBytes(selectedFile.size)}
        </div>
      )}
    </div>
    
    {/* Uploaded Audio Info */}
    {uploadedAudio && (
      <div className="p-3 rounded-lg border border-white/10 bg-black/20">
        <p className="text-xs text-white/55">Uploaded Audio</p>
        <p className="font-mono text-white">{uploadedAudio.filename}</p>
        <p className="text-xs text-white/60">
          Duration: {uploadedAudio.duration}s (target: {targetDuration}s) • 
          Ratio: {uploadedAudio.ratio.toFixed(1)}x
        </p>
      </div>
    )}
    
    {/* Continue Generation */}
    <Button type="button" 
            onClick={handleContinue} 
            disabled={!uploadedAudio || continuing}
            loading={continuing}>
      Continue Generation
    </Button>
  </div>
</Panel>
```

### 5.4 GenerationProgress.tsx
- Handle `awaiting_audio` state
- Show `AwaitingAudioPanel` instead of progress spinner

---

## 6. WF03 Changes (Video Job Worker)

### Claim Logic Update
When claiming a job, check `audio_mode`:

```javascript
// In WF03 after claiming job
if (job.audio_mode === 'custom_audio' && job.status === 'awaiting_audio') {
  // Job is waiting for user - do NOT process, release lease immediately
  await release_video_job(...);
  continue; // poll next job
}
```

### Resume Trigger
When `POST /api/videos/{id}/resume` is called:
- Job status becomes `resuming`
- `next_stage` set to `generate_voice`
- WF03 will claim and process normally

---

## 7. WF04 Changes (Generate Script)

### No Logic Changes
- Script generation unchanged
- After "Save Script" node, add conditional branch:
  - If `audio_mode === 'custom_audio'`:
    - Update job: `status = 'awaiting_audio'`, `next_stage = 'generate_voice'`
    - Release lease
    - End workflow (job waits for user)
  - Else (automatic):
    - Continue to WF05 (existing behavior)

### New Node: "Check Audio Mode"
After "Save Script" → IF node checking `audio_mode`:
- **custom_audio**: Set `status = awaiting_audio`, release lease, stop
- **automatic**: Continue to "Insert Scenes" → trigger WF05

---

## 8. WF05 Changes (Generate Images)

### No Changes Required
- Triggered after script ready (automatic path)
- For custom_audio: triggered after resume

---

## 9. WF06 Changes (Generate Narration)

### New Branch: Custom Audio
**Trigger**: WF06 triggered by WF03 after resume (or automatically for automatic mode)

**New Node: "Check Audio Mode"** (first node after trigger)
```javascript
// IF audio_mode === 'custom_audio' && uploaded_audio_path exists
//   → Branch: Use Uploaded Audio
// Else
//   → Branch: Automatic TTS (existing flow)
```

### Branch: Use Uploaded Audio
1. **Validate Uploaded Audio** (re-validate with ffprobe)
2. **Copy to standard path**: `job_id/narration.wav` (overwrite if needed)
3. **Measure Duration** (ffprobe) → `uploaded_audio_duration`
4. **Skip TTS Call** - audio already available
4. **Correct Audio Duration** (existing node, uses uploaded duration as authoritative)
5. **Save Audio File** → assets table as `narration_custom`
6. Continue to WF07

### Branch: Automatic TTS (Existing)
- Unchanged - uses ClipCraft TTS

---

## 10. WF07 / Caption Changes

### Proportional Timing Mapping
For custom audio, scene durations must adapt to uploaded audio duration:

```javascript
// In WF07 (Build Captions) or WF08 (Build Manifest)
// After receiving uploaded_audio_duration:
const ratio = uploaded_audio_duration / requested_duration;

// Scale all scene durations proportionally
scenes.forEach(scene => {
  scene.duration_seconds = Math.round(scene.duration_seconds * ratio * 100) / 100;
});

// Renormalize to sum exactly to uploaded_audio_duration (largest-remainder)
```

**Caption Timing**: Use proportional mapping from script timing to actual audio timing.
- Initial version: Simple proportional scaling
- Limitation: No word-level alignment (acceptable for MVP)

---

## 11. Manifest / Render Changes

### Manifest Duration
- Use `uploaded_audio_duration` as authoritative
- `manifest.duration = uploaded_audio_duration`
- All scene durations already normalized

### Renderer
- Use manifest duration for video length
- No changes to renderer logic

---

## 12. Pause-State Contract

### State: `awaiting_audio`
- **Job status**: `awaiting_audio`
- **Lease**: RELEASED (no active worker)
- **Reaper**: IGNORES jobs with `audio_mode = 'custom_audio' AND status = 'awaiting_audio'`
- **Resumable after**: Browser refresh, backend restart, n8n restart, PC reboot
- **Lease**: None held while waiting

### Reaper Exclusion
```sql
-- In reap_expired_video_job_leases
where lease_token is not null 
  and lease_expires_at <= now() 
  and status not in ('completed','failed','cancelled')
  and NOT (audio_mode = 'custom_audio' and status = 'awaiting_audio')
```

---

## 12. Resume Contract

### Endpoint: POST /api/videos/{id}/resume
- **Idempotent**: Safe to call multiple times
- **Fenced**: Uses job's current `lease_token`/`attempt_number` (even if null, uses DB row lock)
- **State Transition**: `awaiting_audio` → `resuming` → `generating_voice`
- **Next Stage**: `generate_voice`

### Idempotency
```sql
-- In resume endpoint
update video_jobs 
set status = 'resuming', next_stage = 'generate_voice', updated_at = now()
where id = $1 
  and audio_mode = 'custom_audio' 
  and status = 'awaiting_audio'
  and uploaded_audio_path is not null
returning *;
```

---

## 13. Audio Validation Contract

### POST /api/videos/{id}/audio
**Accept**: WAV, MP3 (audio/wav, audio/mpeg, audio/mp3)
**Max Size**: 50MB
**Validation**:
1. `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1`
2. Duration > 0
3. MIME type matches
3. File saved as `{job_id}/narration_custom.wav` (converted to WAV if MP3)
4. Database: `uploaded_audio_path`, `uploaded_audio_duration`, `uploaded_audio_mime_type`, `uploaded_audio_file_size`

---

## 13. Duration/Timing Contract

### Custom Audio Mode
- **Authoritative Duration**: `uploaded_audio_duration` (measured by ffprobe)
- **Scene Durations**: Proportionally scaled from script durations
- **Scene Sum**: Normalized to exactly `uploaded_audio_duration` (largest-remainder)
- **Manifest Duration**: `uploaded_audio_duration`
- **Render Duration**: Matches manifest

### Automatic Mode (Unchanged)
- Requested duration → TTS → `Correct Audio Duration` (atempo correction)
- Scene durations sum to requested duration

---

## 14. Files/Workflows Requiring Modification

### Database
- [ ] `clipcraft/supabase/migrations/XXXX_custom_audio_mode.sql`

### Backend
- [ ] `backend/app/main.py` - Add endpoints, extend VideoDraft
- [ ] `backend/app/services/internal_text_execution.py` - (if needed)

### Workflows (n8n)
- [ ] `clipcraft/workflows/03-video-job-worker.json` - Skip awaiting_audio jobs
- [ ] `clipcraft/workflows/04-generate-script-and-scenes.json` - Pause at awaiting_audio
- [ ] `clipcraft/workflows/06-generate-narration.json` - Custom audio branch

### Frontend
- [ ] `frontend/src/features/generate/components/GenerateForm.tsx` - Voice source selector
- [ ] `frontend/src/features/generate/pages/GeneratePage.tsx` - Awaiting audio handling
- [ ] `frontend/src/features/generate/components/GenerationProgress.tsx` - Awaiting audio state
- [ ] `frontend/src/features/generate/components/AwaitingAudioPanel.tsx` (NEW)
- [ ] `frontend/src/features/videos/types.ts` - Add audio_mode, uploaded_audio_*

### Tests
- [ ] Backend: Audio upload validation, resume idempotency
- [ ] Frontend: Awaiting audio UI, upload flow
- [ ] Integration: Custom audio full pipeline

---

## 15. Main Risks

| Risk | Mitigation |
|------|------------|
| Reaper consumes awaiting_audio jobs | Exclude in reaper SQL |
| Lease lost while waiting | Release lease at pause, no lease held |
| User never uploads audio | Job stays awaiting_audio indefinitely (manual cleanup or TTL) |
| Audio duration mismatch | Proportional scaling, document limitation |
| Duplicate resume clicks | Idempotent resume endpoint |
| MP3 upload → needs WAV | Convert on upload via ffmpeg |
| Large audio files | 50MB limit, ffprobe before full read |

---

## 16. Minimal Implementation Sequence

1. **Database Migration** - Add columns, constraints, indexes
2. **Backend Endpoints** - Upload audio, resume, extend create video
3. **WF03** - Skip awaiting_audio jobs, handle resume
4. **WF04** - Pause at awaiting_audio for custom_audio
5. **WF06** - Custom audio branch (skip TTS, use uploaded)
6. **WF07/WF08** - Proportional duration scaling
7. **Frontend** - Voice source selector, awaiting audio UI, upload/resume
8. **Tests** - Unit + integration

---

## 17. Tests Required

### Unit Tests
- [ ] Audio upload validation (valid/invalid formats, size, duration)
- [ ] Resume endpoint idempotency
- [ ] Reaper exclusion for awaiting_audio
- [ ] Duration proportional scaling logic

### Integration Tests
- [ ] Automatic mode: full pipeline unchanged
- [ ] Custom audio: script → pause → upload → resume → complete
- [ ] Replacement audio before resume
- [ ] Browser refresh during pause
- [ ] Backend restart during pause
- [ ] Invalid audio upload rejection

### Frontend Tests
- [ ] Voice source selector toggles
- [ ] Awaiting audio panel renders correctly
- [ ] Upload → validation → continue flow
- [ ] Download narration.txt

---

## 18. Design Document Location

**Path**: `docs/superpowers/specs/phase-8-custom-audio-assisted-mode.md`

---

*This design preserves the existing automatic pipeline exactly while adding an optional, safe custom audio path with proper pause/resume semantics.*