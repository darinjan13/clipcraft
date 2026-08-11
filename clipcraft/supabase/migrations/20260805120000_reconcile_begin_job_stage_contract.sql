-- Checkpoint 1R: reconcile the additive begin_job_stage ledger contract.
-- Constrained Option A. Preserves the exact signature:
--   begin_job_stage(uuid, integer, text, text, text, text, uuid, integer) returns jsonb
-- CREATE OR REPLACE FUNCTION only (no DROP). No new columns, no historical rewrites,
-- no destructive changes. service_role-only grants re-asserted.
--
-- Canonical responses:
--   STARTED               new ledger row inserted (status 'running'); exactly one fresh run_token
--   CACHED_SUCCESS        existing 'succeeded' row with matching input_hash; output = output_json; no run_token
--   RUNNING               existing 'running' row with matching input_hash; no new token, no ownership refresh
--   FAILED                existing 'failed' row with matching input_hash (terminal, never overwritten)
--   INPUT_HASH_MISMATCH   existing row (succeeded/running/failed) with differing input_hash
--   INVALID_ITEM_KEY      JSON return (NOT an exception) when p_item_key is blank; reserved solely for that
--   UNKNOWN_OUTCOME       existing row with a non-canonical status
--   LEASE_LOST            exception: fence mismatch / expired lease / terminal video job /
--                         null lease token / non-positive attempt / non-positive revision
-- Controlled validation exceptions before any mutation:
--   INVALID_STAGE, INVALID_INPUT_HASH, INVALID_WORKER_ID.

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
  if p_stage is null or length(trim(p_stage)) = 0 then
    raise exception 'INVALID_STAGE';
  end if;
  if p_input_hash is null or length(trim(p_input_hash)) = 0 then
    raise exception 'INVALID_INPUT_HASH';
  end if;
  if p_worker_id is null or length(trim(p_worker_id)) = 0 then
    raise exception 'INVALID_WORKER_ID';
  end if;
  if p_item_key is null or length(trim(p_item_key)) = 0 then
    return jsonb_build_object('state','INVALID_ITEM_KEY');
  end if;
  if p_lease_token is null or p_attempt_number <= 0 or p_pipeline_revision <= 0 then
    raise exception 'LEASE_LOST';
  end if;

  select * into job_row from public.video_jobs where id = p_job_id for update;
  if not found
     or job_row.claimed_by is distinct from p_worker_id
     or job_row.lease_token is distinct from p_lease_token
     or job_row.attempt_number is distinct from p_attempt_number
     or job_row.pipeline_revision is distinct from p_pipeline_revision
     or job_row.lease_expires_at <= now()
     or job_row.status in ('completed','failed','cancelled') then
    raise exception 'LEASE_LOST';
  end if;

  select * into stage_row from public.job_stage_runs
  where job_id = p_job_id and pipeline_revision = p_pipeline_revision
    and stage = p_stage and item_key = p_item_key
  for update;

  if found then
    if stage_row.status = 'succeeded' then
      if stage_row.input_hash is distinct from p_input_hash then
        return jsonb_build_object('state','INPUT_HASH_MISMATCH','stage_run_id',stage_row.id);
      end if;
      return jsonb_build_object('state','CACHED_SUCCESS','stage_run_id',stage_row.id,'output',stage_row.output_json);
    end if;
    if stage_row.input_hash is distinct from p_input_hash then
      return jsonb_build_object('state','INPUT_HASH_MISMATCH','stage_run_id',stage_row.id);
    end if;
    if stage_row.status = 'running' then
      return jsonb_build_object('state','RUNNING','stage_run_id',stage_row.id);
    end if;
    if stage_row.status = 'failed' then
      return jsonb_build_object('state','FAILED','stage_run_id',stage_row.id,'error',stage_row.error_json);
    end if;
    return jsonb_build_object('state','UNKNOWN_OUTCOME','stage_run_id',stage_row.id);
  end if;

  insert into public.job_stage_runs(job_id,pipeline_revision,stage,item_key,input_hash,status,job_attempt_number,worker_id,lease_token)
  values(p_job_id,p_pipeline_revision,p_stage,p_item_key,p_input_hash,'running',p_attempt_number,p_worker_id,p_lease_token)
  returning * into stage_row;

  return jsonb_build_object('state','STARTED','stage_run_id',stage_row.id,'run_token',stage_row.run_token);
end;
$$;

revoke all on function public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer) from public, anon, authenticated;
grant execute on function public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer) to service_role;
