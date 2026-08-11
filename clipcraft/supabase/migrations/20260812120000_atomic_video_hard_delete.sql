-- Atomic, irreversible deletion of one video job and all job-owned records.

create or replace function public.prevent_video_job_event_mutations()
returns trigger
language plpgsql
security definer set search_path = ''
as $$
begin
  if tg_op = 'DELETE'
     and current_setting('clipcraft.hard_delete_job_id', true) = old.job_id::text then
    return old;
  end if;

  raise exception 'video_job_events is append-only';
end;
$$;

revoke all on function public.prevent_video_job_event_mutations() from public, anon, authenticated;

drop trigger if exists video_job_events_append_only on public.video_job_events;
create trigger video_job_events_append_only
  before update or delete on public.video_job_events
  for each row execute function public.prevent_video_job_event_mutations();

create or replace function public.hard_delete_video_job(p_job_id uuid)
returns boolean
language plpgsql
security definer set search_path = ''
as $$
begin
  perform 1
  from public.video_jobs
  where id = p_job_id
  for update;

  if not found then
    return false;
  end if;

  perform set_config('clipcraft.hard_delete_job_id', p_job_id::text, true);

  delete from public.video_job_events where job_id = p_job_id;
  if pg_catalog.to_regclass('public.regeneration_operations') is not null then
    execute 'delete from public.regeneration_operations where job_id = $1' using p_job_id;
  end if;
  delete from public.assets where job_id = p_job_id;
  delete from public.scenes where job_id = p_job_id;
  delete from public.job_stage_runs where job_id = p_job_id;
  delete from public.video_jobs where id = p_job_id;

  return found;
end;
$$;

revoke all on function public.hard_delete_video_job(uuid) from public, anon, authenticated;
grant execute on function public.hard_delete_video_job(uuid) to service_role;
