alter table public.video_jobs
  add column if not exists uploaded_audio_duration numeric(6,2);

delete from public.assets older
using public.assets newer
where older.job_id = newer.job_id
  and older.asset_type = 'narration_custom'
  and newer.asset_type = 'narration_custom'
  and (older.created_at, older.id) < (newer.created_at, newer.id);

create unique index if not exists assets_custom_narration_job_uidx
  on public.assets(job_id)
  where asset_type = 'narration_custom';

create or replace function public.persist_custom_audio_upload(
  p_job_id uuid,
  p_local_path text,
  p_mime_type text,
  p_file_size bigint,
  p_duration numeric
)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  job public.video_jobs;
  asset public.assets;
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
  if job.status <> 'awaiting_audio' then
    raise exception 'AWAITING_AUDIO_REQUIRED';
  end if;
  if p_duration is null or p_duration <= 0 then
    raise exception 'INVALID_AUDIO_DURATION';
  end if;
  if p_file_size is null or p_file_size <= 0 then
    raise exception 'INVALID_AUDIO_FILE_SIZE';
  end if;

  update public.video_jobs
  set uploaded_audio_duration = round(p_duration, 2),
      effective_duration = round(p_duration, 2),
      updated_at = now()
  where id = p_job_id;

  insert into public.assets(job_id, asset_type, local_path, mime_type, file_size)
  values (p_job_id, 'narration_custom', p_local_path, p_mime_type, p_file_size)
  on conflict (job_id) where asset_type = 'narration_custom'
  do update set local_path = excluded.local_path,
                mime_type = excluded.mime_type,
                file_size = excluded.file_size,
                created_at = now()
  returning * into asset;

  return to_jsonb(asset);
end;
$$;

revoke all on function public.persist_custom_audio_upload(uuid, text, text, bigint, numeric)
  from public, anon, authenticated;
grant execute on function public.persist_custom_audio_upload(uuid, text, text, bigint, numeric)
  to service_role;
