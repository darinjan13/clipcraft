-- Mirror of the fail_job_stage hardening: scene fan-out can reach
-- finalize_stage_success after the stage row already left 'running'
-- (e.g. a failure branch committed first, or a duplicate finalize).
-- Raising RUN_TOKEN_LOST/LEASE_LOST in that case turns a recoverable
-- race into an opaque 400 that kills the job with "Bad request".
-- Return a benign already_finalized result when the row/job is already
-- terminal; keep raising on genuine token/lease mismatch.
CREATE OR REPLACE FUNCTION public.finalize_stage_success(p_stage_run_id uuid, p_run_token uuid, p_job_id uuid, p_worker_id text, p_lease_token uuid, p_attempt_number integer, p_pipeline_revision integer, p_output jsonb, p_output_hash text, p_next_stage text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare changed integer;
declare cur_status text;
declare cur_job_status text;
begin
  update public.job_stage_runs set status='succeeded', side_effect_phase='committed', output_json=p_output, output_hash=p_output_hash, completed_at=now(), heartbeat_at=now()
  where id=p_stage_run_id and status='running' and run_token=p_run_token and job_id=p_job_id and worker_id=p_worker_id and lease_token=p_lease_token and job_attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision;
  get diagnostics changed = row_count;
  if changed <> 1 then
    select status into cur_status from public.job_stage_runs where id=p_stage_run_id;
    if cur_status in ('succeeded','failed') then
      return jsonb_build_object('ok',true,'already_finalized',true,'next_stage',p_next_stage);
    end if;
    raise exception 'RUN_TOKEN_LOST';
  end if;
  update public.video_jobs set next_stage=p_next_stage, last_completed_stage=(select stage from public.job_stage_runs where id=p_stage_run_id), current_step=p_next_stage, status=case when p_next_stage='completed' then 'completed' else status end, progress=case when p_next_stage='completed' then 100 else progress end, finished_at=case when p_next_stage='completed' then now() else finished_at end, updated_at=now(), claimed_by=case when p_next_stage='completed' then null else claimed_by end, claimed_at=case when p_next_stage='completed' then null else claimed_at end, lease_token=case when p_next_stage='completed' then null else lease_token end, lease_expires_at=case when p_next_stage='completed' then null else lease_expires_at end, heartbeat_at=case when p_next_stage='completed' then null else heartbeat_at end where id=p_job_id and status not in ('completed','failed','cancelled') and claimed_by=p_worker_id and lease_token=p_lease_token and attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision and lease_expires_at > now();
  get diagnostics changed = row_count;
  if changed <> 1 then
    select status into cur_job_status from public.video_jobs where id=p_job_id;
    if cur_job_status in ('completed','failed','cancelled') then
      return jsonb_build_object('ok',true,'already_finalized',true,'next_stage',p_next_stage);
    end if;
    raise exception 'LEASE_LOST';
  end if;
  return jsonb_build_object('ok',true,'next_stage',p_next_stage);
end;
$function$;
