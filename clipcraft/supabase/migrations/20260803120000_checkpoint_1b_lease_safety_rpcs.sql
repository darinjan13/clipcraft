-- Checkpoint 1B lease safety. Legacy nullable values are preserved; defaults
-- and NOT VALID checks constrain rows written after this migration.

alter table public.video_jobs
  add column if not exists max_job_attempts integer;

alter table public.video_jobs
  alter column max_job_attempts set default 3,
  alter column attempt_number set default 0,
  alter column pipeline_revision set default 1;

do $$
begin
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.video_jobs'::regclass
      and conname = 'video_jobs_attempt_number_forward_check'
  ) then
    alter table public.video_jobs
      add constraint video_jobs_attempt_number_forward_check
      check (attempt_number is not null and attempt_number >= 0) not valid;
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.video_jobs'::regclass
      and conname = 'video_jobs_pipeline_revision_forward_check'
  ) then
    alter table public.video_jobs
      add constraint video_jobs_pipeline_revision_forward_check
      check (pipeline_revision is not null and pipeline_revision >= 1) not valid;
  end if;
  if not exists (
    select 1 from pg_constraint
    where conrelid = 'public.video_jobs'::regclass
      and conname = 'video_jobs_max_job_attempts_forward_check'
  ) then
    alter table public.video_jobs
      add constraint video_jobs_max_job_attempts_forward_check
      check (max_job_attempts is not null and max_job_attempts >= 1) not valid;
  end if;
end;
$$;

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
  next_attempt integer;
  claim_stage text;
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

  next_attempt := coalesce(claimed_job.attempt_number, 0);
  if next_attempt >= coalesce(claimed_job.max_job_attempts, 3) then
    update public.video_jobs
    set attempt_number = next_attempt,
        max_job_attempts = coalesce(claimed_job.max_job_attempts, 3),
        pipeline_revision = coalesce(claimed_job.pipeline_revision, 1),
        status = 'failed',
        current_step = 'failed',
        failure_class = 'LEASE_EXPIRED_MAX_ATTEMPTS',
        error_message = 'LEASE_EXPIRED_MAX_ATTEMPTS',
        finished_at = now(),
        updated_at = now()
    where id = claimed_job.id;

    return jsonb_build_object(
      'claimed', false,
      'job_id', claimed_job.id,
      'failure_class', 'LEASE_EXPIRED_MAX_ATTEMPTS',
      'error_message', 'LEASE_EXPIRED_MAX_ATTEMPTS'
    );
  end if;

  claim_stage := coalesce(claimed_job.next_stage, 'generate_script');
  update public.video_jobs
  set status = case claim_stage
        when 'generate_script' then 'generating_script'
        when 'generate_images' then 'generating_images'
        when 'generate_voice' then 'generating_voice'
        when 'build_captions' then 'building_captions'
        when 'build_manifest' then 'building_manifest'
        when 'render' then 'rendering'
        else 'generating_script'
      end,
      current_step = claim_stage,
      progress = greatest(progress, 5),
      claimed_by = p_worker_id,
      claimed_at = now(),
      lease_token = pg_catalog.gen_random_uuid(),
      lease_expires_at = now() + make_interval(secs => p_lease_seconds),
      heartbeat_at = now(),
      attempt_number = next_attempt + 1,
      max_job_attempts = coalesce(claimed_job.max_job_attempts, 3),
      pipeline_revision = coalesce(pipeline_revision, 1),
      next_stage = claim_stage,
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
      'max_job_attempts', claimed_job.max_job_attempts,
      'pipeline_revision', claimed_job.pipeline_revision,
      'next_stage', claimed_job.next_stage,
      'last_completed_stage', claimed_job.last_completed_stage,
      'failure_class', claimed_job.failure_class
    )
  );
end;
$$;

