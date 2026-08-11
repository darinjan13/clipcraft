-- Rollback for 20260802140000_reconcile_job_leases_and_claim_contract.sql.
-- Refuse to remove an active fenced lease; terminal fenced history may be removed
-- with the stage ledger as part of an explicit rollback.

do $guard$
declare
  active_fenced boolean;
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'video_jobs' and column_name = 'lease_token'
  ) then
    execute $query$
      select exists (
        select 1 from public.video_jobs
        where lease_token is not null
          and status not in ('completed', 'failed', 'cancelled')
      )
    $query$ into active_fenced;
    if active_fenced then
      raise exception 'ACTIVE_FENCED_LEASES_EXIST';
    end if;
  end if;
end;
$guard$;

drop function if exists public.fail_job_stage(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text, boolean);
drop function if exists public.finalize_stage_success(uuid, uuid, uuid, text, uuid, integer, integer, jsonb, text, text);
drop function if exists public.reserve_stage_external_attempt(uuid, uuid, text, integer, uuid, text, uuid, integer, integer);
drop function if exists public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer);
drop function if exists public.heartbeat_video_job(uuid, text, uuid, integer, integer, integer);
drop function if exists public.claim_next_video_job_fenced(text, integer);

drop index if exists public.video_jobs_fenced_queue_idx;
drop index if exists public.video_jobs_fenced_lease_idx;
drop table if exists public.job_stage_runs cascade;

alter table public.video_jobs
  drop constraint if exists video_jobs_lease_shape_check,
  drop column if exists lease_token,
  drop column if exists lease_expires_at,
  drop column if exists heartbeat_at,
  drop column if exists attempt_number,
  drop column if exists pipeline_revision,
  drop column if exists next_stage,
  drop column if exists last_completed_stage,
  drop column if exists failure_class;
