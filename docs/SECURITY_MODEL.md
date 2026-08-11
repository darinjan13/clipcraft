# Security Model

## Secrets

Known secret-bearing configuration includes:

- `CLOUDFLARE_AI_TOKEN`
- `SUPABASE_SERVICE_ROLE_KEY`
- `INTERNAL_API_KEY`
- `N8N_ENCRYPTION_KEY`
- Public n8n API key used by functional verification

The repository contains an ignored `clipcraft/.env`; its values were not inspected. Never commit or print those values.

## Authentication Boundaries

- n8n public API: `X-N8N-API-KEY` with workflow and execution scopes required by the test suite.
- WF15 download: `X-Internal-Api-Key` checked against `INTERNAL_API_KEY`.
- Supabase: n8n uses `SUPABASE_SERVICE_ROLE_KEY`, which bypasses RLS.
- WF01/WF02 and several public webhooks do not visibly authenticate callers in source.
- Frontend/session authentication is **UNKNOWN**.

## Environment and Container Risks

The primary Compose configuration:

- Uses HTTP rather than HTTPS.
- Allows an empty `N8N_ENCRYPTION_KEY` default.
- Sets `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`.
- Runs n8n as `root`.
- Exposes port `5680` on the host.

These may be acceptable for local development but are not established as production-safe.

## Data Exposure Risks

- Public workflows may expose job access without demonstrated user binding.
- Service-role access is broad and workflow-side authorization is not fully evidenced.
- Execution data may contain prompts, provider request objects, or response content.
- n8n execution pruning is configured, but retention and redaction policy is not documented.
- Local job files contain generated media and logs.
- Error handling must not return provider response bodies, tokens, filesystem paths, or raw Supabase errors.

## Input and File Protections

WF15 validates UUIDs, rejects path traversal, and uses an asset allowlist. `asset_paths.py` also validates UUIDs and asset types. These protections should remain covered by tests.

## Recommended Mitigations

- Require and rotate a nonempty n8n encryption key.
- Put n8n and download traffic behind TLS and an authenticated frontend/proxy.
- Replace broad public webhook access with user/session authorization and job ownership checks.
- Add explicit RLS policies or document why all access is intentionally service-role-only.
- Run n8n as a non-root user where volume ownership permits.
- Set `N8N_BLOCK_ENV_ACCESS_IN_NODE=true` unless a reviewed workflow requires otherwise.
- Establish secret rotation, exposure response, and backup encryption procedures.
- Define execution-data retention and redaction requirements.
- Add security tests for every public webhook.
