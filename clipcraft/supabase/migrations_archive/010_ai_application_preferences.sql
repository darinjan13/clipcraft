-- ClipCraft AI - Global application preferences
-- Prerequisites: 001_create_all_tables.sql

create table if not exists public.ai_application_preferences (
  id boolean primary key default true check (id = true),
  default_text_provider text,
  default_text_model text,
  default_visual_source text,
  default_image_provider text,
  default_image_model text,
  default_pexels_media_type text,
  default_pexels_orientation text,
  updated_at timestamptz not null default now()
);

alter table public.ai_application_preferences enable row level security;
revoke all on table public.ai_application_preferences from public, anon, authenticated;
grant select, insert, update, delete on table public.ai_application_preferences to service_role;

do $$
begin
  if not exists (select 1 from pg_trigger where tgname = 'ai_application_preferences_updated_at') then
    create trigger ai_application_preferences_updated_at
      before update on public.ai_application_preferences
      for each row execute function public.set_updated_at();
  end if;
end;
$$;
