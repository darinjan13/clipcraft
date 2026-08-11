-- Additive lease-contract reconciliation for the live legacy schema.
-- Historical rows remain unchanged. New fencing starts only at claim time.

create extension if not exists pgcrypto;

alter table public.video_jobs
  add column if not exists lease_token uuid,
  add column if not exists lease_expires_at timestamptz,
  add column if not exists heartbeat_at timestamptz,
  add column if not exists attempt_number integer,
  add column if not exists pipeline_revision integer,
  add column if not exists next_stage text,
  add column if not exists last_completed_stage text,
  add column if not exists failure_class text;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.video_jobs'::regclass
      and conname = 'video_jobs_lease_shape_check'
  ) then
    alter table public.video_jobs add constraint video_jobs_lease_shape_check check (
      (lease_token is null and lease_expires_at is null and heartbeat_at is null)
      or
      (lease_token is not null and lease_expires_at is not null and heartbeat_at is not null)
    );
  end if;
end;
$$;

create index if not exists video_jobs_fenced_queue_idx
  on public.video_jobs(priority desc, created_at asc)
  where status = 'queued' and lease_token is null and claimed_by is null and claimed_at is null;

create index if not exists video_jobs_fenced_lease_idx
  on public.video_jobs(lease_expires_at)
  where lease_token is not null;

create table if not exists public.job_stage_runs (
  id uuid primary key default pg_catalog.gen_random_uuid(),
  job_id uuid not null references public.video_jobs(id) on delete cascade,
  pipeline_revision integer not null,
  stage text not null,
  item_key text not null,
  input_hash text not null,
  status text not null default 'running',
  run_token uuid not null default pg_catalog.gen_random_uuid(),
  job_attempt_number integer not null,
  worker_id text not null,
  lease_token uuid not null,
  provider_attempt_count integer not null default 0,
  tts_attempt_count integer not null default 0,
  renderer_attempt_count integer not null default 0,
  filesystem_attempt_count integer not null default 0,
  side_effect_phase text not null default 'not_started',
  output_json jsonb,
  output_hash text,
  error_json jsonb,
  started_at timestamptz not null default now(),
  heartbeat_at timestamptz not null default now(),
  completed_at timestamptz,
  unique (job_id, pipeline_revision, stage, item_key)
);

alter table public.job_stage_runs enable row level security;
revoke all on table public.job_stage_runs from public, anon, authenticated;
grant select, insert, update, delete on table public.job_stage_runs to service_role;

