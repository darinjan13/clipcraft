alter table public.video_jobs
  drop constraint if exists video_jobs_status_check;

alter table public.video_jobs
  add constraint video_jobs_status_check
  check (status in (
    'queued',
    'processing',
    'generating_script',
    'script_ready',
    'generating_images',
    'generating_voice',
    'building_captions',
    'building_manifest',
    'rendering',
    'completed',
    'failed',
    'cancelled'
  ));
