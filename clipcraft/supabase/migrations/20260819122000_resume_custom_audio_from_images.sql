alter table public.video_jobs
  drop constraint if exists video_jobs_status_check;

alter table public.video_jobs
  add constraint video_jobs_status_check check (status in (
    'queued','generating_script','script_ready','awaiting_audio','resuming',
    'generating_images','generating_voice','building_captions',
    'building_manifest','rendering','completed','failed','cancelled'
  ));

create or replace function public.resume_custom_audio_job(p_job_id uuid)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  job public.video_jobs;
begin
  select * into job
  from public.video_jobs
  where id = p_job_id
  for update;

  if not found then
    raise exception 'JOB_NOT_FOUND';
  end if;
  if job.audio_mode <> 'custom_audio' then
    raise exception 'CUSTOM_AUDIO_REQUIRED';
  end if;

  if job.status = 'awaiting_audio' then
    if not exists (
      select 1
      from public.assets
      where job_id = p_job_id
        and asset_type = 'narration_custom'
    ) then
      raise exception 'CUSTOM_AUDIO_ASSET_REQUIRED';
    end if;
    if job.effective_duration is null or job.effective_duration <= 0 then
      raise exception 'CUSTOM_AUDIO_DURATION_REQUIRED';
    end if;

    update public.video_jobs
    set status = 'resuming',
        current_step = 'resuming',
        next_stage = 'generate_images',
        updated_at = now()
    where id = p_job_id
    returning * into job;
  end if;

  return jsonb_build_object(
    'status', job.status,
    'next_stage', job.next_stage
  );
end;
$$;

revoke all on function public.resume_custom_audio_job(uuid)
  from public, anon, authenticated;
grant execute on function public.resume_custom_audio_job(uuid)
  to service_role;

create or replace function public.finalize_stage_awaiting_audio(
  p_stage_run_id uuid,
  p_run_token uuid,
  p_job_id uuid,
  p_worker_id text,
  p_lease_token uuid,
  p_attempt_number integer,
  p_pipeline_revision integer,
  p_output jsonb,
  p_output_hash text
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  changed integer;
begin
  update public.job_stage_runs
  set status = 'succeeded',
      side_effect_phase = 'committed',
      output_json = p_output,
      output_hash = p_output_hash,
      completed_at = now(),
      heartbeat_at = now()
  where id = p_stage_run_id
    and status = 'running'
    and run_token = p_run_token
    and job_id = p_job_id
    and worker_id = p_worker_id
    and lease_token = p_lease_token
    and job_attempt_number = p_attempt_number
    and pipeline_revision = p_pipeline_revision;

  get diagnostics changed = row_count;
  if changed <> 1 then
    raise exception 'RUN_TOKEN_LOST';
  end if;

  update public.video_jobs
  set status = 'awaiting_audio',
      current_step = 'awaiting_audio',
      progress = 25,
      next_stage = 'generate_images',
      last_completed_stage = 'generate_script',
      claimed_by = null,
      claimed_at = null,
      lease_token = null,
      lease_expires_at = null,
      heartbeat_at = null,
      updated_at = now()
  where id = p_job_id
    and audio_mode = 'custom_audio'
    and status not in ('completed', 'failed', 'cancelled')
    and claimed_by = p_worker_id
    and lease_token = p_lease_token
    and attempt_number = p_attempt_number
    and pipeline_revision = p_pipeline_revision
    and lease_expires_at > now();

  get diagnostics changed = row_count;
  if changed <> 1 then
    raise exception 'LEASE_LOST';
  end if;

  return jsonb_build_object(
    'ok', true,
    'status', 'awaiting_audio',
    'next_stage', 'generate_images'
  );
end;
$$;

revoke all on function public.finalize_stage_awaiting_audio(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text)
  from public, anon, authenticated;
grant execute on function public.finalize_stage_awaiting_audio(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text)
  to service_role;

create or replace function public.claim_next_video_job_fenced(
  p_worker_id text,
  p_lease_seconds integer default 120
)
returns jsonb
language plpgsql
security definer
set search_path = ''
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
  where status in ('queued', 'resuming')
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
      pipeline_revision = coalesce(claimed_job.pipeline_revision, 1),
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
      'failure_class', claimed_job.failure_class,
      'audio_mode', claimed_job.audio_mode,
      'effective_duration', claimed_job.effective_duration
    )
  );
end;
$$;

revoke all on function public.claim_next_video_job_fenced(text, integer)
  from public, anon, authenticated;
grant execute on function public.claim_next_video_job_fenced(text, integer)
  to service_role;
