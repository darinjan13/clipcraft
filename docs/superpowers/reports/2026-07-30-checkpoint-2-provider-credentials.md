# Phase 1 Checkpoint 2 Report: Provider Credentials

## Boundary

Implemented global provider credential storage and masking only. Connection
testing, global preferences, job snapshots, HMAC callbacks, UI, and n8n routing
were not started.

## Files Changed

- `backend/app/clients.py`
- `backend/app/main.py`
- `backend/app/models.py`
- `backend/tests/test_credential_crypto.py`
- `backend/tests/test_provider_credentials.py`
- `clipcraft/supabase/migrations/007_ai_provider_credentials.sql`
- `docs/superpowers/specs/2026-07-30-phase-1-provider-security-design.md`
- `docs/superpowers/reports/2026-07-30-checkpoint-2-provider-credentials.md`

## Migration

- Added and applied `007_ai_provider_credentials.sql`.
- The live table has zero rows, unique `provider_id`, RLS enabled, controlled
  status/test-status checks, and the existing `set_updated_at()` trigger.
- No existing job rows or columns were changed.

## Endpoints

- `GET /api/ai/credentials`
- `GET /api/ai/credentials/{provider_id}`
- `PUT /api/ai/credentials/{provider_id}`
- `DELETE /api/ai/credentials/{provider_id}`

Responses expose provider ID, configured/enabled state, status, last four
characters, and safe test metadata only.

## Tests

- One-record-per-provider masking and encryption
- Atomic replacement metadata reset
- Idempotent deletion
- Missing encryption key fail-closed behavior
- Canonical provider validation
- Secret absence from responses and stored fields
- AES-GCM crypto regression coverage

Focused tests:

```text
11 passed
```

Full backend suite:

```text
54 passed
```

## Compatibility Impact

- Existing environment-based provider credentials remain the only credentials
  used by generation.
- Stored credentials are not read by adapters yet.
- Existing provider defaults, n8n payloads, workflows, job rows, and generation
  sequence are unchanged.
- No frontend or Settings UI changes were made.

## Unresolved Risks

- Stored credentials are not yet used for provider connection tests or
  generation; that is Checkpoint 3 and later routing work.
- The local backend test suite uses a fake database client for CRUD behavior;
  the live migration shape was verified separately through Supabase schema
  inspection.
