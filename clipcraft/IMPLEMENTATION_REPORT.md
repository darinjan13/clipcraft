# ClipCraft AI — Implementation Report

## Overview

| Metric | Value |
|--------|-------|
| Workflows | 18 |
| Total nodes | 192 |
| Supabase migrations | 3 |
| Video processing pipeline | 9 sub-workflows |
| API endpoints | 8 |
| Internal sub-workflows | 3 (WF16–WF18) |

## Architecture

```
WF01 Chat → WF02 Create Job → WF03 Queue Poller
                                    ↓
              ┌── WF04 Generate Script (via WF17 AI Text)
              │── WF05 Generate Images (via WF18 AI Image)
              │── WF06 Generate Narration (TTS)
              │── WF07 Build Captions
              │── WF08 Build Manifest (via WF16 Resolve Paths)
              │── WF09 Render Video
              │
              └── WF14 Error Handler (retry logic)

API: WF10 Status, WF11 Result, WF12 Regenerate Scene,
     WF13 Regenerate Video, WF15 Download Asset
```

## Files Created

| File | Purpose |
|------|---------|
| `supabase/migrations/002_add_job_claiming.sql` | Atomic job claim + retry tracking |
| `supabase/migrations/003_asset_path_functions.sql` | `get_asset_path()` + `get_asset_url()` |
| `video-tools/asset_paths.py` | Canonical Python path generator |
| `workflows/16-resolve-asset-paths.json` | Internal asset path resolution |
| `workflows/17-ai-generate-text.json` | Provider-abstracted AI text |
| `workflows/18-ai-generate-image.json` | Provider-abstracted AI image |
| `tests/test_asset_paths.py` | Cross-implementation path tests |
| `workflows/README.md` | Workflow index and conventions |
| `supabase/run-migrations.sh` | Idempotent migration runner (supabase CLI or direct psql) |
| `supabase/migrations/verify-migrations.sql` | Verifies all tables, columns, RPCs, and status constraints |

## Files Modified

| File | Changes |
|------|---------|
| `workflows/03-video-job-worker.json` | Uses `claim_next_video_job` RPC |
| `workflows/04-generate-script-and-scenes.json` | Calls WF17 instead of direct Cloudflare |
| `workflows/01-chat-message.json` | Calls WF17 instead of direct Cloudflare |
| `workflows/05-generate-scene-images.json` | Calls WF18 instead of direct Cloudflare |
| `workflows/12-regenerate-scene.json` | Calls WF18 instead of direct Cloudflare |
| `workflows/14-error-handler.json` | Uses `handle_job_error` RPC |
| `shared-contract.md` | Canonical asset map, internal workflow contracts |
| `.env`, `.env.example` | AI provider env vars |
| `docker-compose.yml` | AI provider env vars |

## Key Design Decisions

1. **Atomic claiming via `FOR UPDATE SKIP LOCKED`** — prevents race conditions between multiple workers
2. **Provider-abstracted AI** — only WF17/WF18 call AI providers; env var routing
3. **Canonical asset map** — shared across PostgreSQL, Python, n8n (WF16); tested via `test_asset_paths.py`
4. **Retry tracking** — `retry_count` / `max_retries` with automatic re-queue vs. permanent failure

## Validation Results

| Test | Status | Notes |
|------|--------|-------|
| Asset path equivalence (13 tests) | ✓ All passed | Python, WF16, canonical map all agree |
| Workflow validation (WF01-WF18) | ✓ 0 violations | 18 workflows, 192 nodes, all IDs unique |
| Webhook uniqueness | ✓ All unique | No duplicate paths |
| Secret scan | ✓ Clean | No hardcoded secrets |
| `docker compose config` | ✓ Valid | No errors |
| `asset_paths.py` import in container | ✓ 3/3 passed | Works via `PYTHONPATH=/opt/video-tools` |
| Render test (3 scenes, 12s) | ✓ All passed | 77s duration, full zoompan/audio/subtitle pipeline |

## Container Configuration Changes

| Change | Reason |
|--------|--------|
| `user: root` in docker-compose.yml | Volume permissions: `node` user (UID 1000) can't write to root-owned Docker volume at `/home/node/.n8n` |
| `PYTHONPATH=/opt/video-tools` in env | Allows `import asset_paths` from any working directory |
| `ENV PYTHONPATH=/opt/video-tools` in Dockerfile | Bakes in path for freshly-built images |
## Remaining

- **Credentialed end-to-end tests** — requires Supabase credentials and running stack with real data
- **Supabase migrations** — apply via `./supabase/run-migrations.sh` (requires `DATABASE_URL` or `supabase` CLI linked to project)
- **Migration trigger** — wire migration into deployment workflow (e.g., GitHub Actions or post-deploy hook)
