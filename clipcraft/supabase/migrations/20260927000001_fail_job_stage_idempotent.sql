-- Scene fan-out can finalize a stage on the success branch while a failed
-- scene still reaches fail_job_stage on the failure branch. Raising
-- RUN_TOKEN_LOST/LEASE_LOST in that case turns a recoverable scene failure
-- (pending scenes are retried by the worker) into an opaque 400 that kills
-- the job with "Bad request". Return a benign already_finalized result when
-- the row is already terminal; keep raising on genuine token/lease mismatch.
CREATE OR REPLACE FUNCTION public.fail_job_stage(p_stage_run_id uuid, p_run_token uuid, p_job_id uuid, p_worker_id text, p_lease_token uuid, p_attempt_number integer, p_pipeline_revision integer, p_error jsonb, p_failure_class text, p_retryable boolean)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
declare changed integer;
declare cur_status text;
declare cur_job_status text;
begin
  update public.job_stage_runs set status='failed', error_json=coalesce(p_error,'{}'::jsonb) || jsonb_build_object('_retryable',p_retryable), completed_at=now()
  where id=p_stage_run_id and status='running' and run_token=p_run_token and job_id=p_job_id and worker_id=p_worker_id and lease_token=p_lease_token and job_attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision;
  get diagnostics changed = row_count;
  if changed <> 1 then
    select status into cur_status from public.job_stage_runs where id=p_stage_run_id;
    if cur_status in ('succeeded','failed') then
      return jsonb_build_object('ok',true,'already_finalized',true,'retryable',p_retryable);
    end if;
    raise exception 'RUN_TOKEN_LOST';
  end if;
  update public.video_jobs set failure_class=p_failure_class, error_message=coalesce(p_error->>'message',error_message), updated_at=now() where id=p_job_id and status not in ('completed','failed','cancelled') and claimed_by=p_worker_id and lease_token=p_lease_token and attempt_number=p_attempt_number and pipeline_revision=p_pipeline_revision and lease_expires_at > now();
  get diagnostics changed = row_count;
  if changed <> 1 then
    select status into cur_job_status from public.video_jobs where id=p_job_id;
    if cur_job_status in ('completed','failed','cancelled') then
      return jsonb_build_object('ok',true,'already_finalized',true,'retryable',p_retryable);
    end if;
    raise exception 'LEASE_LOST';
  end if;
  return jsonb_build_object('ok',true,'retryable',p_retryable);
end;
$function$;
