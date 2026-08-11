# Phase 1 Checkpoint 4 Report: Job Configuration Snapshots

## Boundary

Implemented non-secret job configuration snapshots only. Global preferences,
HMAC callbacks, Settings UI, Generate-page changes, Pexels workflows, NVIDIA
routing, provider switching, and n8n routing were not started.

## Read-Only Reviews

- Schema audit confirmed `video_jobs` exists with the existing status/check/
  timestamp triggers and that nullable text columns are additive.
- Compatibility review confirmed existing API responses, `brief_json`, n8n
  payloads, provider defaults, and legacy jobs remain compatible.

## Files Changed

- `backend/app/clients.py`
- `backend/app/main.py`
- `backend/app/services/ai/provider_registry.py`
- `backend/tests/test_api.py`
- `clipcraft/supabase/migrations/009_video_job_configuration_snapshots.sql`
- `clipcraft/supabase/run-migrations.sh`
- `docs/superpowers/specs/2026-07-30-phase-1-provider-security-design.md`
- `docs/superpowers/reports/2026-07-30-checkpoint-4-job-snapshots.md`

## Migration

- Added and applied `009_video_job_configuration_snapshots.sql`.
- Added nullable text columns:
  - `text_provider`
  - `text_model`
  - `visual_source`
  - `image_provider`
  - `image_model`
  - `credential_source`
  - `provider_configuration_version`
- No historical backfill or destructive operation was performed.
- Live verification found 42 existing jobs and zero snapshotted historical jobs.

## Endpoints

- No endpoints added or changed.
- Snapshot fields are deliberately excluded from `Video` and status responses.

## Tests Added or Updated

- Default snapshot persistence.
- Explicit provider/model snapshot persistence.
- Snapshot exclusion from public API responses.
- Rename preservation.
- Regeneration and duplication snapshot copying.
- Legacy rows without snapshots remain readable.
- Additive migration and non-secret column checks.

Focused snapshot/API/registry tests:

```text
44 passed
```

Full backend suite:

```text
71 passed
```

## Compatibility Impact

- `brief_json` remains unchanged and remains the n8n generation input contract.
- Existing generation defaults remain unchanged.
- Existing n8n payloads and workflows remain unchanged.
- Existing environment-based credentials remain active.
- Legacy jobs and legacy n8n-created rows remain readable with null snapshots.
- Derived jobs copy complete existing snapshots; incomplete legacy source data
  is not given invented historical metadata.
- Snapshot values contain only provider/model/source/version strings and no
  plaintext credentials, ciphertext, or headers.

## Unresolved Limitations

- Snapshots are audit metadata only; generation still uses `brief_json`.
- Existing legacy jobs remain unsnapshotted by design.
- Global preference resolution is the next checkpoint.
