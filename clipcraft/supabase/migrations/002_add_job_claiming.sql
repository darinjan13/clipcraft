-- AI Video Factory — Atomic job claiming and retry tracking
-- Prerequisite: 001_create_all_tables.sql
-- Adds claiming columns, indexes, and the claim_next_video_job() function.

-- ============================================================
-- Add columns to video_jobs (existing data preserved)
-- ============================================================
alter table public.video_jobs
  add column if not exists priority   integer not null default 0,
  add column if not exists claimed_by text,
  add column if not exists claimed_at timestamptz,
  add column if not exists max_retries integer not null default 2,
  add column if not exists last_error text,
  add column if not exists started_at timestamptz,
  add column if not exists finished_at timestamptz;

comment on column public.video_jobs.priority      is 'Higher values are claimed first';
comment on column public.video_jobs.claimed_by    is 'Worker identity that claimed this job';
comment on column public.video_jobs.claimed_at    is 'When the job was claimed';
comment on column public.video_jobs.retry_count   is 'Number of retry attempts so far';
comment on column public.video_jobs.max_retries   is 'Maximum retry attempts before giving up';
comment on column public.video_jobs.last_error    is 'Most recent error message';
comment on column public.video_jobs.started_at    is 'When processing first started';
comment on column public.video_jobs.finished_at   is 'When processing finished (any outcome)';

-- ============================================================
-- Indexes for queue lookup
-- ============================================================
create index if not exists video_jobs_queue_idx
  on public.video_jobs(status, priority desc, created_at asc)
  where status = 'queued';

create index if not exists video_jobs_claim_idx
  on public.video_jobs(claimed_by, claimed_at)
  where claimed_by is not null;

create index if not exists video_jobs_retry_idx
  on public.video_jobs(retry_count, max_retries);

-- ============================================================
-- claim_next_video_job(worker_id text)
-- Atomically selects and claims one queued job.
-- Uses FOR UPDATE SKIP LOCKED to prevent double-claiming.
-- Prefers higher priority, then older jobs.
-- Only claims jobs where retry_count < max_retries.
-- ============================================================
create or replace function public.claim_next_video_job(worker_id text)
returns public.video_jobs
language plpgsql
as $$
declare
  claimed_job public.video_jobs;
begin
  select *
  into claimed_job
  from public.video_jobs
  where status = 'queued'
    and retry_count < max_retries
  order by priority desc, created_at asc
  limit 1
  for update skip locked;

  if not found then
    return null;
  end if;

  update public.video_jobs
  set
    status       = 'generating_script',
    current_step = 'generating_script',
    progress     = 5,
    claimed_by   = worker_id,
    claimed_at   = now(),
    started_at   = coalesce(started_at, now()),
    updated_at   = now()
  where id = claimed_job.id;

  -- Return the updated row
  select *
  into claimed_job
  from public.video_jobs
  where id = claimed_job.id;

  return claimed_job;
end;
$$;

-- ============================================================
-- Helper: increment_retry(job_id uuid, error_text text)
-- Called by the error handler when a sub-workflow fails.
-- ============================================================
create or replace function public.increment_retry(
  target_job_id uuid,
  error_text text default null
)
returns public.video_jobs
language plpgsql
as $$
declare
  updated_job public.video_jobs;
begin
  update public.video_jobs
  set
    retry_count  = retry_count + 1,
    last_error   = coalesce(error_text, last_error),
    updated_at   = now()
  where id = target_job_id
  returning * into updated_job;

  return updated_job;
end;
$$;

-- ============================================================
-- Helper: fail_job(job_id uuid, error_text text)
-- Marks a job as failed, sets finished_at.
-- ============================================================
create or replace function public.fail_job(
  target_job_id uuid,
  error_text text default null
)
returns public.video_jobs
language plpgsql
as $$
declare
  updated_job public.video_jobs;
begin
  update public.video_jobs
  set
    status       = 'failed',
    current_step = 'failed',
    progress     = case when progress < 100 then progress else 100 end,
    error_message = coalesce(error_text, error_message),
    last_error    = coalesce(error_text, last_error),
    finished_at   = now(),
    updated_at   = now()
  where id = target_job_id
  returning * into updated_job;

  return updated_job;
end;
$$;

-- ============================================================
-- Helper: handle_job_error(target_job_id uuid, error_text text)
-- Increments retry_count. If under max_retries, re-queues.
-- If at max_retries, marks as failed.
-- ============================================================
create or replace function public.handle_job_error(
  target_job_id uuid,
  error_text text default null
)
returns public.video_jobs
language plpgsql
as $$
declare
  updated_job public.video_jobs;
  current_retry integer;
  max_r integer;
begin
  select retry_count, max_retries into current_retry, max_r
  from public.video_jobs where id = target_job_id;

  if not found then
    return null;
  end if;

  if current_retry + 1 >= max_r then
    -- Exceeded max retries → fail
    update public.video_jobs
    set
      status        = 'failed',
      current_step  = 'failed',
      progress      = least(progress, 99),
      retry_count   = retry_count + 1,
      last_error    = coalesce(error_text, last_error),
      error_message = coalesce(error_text, error_message),
      claimed_by    = null,
      claimed_at    = null,
      finished_at   = now(),
      updated_at    = now()
    where id = target_job_id
    returning * into updated_job;
  else
    -- Under max retries → re-queue
    update public.video_jobs
    set
      status       = 'queued',
      current_step = 'queued',
      progress     = 0,
      retry_count  = retry_count + 1,
      last_error   = coalesce(error_text, last_error),
      claimed_by   = null,
      claimed_at   = null,
      updated_at   = now()
    where id = target_job_id
    returning * into updated_job;
  end if;

  return updated_job;
end;
$$;

-- ============================================================
-- Helper: complete_job(target_job_id uuid)
-- Marks a job as completed, sets finished_at and completed_at.
-- ============================================================
create or replace function public.complete_job(target_job_id uuid)
returns public.video_jobs
language plpgsql
as $$
declare
  updated_job public.video_jobs;
begin
  update public.video_jobs
  set
    status       = 'completed',
    progress     = 100,
    finished_at  = now(),
    completed_at = now(),
    updated_at   = now()
  where id = target_job_id
  returning * into updated_job;

  return updated_job;
end;
$$;
