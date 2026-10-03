-- Persist the narration formatting selected when a job is created.
alter table public.video_jobs
  add column if not exists narration_export_style text not null default 'clean'
    check (narration_export_style in ('clean', 'expressive'));
