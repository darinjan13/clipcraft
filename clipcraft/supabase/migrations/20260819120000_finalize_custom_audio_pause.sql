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
      next_stage = 'generate_voice',
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
    'next_stage', 'generate_voice'
  );
end;
$$;

revoke all on function public.finalize_stage_awaiting_audio(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text)
  from public, anon, authenticated;
grant execute on function public.finalize_stage_awaiting_audio(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text)
  to service_role;