create or replace function public.reap_expired_video_job_leases(
  p_batch_size integer default 100
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare
  job public.video_jobs;
  next_attempt integer;
  reaped_count integer := 0;
  failed_count integer := 0;
begin
  if p_batch_size is null then
    raise exception 'INVALID_BATCH_SIZE';
  end if;

  for job in
    select *
    from public.video_jobs
    where lease_token is not null
      and lease_expires_at < now()
      and status not in ('completed', 'failed', 'cancelled')
    order by lease_expires_at asc
    limit greatest(1, least(p_batch_size, 1000))
    for update skip locked
  loop
    next_attempt := coalesce(job.attempt_number, 0) + 1;
    if next_attempt >= coalesce(job.max_job_attempts, 3) then
      update public.video_jobs
      set attempt_number = next_attempt,
          max_job_attempts = coalesce(job.max_job_attempts, 3),
          pipeline_revision = coalesce(job.pipeline_revision, 1),
          status = 'failed',
          current_step = 'failed',
          failure_class = 'LEASE_EXPIRED_MAX_ATTEMPTS',
          error_message = 'LEASE_EXPIRED_MAX_ATTEMPTS',
          finished_at = now(),
          claimed_by = null,
          claimed_at = null,
          lease_token = null,
          lease_expires_at = null,
          heartbeat_at = null,
          updated_at = now()
      where id = job.id;
      failed_count := failed_count + 1;
    else
      update public.video_jobs
      set attempt_number = next_attempt,
          max_job_attempts = coalesce(job.max_job_attempts, 3),
          pipeline_revision = coalesce(job.pipeline_revision, 1),
          status = 'queued',
          current_step = coalesce(job.next_stage, job.current_step, 'queued'),
          claimed_by = null,
          claimed_at = null,
          lease_token = null,
          lease_expires_at = null,
          heartbeat_at = null,
          updated_at = now()
      where id = job.id;
      reaped_count := reaped_count + 1;
    end if;
  end loop;

  return jsonb_build_object(
    'reaped_count', reaped_count,
    'failed_count', failed_count
  );
end;
$$;

create or replace function public.release_video_job(
  p_job_id uuid,
  p_lease_token uuid,
  p_outcome text,
  p_next_stage text default null
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare
  job public.video_jobs;
  prior_stage text;
begin
  select * into job
  from public.video_jobs
  where id = p_job_id
  for update;

  if not found then
    raise exception 'JOB_NOT_FOUND';
  end if;
  if p_lease_token is null or job.lease_token is distinct from p_lease_token then
    raise exception 'LEASE_LOST';
  end if;
  if job.lease_expires_at is null or job.lease_expires_at <= now() then
    raise exception 'LEASE_LOST';
  end if;
  if job.status in ('completed', 'failed', 'cancelled') then
    raise exception 'JOB_TERMINAL';
  end if;
  if p_outcome is null or p_outcome not in ('completed_stage', 'requeue') then
    raise exception 'INVALID_RELEASE_OUTCOME';
  end if;
  if p_outcome = 'completed_stage' and p_next_stage is null then
    raise exception 'INVALID_NEXT_STAGE';
  end if;
  if p_outcome = 'completed_stage' and p_next_stage not in (
    'generate_script', 'generate_images', 'generate_voice', 'build_captions',
    'build_manifest', 'render', 'completed'
  ) then
    raise exception 'INVALID_NEXT_STAGE';
  end if;
  if p_outcome = 'requeue' and p_next_stage is not null then
    raise exception 'INVALID_NEXT_STAGE';
  end if;

  update public.video_jobs
  set attempt_number = coalesce(job.attempt_number, 0),
      pipeline_revision = coalesce(job.pipeline_revision, 1),
      max_job_attempts = coalesce(job.max_job_attempts, 3)
  where id = p_job_id
  returning * into job;

  if p_outcome = 'completed_stage' then
    prior_stage := coalesce(job.next_stage, job.current_step);
    update public.video_jobs
    set last_completed_stage = prior_stage,
        next_stage = p_next_stage,
        current_step = p_next_stage,
        status = case when p_next_stage = 'completed' then 'completed' else 'queued' end,
        progress = case when p_next_stage = 'completed' then 100 else progress end,
        finished_at = case when p_next_stage = 'completed' then now() else finished_at end,
        claimed_by = null,
        claimed_at = null,
        lease_token = null,
        lease_expires_at = null,
        heartbeat_at = null,
        updated_at = now()
    where id = p_job_id;
  else
    update public.video_jobs
    set status = 'queued',
        current_step = coalesce(job.next_stage, job.current_step),
        claimed_by = null,
        claimed_at = null,
        lease_token = null,
        lease_expires_at = null,
        heartbeat_at = null,
        updated_at = now()
    where id = p_job_id;
  end if;

  return jsonb_build_object('ok', true, 'status', case when p_outcome = 'completed_stage' and p_next_stage = 'completed' then 'completed' else 'queued' end, 'next_stage', p_next_stage);
end;
$$;

revoke all on function public.claim_next_video_job_fenced(text, integer) from public, anon, authenticated;
revoke all on function public.reap_expired_video_job_leases(integer) from public, anon, authenticated;
revoke all on function public.release_video_job(uuid, uuid, text, text) from public, anon, authenticated;
grant execute on function public.claim_next_video_job_fenced(text, integer) to service_role;
grant execute on function public.reap_expired_video_job_leases(integer) to service_role;
grant execute on function public.release_video_job(uuid, uuid, text, text) to service_role;
