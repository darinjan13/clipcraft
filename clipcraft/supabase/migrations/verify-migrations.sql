-- ============================================================
-- Migration Verification Script
-- Run after migrations to confirm everything is in place.
-- Usage: psql $DATABASE_URL -f verify-migrations.sql
-- ============================================================

do $$
declare
  missing text[] := '{}';
  idx int := 1;
begin
  -- ============================================================
  -- Check required tables
  -- ============================================================
  raise notice 'Checking tables...';

  if not exists (select from pg_tables where schemaname = 'public' and tablename = 'video_jobs') then
    missing := array_append(missing, 'table video_jobs');
  end if;

  if not exists (select from pg_tables where schemaname = 'public' and tablename = 'scenes') then
    missing := array_append(missing, 'table scenes');
  end if;

  if not exists (select from pg_tables where schemaname = 'public' and tablename = 'assets') then
    missing := array_append(missing, 'table assets');
  end if;

  if not exists (select from pg_tables where schemaname = 'public' and tablename = 'chat_sessions') then
    missing := array_append(missing, 'table chat_sessions');
  end if;

  if not exists (select from pg_tables where schemaname = 'public' and tablename = 'chat_messages') then
    missing := array_append(missing, 'table chat_messages');
  end if;

  if not exists (select from pg_tables where schemaname = 'public' and tablename = 'job_stage_runs') then
    missing := array_append(missing, 'table job_stage_runs');
  end if;

  if not exists (select from pg_tables where schemaname = 'public' and tablename = 'regeneration_operations') then
    missing := array_append(missing, 'table regeneration_operations');
  end if;

  if not exists (select from pg_tables where schemaname = 'public' and tablename = 'video_job_events') then
    missing := array_append(missing, 'table video_job_events');
  end if;

  -- Video job events RLS
  if exists (select from pg_tables where schemaname = 'public' and tablename = 'video_job_events') then
    if not exists (
      select from pg_class c
      join pg_namespace n on c.relnamespace = n.oid
      where n.nspname = 'public' and c.relname = 'video_job_events' and c.relrowsecurity
    ) then
      missing := array_append(missing, 'RLS disabled on video_job_events');
    end if;
  end if;

  -- ============================================================
  -- Check required columns on video_jobs
  -- ============================================================
  raise notice 'Checking video_jobs columns...';

  declare
    required_cols text[] := '{
      "id","status","brief_json","script_json","render_manifest",
      "output_url","thumbnail_url","error_message","progress",
      "current_step","created_at","updated_at","completed_at",
      "priority","claimed_by","claimed_at","retry_count","max_retries",
       "last_error","started_at","finished_at","narration_export_style"
    }';
    col text;
  begin
    foreach col in array required_cols loop
      if not exists (
        select from information_schema.columns
        where table_schema = 'public' and table_name = 'video_jobs' and column_name = col
      ) then
        missing := array_append(missing, 'video_jobs.' || col);
      end if;
    end loop;
  end;

  declare
    foundation_cols text[] := '{"lease_token","lease_expires_at","heartbeat_at","attempt_number","max_job_attempts","available_at","pipeline_revision","current_revision","revision_sequence","next_stage","last_completed_stage","failure_class","cancel_requested"}';
    col text;
  begin
    foreach col in array foundation_cols loop
      if not exists (
        select from information_schema.columns
        where table_schema = 'public' and table_name = 'video_jobs' and column_name = col
      ) then
        missing := array_append(missing, 'video_jobs.' || col);
      end if;
    end loop;
  end;

  -- ============================================================
  -- Check required columns on scenes
  -- ============================================================
  raise notice 'Checking scenes columns...';

  declare
    scene_cols text[] := '{
      "id","job_id","scene_index","narration","caption",
      "image_prompt","image_url","local_image_path",
      "duration_seconds","motion","transition","generation_status","pipeline_revision"
    }';
    col text;
  begin
    foreach col in array scene_cols loop
      if not exists (
        select from information_schema.columns
        where table_schema = 'public' and table_name = 'scenes' and column_name = col
      ) then
        missing := array_append(missing, 'scenes.' || col);
      end if;
    end loop;
  end;

  declare
    stage_cols text[] := '{"pipeline_revision","stage","item_key","input_hash","status","run_token","lease_token","provider_attempt_count","tts_attempt_count","renderer_attempt_count","database_retry_count","filesystem_attempt_count"}';
    col text;
  begin
    foreach col in array stage_cols loop
      if not exists (
        select from information_schema.columns
        where table_schema = 'public' and table_name = 'job_stage_runs' and column_name = col
      ) then
        missing := array_append(missing, 'job_stage_runs.' || col);
      end if;
    end loop;
  end;

  -- ============================================================
  -- Check RPC functions
  -- ============================================================
  raise notice 'Checking RPC functions...';

  declare
    rpcs text[] := '{
      "claim_next_video_job",
      "handle_job_error",
      "get_asset_path",
      "get_asset_url",
      "get_asset_key",
      "heartbeat_video_job",
      "begin_job_stage",
      "reserve_stage_external_attempt",
      "finalize_stage_success",
      "fail_job_stage",
      "enqueue_regeneration",
      "request_cancel_video_job",
      "acknowledge_cancel_video_job",
      "reap_expired_video_job_leases",
      "persist_video_job_failure"
    }';
    rpc text;
  begin
    foreach rpc in array rpcs loop
      if not exists (
        select from pg_proc p
        join pg_namespace n on p.pronamespace = n.oid
        where n.nspname = 'public' and p.proname = rpc
      ) then
        missing := array_append(missing, 'function ' || rpc);
      end if;
    end loop;
  end;

  -- ============================================================
  -- Check status constraint covers all lifecycle statuses
  -- ============================================================
  raise notice 'Checking status constraint...';

  declare
    expected_statuses text[] := '{
      "queued","generating_script","script_ready","generating_images",
      "generating_voice","building_captions","building_manifest",
      "rendering","completed","failed","cancelled"
    }';
    constraint_name text;
    constraint_def text;
    checked boolean := false;
  begin
    select cc.conname, pg_get_constraintdef(cc.oid)
    into constraint_name, constraint_def
    from pg_constraint cc
    join pg_class cl on cc.conrelid = cl.oid
    join pg_namespace n on cl.relnamespace = n.oid
    where n.nspname = 'public' and cl.relname = 'video_jobs'
      and cc.conname = 'video_jobs_status_check';

    if constraint_name is null then
      missing := array_append(missing, 'status check constraint (none found)');
    else
      raise notice '  Found constraint: %', constraint_name;
      -- Check each expected status appears in the constraint definition
      for idx in 1 .. array_length(expected_statuses, 1) loop
        if position(expected_statuses[idx] in constraint_def) = 0 then
          missing := array_append(missing, 'missing status: ' || expected_statuses[idx]);
        end if;
      end loop;
    end if;
  end;

  -- ============================================================
  -- Report
  -- ============================================================
  if array_length(missing, 1) is not null then
    raise warning '=== VERIFICATION FAILED ===';
    raise warning 'Missing items:';
    for idx in 1 .. array_length(missing, 1) loop
      raise warning '  %: %', idx, missing[idx];
    end loop;
    raise exception '=== VERIFICATION FAILED ===';
  else
    raise notice '=== VERIFICATION PASSED ===';
    raise notice 'All tables, columns, and functions present.';
    raise notice 'Status constraint covers all lifecycle states.';
  end if;
end;
$$;
