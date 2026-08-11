-- ClipCraft AI - Non-secret job configuration snapshots
-- Prerequisites: 001_create_all_tables.sql

alter table public.video_jobs
  add column if not exists text_provider text,
  add column if not exists text_model text,
  add column if not exists visual_source text,
  add column if not exists image_provider text,
  add column if not exists image_model text,
  add column if not exists credential_source text,
  add column if not exists provider_configuration_version text;
