-- Update reap_expired_video_job_leases to exclude awaiting_audio jobs
-- Phase 8: Custom Audio / Assisted Voice Mode

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
      and NOT (audio_mode = 'custom_audio' and status = 'awaiting_audio')
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