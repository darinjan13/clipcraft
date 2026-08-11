-- ClipCraft AI - Video job events and generic failure persistence
-- Prerequisites: 001_create_all_tables.sql, 002_add_job_claiming.sql,
--                003_asset_path_functions.sql, 004_core_backend_foundation.sql

-- ============================================================
-- Append-only video job events for durable activity history
-- ============================================================

create table if not exists public.video_job_events (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.video_jobs(id) on delete cascade,
  idempotency_key text,
  stage text,
  event_type text not null,
  level text not null default 'info',
  message text not null,
  progress integer check (progress between 0 and 100),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- Ordered event retrieval
create index if not exists video_job_events_ordered_idx
  on public.video_job_events(job_id, created_at desc, id desc);

-- Idempotency deduplication for externally reported events
create unique index if not exists video_job_events_idempotency_idx
  on public.video_job_events(job_id, idempotency_key)
  where idempotency_key is not null;

-- Enforce append-only: block UPDATE and DELETE on event rows
create or replace function public.prevent_video_job_event_mutations()
returns trigger
language plpgsql
security definer set search_path = ''
as $$
begin
  raise exception 'video_job_events is append-only';
end;
$$;

drop trigger if exists video_job_events_append_only on public.video_job_events;
create trigger video_job_events_append_only
  before update or delete on public.video_job_events
  for each row execute function public.prevent_video_job_event_mutations();

-- RLS: block browser access
alter table public.video_job_events enable row level security;

revoke all on public.video_job_events from anon, authenticated;
grant select on public.video_job_events to service_role;
grant insert on public.video_job_events to service_role;

-- ============================================================
-- Sanitize error code to a safe, user-facing identifier
-- ============================================================

create or replace function public.sanitize_video_job_error_code(
  p_code text
)
returns text
language sql
immutable
as $$
  select case
    when p_code in (
      'NARRATION_WORD_COUNT_OUT_OF_RANGE',
      'NARRATION_WORD_COUNT_OUT_OF_RANGE_AFTER_REVISION',
      'NARRATION_DURATION_OUT_OF_RANGE',
      'NARRATION_DURATION_OUT_OF_RANGE_AFTER_REVISION',
      'VIDEO_GENERATION_FAILED'
    ) then p_code
    else 'VIDEO_GENERATION_FAILED'
  end;
$$;

-- ============================================================
-- Generic idempotent failure persistence
-- ============================================================

create or replace function public.persist_video_job_failure(
  p_job_id uuid,
  p_idempotency_key text,
  p_stage text,
  p_current_step text,
  p_progress integer,
  p_error_code text,
  p_user_message text,
  p_metadata jsonb default '{}'::jsonb
)
returns void
language plpgsql
security definer set search_path = ''
as $$
declare
  v_safe_code text;
  v_job_status text;
begin
  -- Validate non-empty idempotency key for duplicate suppression
  if p_idempotency_key is null or p_idempotency_key = '' then
    raise exception 'p_idempotency_key is required';
  end if;

  -- Lock the job row
  select status into v_job_status
  from public.video_jobs
  where id = p_job_id
  for update;

  if not found then
    return;
  end if;

  -- Never overwrite completed or cancelled jobs
  if v_job_status in ('completed', 'cancelled') then
    return;
  end if;

  -- Suppress duplicate failure reports via idempotency key
  if exists (
    select 1 from public.video_job_events
    where job_id = p_job_id and idempotency_key = p_idempotency_key
  ) then
    return;
  end if;

  -- Sanitize the error code
  v_safe_code := public.sanitize_video_job_error_code(p_error_code);

  -- Update canonical job fields atomically (only for non-terminal jobs)
  update public.video_jobs
  set status = 'failed',
      current_step = coalesce(p_current_step, 'failed'),
      progress = least(greatest(coalesce(p_progress, 0), 0), 99),
      error_message = coalesce(p_user_message, v_safe_code),
      last_error = v_safe_code,
      failure_class = 'runtime',
      finished_at = now(),
      updated_at = now(),
      claimed_by = null,
      claimed_at = null,
      lease_token = null,
      lease_expires_at = null,
      heartbeat_at = null
  where id = p_job_id
    and status not in ('completed', 'failed', 'cancelled');

  -- Append one terminal error event using sanitized/safe metadata
  insert into public.video_job_events (
    job_id, idempotency_key, stage, event_type, level,
    message, progress, metadata
  ) values (
    p_job_id,
    p_idempotency_key,
    p_stage,
    'job_failed',
    'error',
    coalesce(p_user_message, v_safe_code),
    least(greatest(coalesce(p_progress, 0), 0), 99),
    public.sanitize_video_job_failure_metadata(p_metadata)
  );
end;
$$;

revoke execute on function public.persist_video_job_failure from public, anon, authenticated;
grant execute on function public.persist_video_job_failure to service_role;

-- ============================================================
-- Safe metadata helper: only allowlisted keys
-- ============================================================

create or replace function public.sanitize_video_job_failure_metadata(
  p_metadata jsonb
)
returns jsonb
language sql
immutable
as $$
  select coalesce(
    (select jsonb_object_agg(key, value)
     from jsonb_each(p_metadata)
     where key in (
       'attempt', 'maximum_attempts',
       'actual_words', 'target_words', 'minimum_words', 'maximum_words',
       'measured_duration', 'minimum_duration', 'maximum_duration',
       'current', 'total',
       'provider', 'workflow', 'execution_id', 'node', 'http_status',
       'execution', 'stage', 'code',
       'failure_class', 'retryable', 'error_code',
       'workflow_id', 'stage_run_id', 'attempt_number', 'pipeline_revision'
     )),
    '{}'::jsonb
  );
$$;

-- ============================================================
-- Auto-log job stage and status transitions
-- ============================================================

create or replace function public.log_video_job_transition()
returns trigger
language plpgsql
security definer set search_path = ''
as $$
begin
  if old is null or (
    old.status is distinct from new.status
    or old.current_step is distinct from new.current_step
    or old.progress is distinct from new.progress
  ) then
    insert into public.video_job_events (
      job_id, stage, event_type, level, message, progress
    ) values (
      new.id,
      new.current_step,
      case
        when new.status = 'queued' then 'job_created'
        when new.status = 'completed' then 'job_completed'
        when new.status = 'failed' then 'job_failed'
        when new.status in ('cancelled') then 'cancelled'
        else 'stage_changed'
      end,
      case
        when new.status in ('failed', 'cancelled') then 'error'
        else 'info'
      end,
      case
        when new.status = 'queued' then 'Job created and queued.'
        when new.status = 'completed' then 'Job completed successfully.'
        when new.status = 'failed' then 'Job failed.'
        when new.status = 'cancelled' then 'Job cancelled.'
        else coalesce(new.current_step, new.status)
      end,
      new.progress
    );
  end if;
  return new;
end;
$$;

drop trigger if exists video_jobs_transition_log on public.video_jobs;
create trigger video_jobs_transition_log
  after insert or update of status, current_step, progress
  on public.video_jobs
  for each row execute function public.log_video_job_transition();
