-- AI Video Factory — Full schema
-- Contract reference: shared-contract.md
-- Run in Supabase SQL editor.

create extension if not exists pgcrypto;

-- ============================================================
-- channels
-- ============================================================
create table if not exists public.channels (
  id uuid primary key default gen_random_uuid(),
  user_id text,
  name text not null default 'Default',
  niche text,
  language text not null default 'English',
  content_style text,
  visual_style text,
  voice text,
  voice_tone text,
  caption_style text default 'bold highlighted words',
  default_duration integer not null default 60,
  default_scene_count integer not null default 12,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists channels_user_idx on public.channels(user_id);

-- ============================================================
-- chat_sessions
-- ============================================================
create table if not exists public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id text,
  channel_id uuid references public.channels(id) on delete set null,
  status text not null default 'active'
    check (status in ('active','completed','abandoned')),
  brief_json jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists chat_sessions_user_idx on public.chat_sessions(user_id);
create index if not exists chat_sessions_status_idx on public.chat_sessions(status);

-- ============================================================
-- chat_messages
-- ============================================================
create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  role text not null check (role in ('user','assistant','system')),
  content text not null,
  metadata_json jsonb,
  created_at timestamptz not null default now()
);
create index if not exists chat_messages_session_idx on public.chat_messages(session_id, created_at);

-- ============================================================
-- video_jobs
-- Statuses: queued → generating_script → script_ready →
--   generating_images → generating_voice → building_captions →
--   building_manifest → rendering → completed
-- Also: failed, cancelled
-- ============================================================
create table if not exists public.video_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id text,
  channel_id text not null default 'default',
  session_id text,
  topic text not null,
  status text not null default 'queued'
    check (status in (
      'queued','generating_script','script_ready','generating_images',
      'generating_voice','building_captions','building_manifest',
      'rendering','completed','failed','cancelled'
    )),
  progress integer not null default 0 check (progress between 0 and 100),
  current_step text not null default 'queued',
  brief_json jsonb not null default '{}'::jsonb,
  script_json jsonb,
  render_manifest jsonb,
  output_url text,
  thumbnail_url text,
  error_message text,
  retry_count integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz
);
create index if not exists video_jobs_status_created_idx on public.video_jobs(status, created_at);
create index if not exists video_jobs_user_idx on public.video_jobs(user_id);

-- ============================================================
-- scenes
-- ============================================================
create table if not exists public.scenes (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.video_jobs(id) on delete cascade,
  scene_index integer not null,
  narration text not null,
  caption text,
  image_prompt text not null,
  image_url text,
  local_image_path text,
  duration_seconds numeric(6,2) not null default 5,
  motion text not null default 'zoom_in'
    check (motion in ('zoom_in','zoom_out','pan_left','pan_right','pan_up','pan_down')),
  transition text not null default 'crossfade'
    check (transition in ('fade','crossfade','slide_left','slide_right')),
  generation_status text not null default 'pending'
    check (generation_status in ('pending','generating','completed','failed')),
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(job_id, scene_index)
);
create index if not exists scenes_job_idx on public.scenes(job_id, scene_index);

-- ============================================================
-- assets
-- Columns used by n8n: local_path, public_url, mime_type, file_size
-- ============================================================
create table if not exists public.assets (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.video_jobs(id) on delete cascade,
  scene_id uuid references public.scenes(id) on delete set null,
  asset_type text not null
    check (asset_type in ('image','audio','video','subtitle','thumbnail','other')),
  local_path text,
  public_url text,
  mime_type text,
  file_size bigint,
  created_at timestamptz not null default now()
);
create index if not exists assets_job_idx on public.assets(job_id);
create index if not exists assets_scene_idx on public.assets(scene_id);

-- ============================================================
-- updated_at trigger
-- ============================================================
create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

do $$
begin
  if not exists (select 1 from pg_trigger where tgname = 'channels_updated_at') then
    create trigger channels_updated_at before update on public.channels
      for each row execute function public.set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'chat_sessions_updated_at') then
    create trigger chat_sessions_updated_at before update on public.chat_sessions
      for each row execute function public.set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'video_jobs_updated_at') then
    create trigger video_jobs_updated_at before update on public.video_jobs
      for each row execute function public.set_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'scenes_updated_at') then
    create trigger scenes_updated_at before update on public.scenes
      for each row execute function public.set_updated_at();
  end if;
end;
$$;

-- ============================================================
-- Row-level security
-- ============================================================
-- n8n uses the service-role key, which bypasses RLS.

alter table public.channels enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;
alter table public.video_jobs enable row level security;
alter table public.scenes enable row level security;
alter table public.assets enable row level security;
