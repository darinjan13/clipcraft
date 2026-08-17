-- Phase 8: Custom Audio / Assisted Voice Mode
-- Minimal schema changes for custom audio mode support

-- 1. Add audio_mode column to distinguish automatic vs custom audio
alter table public.video_jobs
  add column if not exists audio_mode text not null default 'automatic'
    check (audio_mode in ('automatic', 'custom_audio'));

-- 2. Store effective duration for custom audio mode (authoritative duration from uploaded audio)
-- This is only populated for custom_audio mode; for automatic mode it remains null
alter table public.video_jobs
  add column if not exists effective_duration numeric(6,2);

-- 3. Add 'awaiting_audio' to status CHECK constraint
alter table public.video_jobs
  drop constraint if exists video_jobs_status_check;

alter table public.video_jobs
  add constraint video_jobs_status_check check (status in (
    'queued','generating_script','script_ready','awaiting_audio',
    'generating_images','generating_voice','building_captions',
    'building_manifest','rendering','completed','failed','cancelled'
  ));

-- 4. Add 'narration_custom' asset type for uploaded custom narration
alter table public.assets
  drop constraint if exists assets_asset_type_check;

alter table public.assets
  add constraint assets_asset_type_check check (asset_type in (
    'image','audio','video','subtitle','thumbnail','other','narration_custom'
  ));

-- 5. Index for jobs awaiting audio (for efficient querying)
create index if not exists video_jobs_awaiting_audio_idx
  on public.video_jobs(id) where audio_mode = 'custom_audio' and status = 'awaiting_audio';

-- 5. Update reap_expired_video_job_leases to ignore awaiting_audio jobs
-- (This will be done in a separate migration or we can update the function here)
-- For now, we'll note that the reaper function needs to be updated to exclude awaiting_audio jobs

-- Comment on new columns
comment on column public.video_jobs.audio_mode is 'Voice generation mode: automatic (ClipCraft TTS) or custom_audio (user uploads narration)';
comment on column public.video_jobs.effective_duration is 'Authoritative duration for custom_audio mode; set from uploaded audio duration; null for automatic mode';