create or replace function public.claim_next_video_job_fenced(
  p_worker_id text,
  p_lease_seconds integer default 120
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare
  claimed_job public.video_jobs;
begin
  if p_worker_id is null or length(trim(p_worker_id)) = 0 then
    raise exception 'INVALID_WORKER_ID';
  end if;
  if p_lease_seconds < 5 or p_lease_seconds > 900 then
    raise exception 'INVALID_LEASE_SECONDS';
  end if;

  select * into claimed_job
  from public.video_jobs
  where status = 'queued'
    and lease_token is null
    and claimed_by is null
    and claimed_at is null
  order by priority desc, created_at asc
  for update skip locked
  limit 1;

  if not found then
    return jsonb_build_object('claimed', false);
  end if;

  update public.video_jobs
  set status = 'generating_script',
      current_step = 'generating_script',
      progress = greatest(progress, 5),
      claimed_by = p_worker_id,
      claimed_at = now(),
      lease_token = pg_catalog.gen_random_uuid(),
      lease_expires_at = now() + make_interval(secs => p_lease_seconds),
      heartbeat_at = now(),
      attempt_number = coalesce(attempt_number, 0) + 1,
      pipeline_revision = coalesce(pipeline_revision, 1),
      next_stage = coalesce(next_stage, 'generate_script'),
      updated_at = now()
  where id = claimed_job.id
  returning * into claimed_job;

  return jsonb_build_object(
    'claimed', true,
    'lease_token', claimed_job.lease_token,
    'job', jsonb_build_object(
      'id', claimed_job.id,
      'topic', claimed_job.topic,
      'status', claimed_job.status,
      'progress', claimed_job.progress,
      'current_step', claimed_job.current_step,
      'brief_json', claimed_job.brief_json,
      'script_json', claimed_job.script_json,
      'render_manifest', claimed_job.render_manifest,
      'output_url', claimed_job.output_url,
      'thumbnail_url', claimed_job.thumbnail_url,
      'retry_count', claimed_job.retry_count,
      'max_retries', claimed_job.max_retries,
      'claimed_by', claimed_job.claimed_by,
      'claimed_at', claimed_job.claimed_at,
      'lease_token', claimed_job.lease_token,
      'lease_expires_at', claimed_job.lease_expires_at,
      'heartbeat_at', claimed_job.heartbeat_at,
      'attempt_number', claimed_job.attempt_number,
      'pipeline_revision', claimed_job.pipeline_revision,
      'next_stage', claimed_job.next_stage,
      'last_completed_stage', claimed_job.last_completed_stage,
      'failure_class', claimed_job.failure_class
    )
  );
end;
$$;

create or replace function public.heartbeat_video_job(
  p_job_id uuid, p_worker_id text, p_lease_token uuid,
  p_attempt_number integer, p_pipeline_revision integer,
  p_lease_seconds integer default 120
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare updated_job public.video_jobs;
begin
  if p_lease_seconds < 5 or p_lease_seconds > 900 then raise exception 'INVALID_LEASE_SECONDS'; end if;
  update public.video_jobs
  set heartbeat_at = now(), lease_expires_at = now() + make_interval(secs => p_lease_seconds), updated_at = now()
  where id = p_job_id and claimed_by = p_worker_id and lease_token = p_lease_token
    and attempt_number = p_attempt_number and pipeline_revision = p_pipeline_revision
    and status not in ('completed', 'failed', 'cancelled') and lease_expires_at > now()
  returning * into updated_job;
  if not found then raise exception 'LEASE_LOST'; end if;
  return jsonb_build_object('ok', true, 'lease_expires_at', updated_job.lease_expires_at, 'cancel_requested', false);
end;
$$;

create or replace function public.begin_job_stage(
  p_job_id uuid, p_pipeline_revision integer, p_stage text, p_item_key text,
  p_input_hash text, p_worker_id text, p_lease_token uuid, p_attempt_number integer
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare job_row public.video_jobs; stage_row public.job_stage_runs;
begin
  select * into job_row from public.video_jobs where id = p_job_id for update;
  if not found or job_row.claimed_by <> p_worker_id or job_row.lease_token <> p_lease_token
     or job_row.attempt_number <> p_attempt_number or job_row.pipeline_revision <> p_pipeline_revision
     or job_row.lease_expires_at <= now() or job_row.status in ('completed','failed','cancelled') then
    raise exception 'LEASE_LOST';
  end if;
  select * into stage_row from public.job_stage_runs
  where job_id = p_job_id and pipeline_revision = p_pipeline_revision and stage = p_stage and item_key = p_item_key
  for update;
  if found and stage_row.status = 'succeeded' then
    return jsonb_build_object('state','CACHED_SUCCESS','stage_run_id',stage_row.id,'output',stage_row.output_json);
  end if;
  if found then
    update public.job_stage_runs set status='running', run_token=pg_catalog.gen_random_uuid(), heartbeat_at=now(), error_json=null
    where id = stage_row.id returning * into stage_row;
  else
    insert into public.job_stage_runs(job_id,pipeline_revision,stage,item_key,input_hash,status,job_attempt_number,worker_id,lease_token)
    values(p_job_id,p_pipeline_revision,p_stage,p_item_key,p_input_hash,'running',p_attempt_number,p_worker_id,p_lease_token)
    returning * into stage_row;
  end if;
  return jsonb_build_object('state','STARTED','stage_run_id',stage_row.id,'run_token',stage_row.run_token);
end;
$$;

create or replace function public.reserve_stage_external_attempt(
  p_stage_run_id uuid, p_run_token uuid, p_kind text, p_limit integer,
  p_job_id uuid, p_worker_id text, p_lease_token uuid,
  p_attempt_number integer, p_pipeline_revision integer
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare stage_row public.job_stage_runs; next_attempt integer;
begin
  select * into stage_row from public.job_stage_runs where id=p_stage_run_id for update;
  if not found or stage_row.status <> 'running' or stage_row.run_token <> p_run_token
     or stage_row.job_id <> p_job_id or stage_row.worker_id <> p_worker_id
     or stage_row.lease_token <> p_lease_token or stage_row.job_attempt_number <> p_attempt_number
     or stage_row.pipeline_revision <> p_pipeline_revision then raise exception 'RUN_TOKEN_LOST'; end if;
  next_attempt := case p_kind when 'provider' then stage_row.provider_attempt_count + 1 when 'tts' then stage_row.tts_attempt_count + 1 when 'renderer' then stage_row.renderer_attempt_count + 1 when 'filesystem' then stage_row.filesystem_attempt_count + 1 else null end;
  if next_attempt is null then raise exception 'UNKNOWN_ATTEMPT_KIND'; end if;
  if next_attempt > p_limit then return jsonb_build_object('permitted',false,'attempt_number',next_attempt,'remaining',0); end if;
  update public.job_stage_runs set provider_attempt_count=case when p_kind='provider' then next_attempt else provider_attempt_count end, tts_attempt_count=case when p_kind='tts' then next_attempt else tts_attempt_count end, renderer_attempt_count=case when p_kind='renderer' then next_attempt else renderer_attempt_count end, filesystem_attempt_count=case when p_kind='filesystem' then next_attempt else filesystem_attempt_count end, side_effect_phase='reserved', heartbeat_at=now() where id=stage_row.id;
  return jsonb_build_object('permitted',true,'attempt_number',next_attempt,'remaining',p_limit-next_attempt);
end;
$$;

create or replace function public.finalize_stage_success(
  p_stage_run_id uuid, p_run_token uuid, p_job_id uuid, p_worker_id text, p_lease_token uuid,
  p_attempt_number integer, p_pipeline_revision integer, p_output jsonb, p_output_hash text, p_next_stage text
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare changed integer;
begin
  update public.job_stage_runs set status='succeeded', side_effect_phase='committed', output_json=p_output, output_hash=p_output_hash, completed_at=now(), heartbeat_at=now()
  where id=p_stage_run_id and status='running' and run_token=p_run_token and job_id=p_job_id and worker_id=p_worker_id and lease_token=p_lease_token and job_attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision;
  get diagnostics changed = row_count;
  if changed <> 1 then raise exception 'RUN_TOKEN_LOST'; end if;
  update public.video_jobs set next_stage=p_next_stage, last_completed_stage=(select stage from public.job_stage_runs where id=p_stage_run_id), current_step=p_next_stage, status=case when p_next_stage='completed' then 'completed' else status end, progress=case when p_next_stage='completed' then 100 else progress end, finished_at=case when p_next_stage='completed' then now() else finished_at end, updated_at=now(), claimed_by=case when p_next_stage='completed' then null else claimed_by end, claimed_at=case when p_next_stage='completed' then null else claimed_at end, lease_token=case when p_next_stage='completed' then null else lease_token end, lease_expires_at=case when p_next_stage='completed' then null else lease_expires_at end, heartbeat_at=case when p_next_stage='completed' then null else heartbeat_at end where id=p_job_id and status not in ('completed','failed','cancelled') and claimed_by=p_worker_id and lease_token=p_lease_token and attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision and lease_expires_at > now();
  get diagnostics changed = row_count;
  if changed <> 1 then raise exception 'LEASE_LOST'; end if;
  return jsonb_build_object('ok',true,'next_stage',p_next_stage);
end;
$$;

create or replace function public.fail_job_stage(
  p_stage_run_id uuid, p_run_token uuid, p_job_id uuid, p_worker_id text, p_lease_token uuid,
  p_attempt_number integer, p_pipeline_revision integer, p_error jsonb, p_failure_class text, p_retryable boolean
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare changed integer;
begin
  update public.job_stage_runs set status='failed', error_json=coalesce(p_error,'{}'::jsonb) || jsonb_build_object('_retryable',p_retryable), completed_at=now()
  where id=p_stage_run_id and status='running' and run_token=p_run_token and job_id=p_job_id and worker_id=p_worker_id and lease_token=p_lease_token and job_attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision;
  get diagnostics changed = row_count;
  if changed <> 1 then raise exception 'RUN_TOKEN_LOST'; end if;
  update public.video_jobs set failure_class=p_failure_class, error_message=coalesce(p_error->>'message',error_message), updated_at=now() where id=p_job_id and status not in ('completed','failed','cancelled') and claimed_by=p_worker_id and lease_token=p_lease_token and attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision and lease_expires_at > now();
  get diagnostics changed = row_count;
  if changed <> 1 then raise exception 'LEASE_LOST'; end if;
  return jsonb_build_object('ok',true,'retryable',p_retryable);
end;
$$;

revoke all on function public.claim_next_video_job_fenced(text, integer) from public, anon, authenticated;
revoke all on function public.heartbeat_video_job(uuid, text, uuid, integer, integer, integer) from public, anon, authenticated;
revoke all on function public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer) from public, anon, authenticated;
revoke all on function public.reserve_stage_external_attempt(uuid, uuid, text, integer, uuid, text, uuid, integer, integer) from public, anon, authenticated;
revoke all on function public.finalize_stage_success(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text, text) from public, anon, authenticated;
revoke all on function public.fail_job_stage(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text, boolean) from public, anon, authenticated;
grant execute on function public.claim_next_video_job_fenced(text, integer) to service_role;
grant execute on function public.heartbeat_video_job(uuid, text, uuid, integer, integer, integer) to service_role;
grant execute on function public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer) to service_role;
grant execute on function public.reserve_stage_external_attempt(uuid, uuid, text, integer, uuid, text, uuid, integer, integer) to service_role;
grant execute on function public.finalize_stage_success(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text, text) to service_role;
grant execute on function public.fail_job_stage(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text, boolean) to service_role;
