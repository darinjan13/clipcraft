-- ClipCraft AI - Core backend architecture foundation
-- Repository-only foundation. Runtime workflows remain unpublished/inactive.
-- Prerequisites: 001_create_all_tables.sql, 002_add_job_claiming.sql,
--                003_asset_path_functions.sql

create extension if not exists pgcrypto;

-- ============================================================
-- Revisioned, fenced job state
-- ============================================================
alter table public.video_jobs
  add column if not exists lease_token uuid,
  add column if not exists lease_expires_at timestamptz,
  add column if not exists heartbeat_at timestamptz,
  add column if not exists attempt_number integer not null default 0,
  add column if not exists max_job_attempts integer not null default 3,
  add column if not exists available_at timestamptz not null default now(),
  add column if not exists pipeline_revision integer not null default 1,
  add column if not exists current_revision integer not null default 1,
  add column if not exists revision_sequence integer not null default 1,
  add column if not exists next_stage text not null default 'generate_script',
  add column if not exists last_completed_stage text,
  add column if not exists failure_class text,
  add column if not exists cancel_requested boolean not null default false;

alter table public.video_jobs
  drop constraint if exists video_jobs_attempt_number_check,
  drop constraint if exists video_jobs_max_job_attempts_check,
  drop constraint if exists video_jobs_pipeline_revision_check,
  drop constraint if exists video_jobs_lease_shape_check;

-- Preserve legacy claimed rows by converting every partial claim into a
-- fenced lease before enforcing the all-or-none lease shape constraint.
update public.video_jobs
set attempt_number = case
      when claimed_by is not null or claimed_at is not null then greatest(1, retry_count + 1)
      else greatest(0, retry_count)
    end,
    max_job_attempts = greatest(1, max_retries + 1),
    revision_sequence = greatest(1, pipeline_revision, current_revision)
where attempt_number = 0 or max_job_attempts = 3;

update public.video_jobs
set claimed_by = coalesce(claimed_by, 'legacy-migration'),
    claimed_at = coalesce(claimed_at, now()),
    lease_token = coalesce(lease_token, public.gen_random_uuid()),
    lease_expires_at = coalesce(claimed_at, now()) + interval '120 seconds',
    heartbeat_at = coalesce(claimed_at, now())
where lease_token is null
  and (claimed_by is not null or claimed_at is not null or lease_expires_at is not null or heartbeat_at is not null);

update public.video_jobs
set claimed_by = coalesce(claimed_by, 'legacy-migration'),
    claimed_at = coalesce(claimed_at, now()),
    lease_expires_at = coalesce(lease_expires_at, now() + interval '120 seconds'),
    heartbeat_at = coalesce(heartbeat_at, claimed_at)
where lease_token is not null;

alter table public.video_jobs
  add constraint video_jobs_attempt_number_check check (attempt_number >= 0),
  add constraint video_jobs_max_job_attempts_check check (max_job_attempts >= 1),
  add constraint video_jobs_pipeline_revision_check check (pipeline_revision >= 1 and current_revision >= 1 and revision_sequence >= current_revision),
  add constraint video_jobs_lease_shape_check check (
    (lease_token is null and claimed_by is null and claimed_at is null and lease_expires_at is null and heartbeat_at is null)
    or
    (lease_token is not null and claimed_by is not null and claimed_at is not null and lease_expires_at is not null and heartbeat_at is not null)
  );

create index if not exists video_jobs_available_queue_idx
  on public.video_jobs(priority desc, available_at asc, created_at asc)
  where status = 'queued' and lease_token is null;

create index if not exists video_jobs_lease_expiry_idx
  on public.video_jobs(lease_expires_at)
  where lease_token is not null;

