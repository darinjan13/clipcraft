-- Rollback for Checkpoint 1R: restore the pre-1R begin_job_stage body
-- (overwrite-on-rebegin behavior, NULL-unsafe fence comparisons) and
-- re-assert service_role-only grants. CREATE OR REPLACE only; signature unchanged.

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

revoke all on function public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer) from public, anon, authenticated;
grant execute on function public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer) to service_role;
