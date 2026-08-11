# Operations

## Evidence Boundary

Only commands explicitly present in repository documentation are recorded as confirmed. No operational command was executed during onboarding.

## Local Stack

The primary stack is defined by `clipcraft/docker-compose.yml` and contains:

- `clipcraft-n8n`, exposed as host port `5680` to container port `5678`.
- `clipcraft-tts`, internal port `8000`.
- Persistent volumes for n8n, jobs, music, fonts, and TTS models.

The repository documents starting the stack with:

```sh
docker compose up -d
```

The exact working directory and whether images must be built first depend on the local development process and are not fully standardized. This local Compose stack is the canonical runtime; no production or deployment environment is assumed.

## Environment Configuration

Use `clipcraft/.env.example` as the variable inventory. The actual `.env` is environment-specific and must not be changed by routine maintenance. Required operational values include Cloudflare, Supabase, internal API, n8n, and TTS settings; exact production values are UNKNOWN.

Configuration discovery found the primary local URL in `clipcraft/.env`: `N8N_PROTOCOL=http`, `N8N_HOST=localhost`, `N8N_PORT=5678`, and `N8N_EDITOR_BASE_URL=http://localhost:5680`. The Compose mapping exposes container port `5678` as host port `5680`. The n8n Public API key is local runtime configuration, but it was not found in `.env`, `.env.example`, or the inspected tooling. Existing scripts use cookie authentication through undocumented `/rest` endpoints and are not an approved substitute. Once the local API key is configured, discover local runtime workflow IDs from n8n rather than using repository IDs.

## Health Checks

The Compose file defines:

- n8n healthcheck: `http://localhost:5678/healthz` inside the n8n container.
- TTS healthcheck: `http://localhost:8000/health` inside the TTS container.

Public webhook health and Supabase health procedures are not formally documented.

## Database Migrations

The primary repository documents:

```sh
./supabase/run-migrations.sh
```

The script supports a `DATABASE_URL`/`psql` path or a linked Supabase CLI path. It applies the three primary migrations and has a verification SQL file. Migration execution was not performed. Which database is authoritative and whether migrations are already applied are UNKNOWN.

## Local Workflow Runtime

Workflow import and activation are referenced in older README files and root operational scripts. There is no authoritative, safe, reproducible local workflow import command for the primary 18-workflow tree. Do not run root mutation scripts without an explicit reviewed change and runtime approval.

## Functional Verification

The approved sequence is:

1. Validate explicit configuration.
2. Retrieve and verify target workflow identity through the public API.
3. Create disposable parent workflow.
4. Invoke approved test cases.
5. Inspect correlated child executions.
6. Deactivate, delete, and verify deletion.

`functional_tests.py` must not be executed until runtime approval is granted.

## Backup and Recovery

Historical workflow exports and SQLite backup files exist under `backups/`. A formal local-development backup selection, restore, and encryption process is **UNKNOWN**. Deployment rollback is not currently applicable. Do not delete or overwrite backup generations.

## Monitoring and Recovery

No production monitoring, alerting, log aggregation, incident response, or secret rotation configuration was found. These are required before production-readiness can be claimed.