-- Existing retry_count/max_retries remain for compatibility. New control uses
-- attempt_number/max_job_attempts, where max_job_attempts is total acquisitions.
comment on column public.video_jobs.attempt_number is 'Total lease acquisitions, including the initial claim';
comment on column public.video_jobs.max_job_attempts is 'Maximum total lease acquisitions; not additional retries';
comment on column public.video_jobs.lease_token is 'Fencing token regenerated on every claim or reclaim';
comment on column public.video_jobs.next_stage is 'Authoritative resume point; current_step remains a display projection';

-- ============================================================
-- Revision-aware scenes and logical assets
-- ============================================================
alter table public.scenes add column if not exists pipeline_revision integer not null default 1;

do $$
declare
  constraint_name text;
begin
  select conname into constraint_name
  from pg_constraint
  where conrelid = 'public.scenes'::regclass
    and contype = 'u'
    and pg_get_constraintdef(oid) like '%job_id%scene_index%';
  if constraint_name is not null then
    execute format('alter table public.scenes drop constraint %I', constraint_name);
  end if;
end;
$$;

create unique index if not exists scenes_job_revision_index_uidx
  on public.scenes(job_id, pipeline_revision, scene_index);

alter table public.assets
  add column if not exists pipeline_revision integer not null default 1,
  add column if not exists logical_key text,
  add column if not exists stage_run_id uuid,
  add column if not exists content_sha256 text,
  add column if not exists committed_at timestamptz;

create unique index if not exists assets_job_revision_logical_uidx
  on public.assets(job_id, pipeline_revision, logical_key)
  where logical_key is not null;

create index if not exists assets_stage_run_idx on public.assets(stage_run_id);

-- ============================================================
-- Durable per-stage execution ledger
-- ============================================================
create table if not exists public.job_stage_runs (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.video_jobs(id) on delete cascade,
  pipeline_revision integer not null check (pipeline_revision >= 1),
  stage text not null check (stage in ('generate_script','generate_images','generate_voice','build_captions','build_manifest','render')),
  item_key text not null,
  input_hash text not null,
  status text not null default 'pending'
    check (status in ('pending','running','unknown_outcome','succeeded','failed','abandoned')),
  run_token uuid,
  job_attempt_number integer not null default 0 check (job_attempt_number >= 0),
  worker_id text,
  lease_token uuid,
  side_effect_phase text not null default 'not_started'
    check (side_effect_phase in ('not_started','reserved','invoked','output_written','committed')),
  workflow_delivery_count integer not null default 0 check (workflow_delivery_count >= 0),
  provider_attempt_count integer not null default 0 check (provider_attempt_count >= 0),
  tts_attempt_count integer not null default 0 check (tts_attempt_count >= 0),
  renderer_attempt_count integer not null default 0 check (renderer_attempt_count >= 0),
  database_retry_count integer not null default 0 check (database_retry_count >= 0),
  filesystem_attempt_count integer not null default 0 check (filesystem_attempt_count >= 0),
  output_json jsonb,
  output_hash text,
  error_json jsonb,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  heartbeat_at timestamptz,
  completed_at timestamptz,
  unique (job_id, pipeline_revision, stage, item_key)
);

create index if not exists job_stage_runs_resume_idx
  on public.job_stage_runs(job_id, pipeline_revision, status, stage);
create index if not exists job_stage_runs_lease_idx
  on public.job_stage_runs(lease_token)
  where lease_token is not null;

-- ============================================================
-- Durable regeneration requests
-- ============================================================
create table if not exists public.regeneration_operations (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.video_jobs(id) on delete cascade,
  client_request_id text not null,
  operation text not null check (operation in ('SCENE_VISUAL','ALL_IMAGES','SCRIPT_CREATIVE','VIDEO_RENDER_ONLY','VIDEO_FULL_CREATIVE')),
  target_scene_id uuid references public.scenes(id) on delete restrict,
  requested_revision integer not null check (requested_revision >= 1),
  resume_from text not null check (resume_from in ('selected_scene_image','generate_images','generate_script','build_manifest')),
  status text not null default 'queued'
    check (status in ('queued','leased','running','awaiting_reconciliation','cancel_requested','succeeded','failed','cancelled')),
  invalidated_artifacts jsonb not null default '[]'::jsonb,
  claimed_by text,
  lease_token uuid,
  lease_expires_at timestamptz,
  attempt_number integer not null default 0 check (attempt_number >= 0),
  error_json jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz,
  unique(job_id, client_request_id)
);

