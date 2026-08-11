-- Guarded rollback for Checkpoint 1B only.

begin;

lock table public.video_jobs in access exclusive mode;

do $$
begin
  if exists (
    select 1
    from public.video_jobs
    where lease_token is not null
      and status not in ('completed', 'failed', 'cancelled')
  ) then
    raise exception 'ACTIVE_FENCED_LEASES_EXIST';
  end if;
end;
$$;

drop function if exists public.reap_expired_video_job_leases(integer);
drop function if exists public.release_video_job(uuid, uuid, text, text);

-- Restore the exact Checkpoint 1A fenced claim before removing the 1B-only
-- attempt-limit column it no longer references.
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

revoke all on function public.claim_next_video_job_fenced(text, integer) from public, anon, authenticated;
grant execute on function public.claim_next_video_job_fenced(text, integer) to service_role;

alter table public.video_jobs
  alter column attempt_number drop default,
  alter column pipeline_revision drop default,
  drop constraint if exists video_jobs_attempt_number_forward_check,
  drop constraint if exists video_jobs_pipeline_revision_forward_check,
  drop constraint if exists video_jobs_max_job_attempts_forward_check,
  drop column if exists max_job_attempts;

commit;
