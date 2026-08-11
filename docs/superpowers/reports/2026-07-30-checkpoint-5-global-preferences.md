# Phase 1 Checkpoint 5 Report: Global Application Preferences

## Boundary

Implemented one global application preferences record and backend API only.
HMAC callbacks, Settings UI, Generate UI, Pexels integration, dynamic provider
routing, and n8n workflow changes were not started.

## Files Changed

- `backend/app/clients.py`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/services/ai/provider_registry.py`
- `backend/tests/test_preferences.py`
- `clipcraft/supabase/migrations/010_ai_application_preferences.sql`
- `clipcraft/supabase/run-migrations.sh`
- `docs/superpowers/specs/2026-07-30-phase-1-provider-security-design.md`
- `docs/superpowers/reports/2026-07-30-checkpoint-5-global-preferences.md`

## Migration

- Added and applied `010_ai_application_preferences.sql`.
- Singleton key is `id boolean primary key default true check (id = true)`.
- RLS is enabled.
- Browser roles have no table privileges.
- `service_role` has CRUD privileges.
- Existing timestamp trigger is used.
- Live table contains zero rows after migration.

## Endpoints

- `GET /api/settings/preferences`
- `PUT /api/settings/preferences`

GET returns canonical registry defaults when no row exists. PUT is a full
normalized replacement: omitted values resolve to canonical defaults, while
explicit invalid values are rejected.

## Validation and Tests

Coverage includes:

- Singleton persistence and repeated upserts.
- Canonical default fallback.
- Unknown providers/models.
- Provider/model mismatch.
- Disabled and unimplemented providers.
- Unsupported visual source.
- Invalid Pexels media type/orientation.
- Corrupt persisted preferences.
- Generation remains on existing defaults.
- Legacy compatibility and serialization.
- Secret/environment-value leakage.

Focused preference tests:

```text
13 passed
```

Full backend suite:

```text
84 passed
```

## Compatibility Impact

- Preferences are not read by `POST /api/videos` or any generation path.
- Existing provider defaults remain unchanged.
- Existing provider adapters, n8n payloads, workflows, job snapshots, and
  public API contracts remain unchanged.
- No secrets or environment values are stored or returned.
- GET revalidates persisted values and returns a generic server configuration
  error if stored data is corrupt.

## Unresolved Limitations

- Preferences are persistence-only until a future approved routing/configuration
  checkpoint explicitly wires them into job creation.
- No frontend Settings UI exists yet.
- Pexels and NVIDIA remain unimplemented provider capabilities.
