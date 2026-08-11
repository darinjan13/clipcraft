-- AI Video Factory — Centralized asset path generation
-- Prerequisite: 002_add_job_claiming.sql
-- Single source of truth for all file paths.
-- All n8n workflows call get_asset_path() via RPC instead of constructing paths inline.

-- ============================================================
-- get_asset_path(job_id uuid, asset_type text, scene_index int default null)
-- Returns a JSON object with the constructed local filesystem path.
-- ============================================================
create or replace function public.get_asset_path(
  job_id uuid,
  asset_type text,
  scene_index int default null
)
returns jsonb
language plpgsql
stable
as $$
declare
  base_path text := '/data/jobs/' || job_id || '/';
  result_path text;
begin
  case asset_type
    when 'scene' then
      if scene_index is null then
        raise exception 'scene_index is required for asset_type=scene';
      end if;
      result_path := base_path || 'scene-' || lpad(scene_index::text, 2, '0') || '.png';
    when 'narration' then
      result_path := base_path || 'narration.wav';
    when 'captions' then
      result_path := base_path || 'captions.ass';
    when 'manifest' then
      result_path := base_path || 'render-manifest.json';
    when 'video' then
      result_path := base_path || 'final.mp4';
    when 'thumbnail' then
      result_path := base_path || 'thumbnail.jpg';
    when 'render_log' then
      result_path := base_path || 'render.log';
    when 'error_log' then
      result_path := base_path || 'error.log';
    else
      raise exception 'Unknown asset_type: %', asset_type;
  end case;

  return jsonb_build_object(
    'path', result_path,
    'filename', substring(result_path from '[^/]+$'),
    'job_id', job_id,
    'asset_type', asset_type
  );
end;
$$;

-- ============================================================
-- get_asset_url(job_id uuid, asset_type text, base_url text default '/webhook/videos/download')
-- Returns the download URL for an asset (for public API responses).
-- Used by WF11 to build download URLs without constructing paths inline.
-- ============================================================
create or replace function public.get_asset_url(
  job_id uuid,
  asset_type text,
  base_url text default '/webhook/videos/download'
)
returns text
language plpgsql
stable
as $$
begin
  if asset_type not in ('video', 'thumbnail', 'captions') then
    raise exception 'Asset type % is not downloadable via webhook', asset_type;
  end if;
  return base_url || '?jobId=' || job_id || '&asset=' || asset_type;
end;
$$;
