-- ClipCraft AI - Soft delete for video jobs
-- Prerequisites: 001_create_all_tables.sql

alter table public.video_jobs
  add column if not exists deleted_at timestamptz;

create index if not exists video_jobs_active_idx
  on public.video_jobs(id)
  where deleted_at is null;