create unique index if not exists regeneration_one_live_job_uidx
  on public.regeneration_operations(job_id)
  where status in ('queued','leased','running','awaiting_reconciliation','cancel_requested');
create index if not exists regeneration_queue_idx
  on public.regeneration_operations(status, created_at)
  where status = 'queued';

-- ============================================================
-- Canonical path identifiers
-- ============================================================
create or replace function public.get_asset_key(
  p_job_id uuid,
  p_asset_type text,
  p_scene_index integer default null
)
returns text
language plpgsql
stable
as $$
declare
  filename text;
begin
  if p_asset_type not in ('scene','narration','captions','manifest','video','thumbnail','render_log','error_log') then
    raise exception 'UNKNOWN_ASSET_TYPE';
  end if;
  if p_asset_type = 'scene' then
    if p_scene_index is null or p_scene_index < 1 or p_scene_index > 999 then
      raise exception 'INVALID_SCENE_INDEX';
    end if;
    filename := 'scene-' || lpad(p_scene_index::text, 2, '0') || '.png';
  else
    filename := case p_asset_type
      when 'narration' then 'narration.wav'
      when 'captions' then 'captions.ass'
      when 'manifest' then 'render-manifest.json'
      when 'video' then 'final.mp4'
      when 'thumbnail' then 'thumbnail.jpg'
      when 'render_log' then 'render.log'
      when 'error_log' then 'error.log'
    end;
  end if;
  return lower(p_job_id::text) || '/' || filename;
end;
$$;

create or replace function public.get_asset_path(
  job_id uuid,
  asset_type text,
  scene_index integer default null
)
returns jsonb
language plpgsql
stable
as $$
declare
  asset_key text := public.get_asset_key(job_id, asset_type, scene_index);
  filename text := substring(asset_key from '[^/]+$');
  container_path text := '/data/jobs/' || asset_key;
begin
  return jsonb_build_object(
    'asset_key', asset_key,
    'container_path', container_path,
    'path', container_path,
    'filename', filename,
    'job_id', lower(job_id::text),
    'asset_type', asset_type
  );
end;
$$;

