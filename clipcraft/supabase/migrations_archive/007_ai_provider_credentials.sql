-- ClipCraft AI - Global encrypted provider credentials
-- Prerequisites: 001_create_all_tables.sql

create table if not exists public.ai_provider_credentials (
  id uuid primary key default gen_random_uuid(),
  provider_id text not null unique,
  encrypted_secret text not null,
  encrypted_metadata text,
  secret_last_four text,
  enabled boolean not null default true,
  status text not null default 'configured'
    check (status in ('configured', 'disabled', 'unconfigured')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  last_tested_at timestamptz,
  last_test_status text
    check (last_test_status is null or last_test_status in ('connected', 'invalid_credentials', 'quota_exceeded', 'rate_limited', 'unavailable', 'timeout', 'not_implemented', 'configuration_error', 'provider_error')),
  last_test_error_safe text
);

alter table public.ai_provider_credentials enable row level security;

do $$
begin
  if not exists (select 1 from pg_trigger where tgname = 'ai_provider_credentials_updated_at') then
    create trigger ai_provider_credentials_updated_at
      before update on public.ai_provider_credentials
      for each row execute function public.set_updated_at();
  end if;
end;
$$;