-- ============================================================
-- Ownership helpers and lease RPCs
-- ============================================================
create or replace function public.claim_next_video_job(
  p_worker_id text,
  p_lease_seconds integer default 120
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare
  selected_job public.video_jobs;
  claimed_job public.video_jobs;
  new_token uuid := public.gen_random_uuid();
begin
  if p_worker_id is null or length(trim(p_worker_id)) = 0 then raise exception 'INVALID_WORKER_ID'; end if;
  if p_lease_seconds < 5 or p_lease_seconds > 900 then raise exception 'INVALID_LEASE_SECONDS'; end if;

  select * into selected_job
  from public.video_jobs
  where (
    (status = 'queued' and lease_token is null and available_at <= now())
    or
    (status not in ('completed','failed','cancelled') and lease_token is not null and lease_expires_at <= now())
  )
  and attempt_number < max_job_attempts
  order by priority desc, available_at asc, created_at asc
  limit 1
  for update skip locked;

  if not found then return jsonb_build_object('claimed', false); end if;

  update public.video_jobs
  set status = case next_stage
      when 'generate_script' then 'generating_script'
      when 'generate_images' then 'generating_images'
      when 'generate_voice' then 'generating_voice'
      when 'build_captions' then 'building_captions'
      when 'build_manifest' then 'building_manifest'
      when 'render' then 'rendering'
      else status end,
      current_step = next_stage,
      claimed_by = p_worker_id,
      claimed_at = now(),
      heartbeat_at = now(),
      lease_expires_at = now() + make_interval(secs => p_lease_seconds),
      lease_token = new_token,
      attempt_number = attempt_number + 1,
      started_at = coalesce(started_at, now()),
      updated_at = now()
  where id = selected_job.id
  returning * into claimed_job;

  return jsonb_build_object('claimed', true, 'job', to_jsonb(claimed_job), 'lease_token', new_token);
end;
$$;

create or replace function public.heartbeat_video_job(
  p_job_id uuid,
  p_worker_id text,
  p_lease_token uuid,
  p_attempt_number integer,
  p_pipeline_revision integer,
  p_lease_seconds integer default 120
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare updated_count integer;
begin
  update public.video_jobs
  set heartbeat_at = now(), lease_expires_at = now() + make_interval(secs => p_lease_seconds), updated_at = now()
  where id = p_job_id and status not in ('completed','failed','cancelled') and claimed_by = p_worker_id and lease_token = p_lease_token
    and attempt_number = p_attempt_number and pipeline_revision = p_pipeline_revision
    and lease_expires_at > now() and status not in ('completed','failed','cancelled');
  get diagnostics updated_count = row_count;
  if updated_count <> 1 then raise exception 'LEASE_LOST'; end if;
  return jsonb_build_object('ok', true, 'lease_expires_at', (select lease_expires_at from public.video_jobs where id = p_job_id), 'cancel_requested', (select cancel_requested from public.video_jobs where id = p_job_id));
end;
$$;

create or replace function public.release_video_job(
  p_job_id uuid, p_worker_id text, p_lease_token uuid, p_attempt_number integer,
  p_pipeline_revision integer, p_available_at timestamptz default now()
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare updated_count integer;
begin
  update public.video_jobs
  set status = 'queued', current_step = next_stage, available_at = p_available_at,
      claimed_by = null, claimed_at = null, heartbeat_at = null, lease_expires_at = null, lease_token = null,
      updated_at = now()
  where id = p_job_id and status not in ('completed','failed','cancelled') and claimed_by = p_worker_id and lease_token = p_lease_token
    and attempt_number = p_attempt_number and pipeline_revision = p_pipeline_revision and lease_expires_at > now();
  get diagnostics updated_count = row_count;
  if updated_count <> 1 then raise exception 'LEASE_LOST'; end if;
  return jsonb_build_object('ok', true, 'status', 'queued');
end;
$$;

create or replace function public.reap_expired_video_job_leases(p_batch_size integer default 100)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare requeued uuid[] := '{}'; failed uuid[] := '{}'; job public.video_jobs;
begin
  for job in
    select * from public.video_jobs
    where lease_token is not null and lease_expires_at <= now() and status not in ('completed','failed','cancelled')
    order by lease_expires_at asc limit greatest(1, least(p_batch_size, 1000))
    for update skip locked
  loop
    if job.attempt_number >= job.max_job_attempts then
      update public.video_jobs set status='failed', current_step='failed', failure_class='crash', error_message='JOB_ATTEMPTS_EXHAUSTED', finished_at=now(), claimed_by=null, claimed_at=null, heartbeat_at=null, lease_expires_at=null, lease_token=null, updated_at=now() where id=job.id;
      failed := array_append(failed, job.id);
    else
      update public.video_jobs set status='queued', current_step=next_stage, available_at=now(), claimed_by=null, claimed_at=null, heartbeat_at=null, lease_expires_at=null, lease_token=null, updated_at=now() where id=job.id;
      requeued := array_append(requeued, job.id);
    end if;
  end loop;
  return jsonb_build_object('requeued_job_ids', requeued, 'failed_job_ids', failed);
end;
$$;

create or replace function public.request_cancel_video_job(
  p_job_id uuid, p_actor_id text, p_reason text default null
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare job public.video_jobs;
begin
  select * into job from public.video_jobs where id=p_job_id for update;
  if not found then raise exception 'JOB_NOT_FOUND'; end if;
  if job.user_id is distinct from p_actor_id then raise exception 'FORBIDDEN'; end if;
  if job.status in ('completed','failed','cancelled') then raise exception 'JOB_TERMINAL'; end if;
  if job.lease_token is null then
    update public.video_jobs set status='cancelled', current_step='cancelled', error_message=coalesce(p_reason,error_message), finished_at=now(), updated_at=now() where id=p_job_id;
    return jsonb_build_object('ok',true,'status','cancelled');
  end if;
  update public.video_jobs set cancel_requested=true, error_message=coalesce(p_reason,error_message), updated_at=now() where id=p_job_id;
  return jsonb_build_object('ok',true,'status','cancel_requested');
end;
$$;

create or replace function public.acknowledge_cancel_video_job(
  p_job_id uuid, p_worker_id text, p_lease_token uuid, p_attempt_number integer, p_pipeline_revision integer
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare updated_count integer;
begin
  update public.video_jobs set status='cancelled', current_step='cancelled', finished_at=now(), claimed_by=null, claimed_at=null, heartbeat_at=null, lease_expires_at=null, lease_token=null, updated_at=now()
  where id=p_job_id and claimed_by=p_worker_id and lease_token=p_lease_token and attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision and lease_expires_at > now() and cancel_requested=true;
  get diagnostics updated_count = row_count;
  if updated_count <> 1 then raise exception 'LEASE_LOST'; end if;
  return jsonb_build_object('ok',true,'status','cancelled');
end;
$$;

-- ============================================================
-- Stage lifecycle and exclusive external-attempt reservation
-- ============================================================
create or replace function public.begin_job_stage(
  p_job_id uuid, p_pipeline_revision integer, p_stage text, p_item_key text, p_input_hash text,
  p_worker_id text, p_lease_token uuid, p_attempt_number integer
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare job public.video_jobs; stage_row public.job_stage_runs; new_run uuid := public.gen_random_uuid();
begin
  if p_item_key is null or length(trim(p_item_key)) = 0 then raise exception 'INVALID_ITEM_KEY'; end if;
  select * into job from public.video_jobs where id=p_job_id for update;
  if not found or job.claimed_by <> p_worker_id or job.lease_token <> p_lease_token or job.attempt_number <> p_attempt_number or job.pipeline_revision <> p_pipeline_revision or job.lease_expires_at <= now() or job.status in ('completed','failed','cancelled') then raise exception 'LEASE_LOST'; end if;
  select * into stage_row from public.job_stage_runs where job_id=p_job_id and pipeline_revision=p_pipeline_revision and stage=p_stage and item_key=p_item_key for update;
  if found then
    if stage_row.input_hash <> p_input_hash then raise exception 'INPUT_HASH_MISMATCH'; end if;
    if stage_row.status = 'succeeded' then return jsonb_build_object('state','CACHED_SUCCESS','stage_run_id',stage_row.id,'output',stage_row.output_json); end if;
    if stage_row.status = 'unknown_outcome' then return jsonb_build_object('state','UNKNOWN_OUTCOME','stage_run_id',stage_row.id); end if;
    if stage_row.status = 'running' then return jsonb_build_object('state','RUNNING','stage_run_id',stage_row.id,'run_token',stage_row.run_token); end if;
    if stage_row.status = 'failed' and coalesce((stage_row.error_json->>'_retryable')::boolean, false) = false then return jsonb_build_object('state','FAILED','stage_run_id',stage_row.id,'output',stage_row.error_json); end if;
    update public.job_stage_runs set status='running', run_token=new_run, worker_id=p_worker_id, lease_token=p_lease_token, job_attempt_number=p_attempt_number, started_at=coalesce(started_at,now()), heartbeat_at=now() where id=stage_row.id returning * into stage_row;
  else
    insert into public.job_stage_runs(job_id,pipeline_revision,stage,item_key,input_hash,status,run_token,job_attempt_number,worker_id,lease_token,started_at,heartbeat_at)
    values(p_job_id,p_pipeline_revision,p_stage,p_item_key,p_input_hash,'running',new_run,p_attempt_number,p_worker_id,p_lease_token,now(),now()) returning * into stage_row;
  end if;
  return jsonb_build_object('state','STARTED','stage_run_id',stage_row.id,'run_token',stage_row.run_token);
end;
$$;

create or replace function public.reserve_stage_external_attempt(
  p_stage_run_id uuid, p_run_token uuid, p_kind text, p_limit integer,
  p_job_id uuid, p_worker_id text, p_lease_token uuid, p_attempt_number integer, p_pipeline_revision integer
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare row public.job_stage_runs; next_attempt integer;
begin
  select * into row from public.job_stage_runs where id=p_stage_run_id for update;
  if not found or row.status <> 'running' or row.run_token <> p_run_token or row.worker_id <> p_worker_id or row.job_id <> p_job_id or row.lease_token <> p_lease_token or row.job_attempt_number <> p_attempt_number or row.pipeline_revision <> p_pipeline_revision then raise exception 'RUN_TOKEN_LOST'; end if;
  if not exists (select 1 from public.video_jobs where id=p_job_id and status not in ('completed','failed','cancelled') and claimed_by=p_worker_id and lease_token=p_lease_token and attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision and lease_expires_at > now()) then raise exception 'LEASE_LOST'; end if;
  next_attempt := case p_kind when 'provider' then row.provider_attempt_count + 1 when 'tts' then row.tts_attempt_count + 1 when 'renderer' then row.renderer_attempt_count + 1 when 'database' then row.database_retry_count + 1 when 'filesystem' then row.filesystem_attempt_count + 1 when 'workflow' then row.workflow_delivery_count + 1 else null end;
  if next_attempt is null then raise exception 'UNKNOWN_ATTEMPT_KIND'; end if;
  if next_attempt > p_limit then return jsonb_build_object('permitted',false,'attempt_number',next_attempt,'remaining',0); end if;
  update public.job_stage_runs set provider_attempt_count=case when p_kind='provider' then next_attempt else provider_attempt_count end, tts_attempt_count=case when p_kind='tts' then next_attempt else tts_attempt_count end, renderer_attempt_count=case when p_kind='renderer' then next_attempt else renderer_attempt_count end, database_retry_count=case when p_kind='database' then next_attempt else database_retry_count end, filesystem_attempt_count=case when p_kind='filesystem' then next_attempt else filesystem_attempt_count end, workflow_delivery_count=case when p_kind='workflow' then next_attempt else workflow_delivery_count end, side_effect_phase='reserved', heartbeat_at=now() where id=row.id;
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
declare updated_count integer;
begin
  update public.job_stage_runs set status='succeeded', side_effect_phase='committed', output_json=p_output, output_hash=p_output_hash, completed_at=now(), heartbeat_at=now()
  where id=p_stage_run_id and status='running' and run_token=p_run_token and job_id=p_job_id and worker_id=p_worker_id and lease_token=p_lease_token and job_attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision;
  get diagnostics updated_count = row_count;
  if updated_count <> 1 then raise exception 'RUN_TOKEN_LOST'; end if;
  if p_next_stage not in ('generate_script','generate_images','generate_voice','build_captions','build_manifest','render','completed') then raise exception 'INVALID_NEXT_STAGE'; end if;
  update public.video_jobs set next_stage=p_next_stage, last_completed_stage=(select stage from public.job_stage_runs where id=p_stage_run_id), current_step=p_next_stage,
    status=case when p_next_stage='completed' then 'completed' else status end,
    progress=case when p_next_stage='completed' then 100 else progress end,
    completed_at=case when p_next_stage='completed' then now() else completed_at end,
    finished_at=case when p_next_stage='completed' then now() else finished_at end,
    claimed_by=case when p_next_stage='completed' then null else claimed_by end,
    claimed_at=case when p_next_stage='completed' then null else claimed_at end,
    heartbeat_at=case when p_next_stage='completed' then null else heartbeat_at end,
    lease_expires_at=case when p_next_stage='completed' then null else lease_expires_at end,
    lease_token=case when p_next_stage='completed' then null else lease_token end,
    updated_at=now()
  where id=p_job_id and status not in ('completed','failed','cancelled') and claimed_by=p_worker_id and lease_token=p_lease_token and attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision and lease_expires_at > now();
  get diagnostics updated_count = row_count;
  if updated_count <> 1 then raise exception 'LEASE_LOST'; end if;
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
declare updated_count integer; next_state text;
begin
  next_state := 'failed';
  update public.job_stage_runs set status=next_state, error_json=coalesce(p_error,'{}'::jsonb) || jsonb_build_object('_retryable',p_retryable), completed_at=now() where id=p_stage_run_id and status='running' and run_token=p_run_token and job_id=p_job_id and worker_id=p_worker_id and lease_token=p_lease_token and job_attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision;
  get diagnostics updated_count = row_count;
  if updated_count <> 1 then raise exception 'RUN_TOKEN_LOST'; end if;
  update public.video_jobs set failure_class=p_failure_class, last_completed_stage=last_completed_stage, error_message=coalesce(p_error->>'message',error_message), updated_at=now() where id=p_job_id and status not in ('completed','failed','cancelled') and claimed_by=p_worker_id and lease_token=p_lease_token and attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision and lease_expires_at > now();
  get diagnostics updated_count = row_count;
  if updated_count <> 1 then raise exception 'LEASE_LOST'; end if;
  return jsonb_build_object('ok',true,'stage_status',next_state,'retryable',p_retryable);
end;
$$;

-- ============================================================
-- Enqueue-only regeneration routing
-- ============================================================
create or replace function public.enqueue_regeneration(
  p_job_id uuid, p_client_request_id text, p_operation text, p_target_scene_id uuid default null
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare job public.video_jobs; existing_operation public.regeneration_operations; operation_row public.regeneration_operations; next_revision integer; resume_stage text; invalidated jsonb;
begin
  if p_operation not in ('SCENE_VISUAL','ALL_IMAGES','SCRIPT_CREATIVE','VIDEO_RENDER_ONLY','VIDEO_FULL_CREATIVE') then raise exception 'INVALID_REGENERATION_OPERATION'; end if;
  if p_client_request_id is null or length(trim(p_client_request_id))=0 then raise exception 'INVALID_CLIENT_REQUEST_ID'; end if;
  select * into job from public.video_jobs where id=p_job_id for update;
  if not found then raise exception 'JOB_NOT_FOUND'; end if;
  select * into existing_operation from public.regeneration_operations where job_id=p_job_id and client_request_id=p_client_request_id;
  if found then return jsonb_build_object('status','EXISTING','operation',to_jsonb(existing_operation)); end if;
  if job.status not in ('completed','failed','cancelled') or job.lease_token is not null then raise exception 'JOB_NOT_TERMINAL'; end if;
  if exists(select 1 from public.regeneration_operations where job_id=p_job_id and status in ('queued','leased','running','awaiting_reconciliation','cancel_requested')) then raise exception 'REGENERATION_CONFLICT'; end if;
  next_revision := greatest(job.pipeline_revision, job.current_revision, job.revision_sequence) + 1;
  resume_stage := case p_operation when 'SCENE_VISUAL' then 'selected_scene_image' when 'ALL_IMAGES' then 'generate_images' when 'SCRIPT_CREATIVE' then 'generate_script' when 'VIDEO_RENDER_ONLY' then 'build_manifest' when 'VIDEO_FULL_CREATIVE' then 'generate_script' end;
  invalidated := case p_operation when 'SCENE_VISUAL' then '["scene_image","manifest","video","thumbnail"]'::jsonb when 'ALL_IMAGES' then '["scene_images","manifest","video","thumbnail"]'::jsonb when 'SCRIPT_CREATIVE' then '["script","scenes","images","narration","captions","manifest","video","thumbnail"]'::jsonb when 'VIDEO_RENDER_ONLY' then '["manifest","video","thumbnail"]'::jsonb when 'VIDEO_FULL_CREATIVE' then '["script","scenes","images","narration","captions","manifest","video","thumbnail"]'::jsonb end;
  if p_operation='SCENE_VISUAL' and p_target_scene_id is null then raise exception 'TARGET_SCENE_REQUIRED'; end if;
  if p_target_scene_id is not null and not exists (select 1 from public.scenes scene where scene.id=p_target_scene_id and scene.job_id=p_job_id) then raise exception 'TARGET_SCENE_JOB_MISMATCH'; end if;
  update public.video_jobs set revision_sequence=next_revision, updated_at=now() where id=p_job_id;
  insert into public.regeneration_operations(job_id,client_request_id,operation,target_scene_id,requested_revision,resume_from,invalidated_artifacts)
  values(p_job_id,p_client_request_id,p_operation,p_target_scene_id,next_revision,resume_stage,invalidated)
  returning * into operation_row;
  return jsonb_build_object('status','QUEUED','operation',to_jsonb(operation_row));
end;
$$;

-- Internal functions are not public API endpoints. Existing n8n service-role
-- execution remains the only intended caller until workflow publication.
revoke all on function public.claim_next_video_job(text, integer) from public, anon, authenticated;
revoke all on function public.heartbeat_video_job(uuid, text, uuid, integer, integer, integer) from public, anon, authenticated;
revoke all on function public.release_video_job(uuid, text, uuid, integer, integer, timestamptz) from public, anon, authenticated;
revoke all on function public.reap_expired_video_job_leases(integer) from public, anon, authenticated;
revoke all on function public.request_cancel_video_job(uuid, text, text) from public, anon, authenticated;
revoke all on function public.acknowledge_cancel_video_job(uuid, text, uuid, integer, integer) from public, anon, authenticated;
revoke all on function public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer) from public, anon, authenticated;
revoke all on function public.reserve_stage_external_attempt(uuid, uuid, text, integer, uuid, text, uuid, integer, integer) from public, anon, authenticated;
revoke all on function public.finalize_stage_success(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text, text) from public, anon, authenticated;
revoke all on function public.fail_job_stage(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text, boolean) from public, anon, authenticated;
revoke all on function public.enqueue_regeneration(uuid, text, text, uuid) from public, anon, authenticated;
grant execute on function public.claim_next_video_job(text, integer) to service_role;
grant execute on function public.heartbeat_video_job(uuid, text, uuid, integer, integer, integer) to service_role;
grant execute on function public.release_video_job(uuid, text, uuid, integer, integer, timestamptz) to service_role;
grant execute on function public.reap_expired_video_job_leases(integer) to service_role;
grant execute on function public.request_cancel_video_job(uuid, text, text) to service_role;
grant execute on function public.acknowledge_cancel_video_job(uuid, text, uuid, integer, integer) to service_role;
grant execute on function public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer) to service_role;
grant execute on function public.reserve_stage_external_attempt(uuid, uuid, text, integer, uuid, text, uuid, integer, integer) to service_role;
grant execute on function public.finalize_stage_success(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text, text) to service_role;
grant execute on function public.fail_job_stage(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text, boolean) to service_role;
grant execute on function public.enqueue_regeneration(uuid, text, text, uuid) to service_role;
