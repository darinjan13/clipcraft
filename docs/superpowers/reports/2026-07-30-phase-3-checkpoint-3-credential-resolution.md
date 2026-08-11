# Phase 3 Checkpoint 3: Credential Resolution

## Status

Implemented and verified as an isolated internal service. Live generation does not use the resolver.

## Files Changed

- `backend/app/config.py`
- `backend/app/services/ai/credential_resolution.py`
- `backend/tests/test_credential_resolution.py`

No frontend files, database migrations, FastAPI routes, n8n workflows, provider adapters, or execution paths were changed.

## CredentialResolver Interface

`CredentialResolver.resolve()` accepts a validated `RoutingDecision`, an optional explicit credential strategy, and an optional provider ID for multi-provider execution contexts.

It returns `ResolvedProviderCredential`, which contains:

- provider ID
- credential strategy
- redacted `SecretStr` secret held in memory
- optional Cloudflare account ID
- in-memory updated-at marker

Provider mismatches are rejected before credential-store access. No generic serialization or `to_dict` method is provided.

## Supported Strategies

### Environment

- Gemini uses existing `GEMINI_API_KEY`.
- Cloudflare uses existing `CLOUDFLARE_AI_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` names.
- Pexels fails safely as unconfigured because no existing Pexels environment variable is defined in the repository; no variable was invented.
- NVIDIA returns `not_implemented` because no credential environment shape exists.

### Stored

- Loads the existing encrypted credential row through `get_credential_for_test`.
- Requires enabled/configured status.
- Decrypts only in process memory using the existing AES-256-GCM service.
- Uses encrypted `account_id` metadata for Cloudflare.
- Supports stored Gemini, Cloudflare, and Pexels credentials.
- Never falls back to environment credentials.

Environment resolution never reads the credential database, and stored resolution never falls back to environment values.

## Provider Credential Shapes

- Gemini: API key only.
- Cloudflare: API token plus account ID metadata.
- Pexels: API key only for stored credentials; environment source is deferred pending an approved existing variable.
- NVIDIA: not implemented without an established credential shape.

## Internal ExecutionContext

`ExecutionContext` is an immutable internal dataclass containing:

- validated `RoutingDecision`
- a tuple of resolved in-memory provider credentials
- optional safe job ID
- timeout policy value

`build_execution_context()` resolves text credentials, AI image credentials when required, and Pexels credentials for a Pexels visual source. Duplicate provider credentials are resolved once. The context is not returned by FastAPI, stored in jobs, placed in `brief_json`, or passed to n8n.

Secrets are excluded from normal dataclass repr and safe string/JSON fallback output through `SecretStr` and hidden dataclass fields.

## Error Model

Internal errors use `CredentialResolutionError` with safe codes such as:

- `unknown_provider`
- `unsupported_provider`
- `credential_missing`
- `credential_configuration_error`
- `credential_decryption_error`
- `credential_source_invalid`
- `provider_metadata_missing`
- `encryption_key_missing`
- `provider_mismatch`
- `not_implemented`

Messages contain no secret values, ciphertext, environment values, database bodies, or chained raw exception details.

## Rotation And Concurrency

Resolution reads one credential row and decrypts that row atomically for the resolution attempt. Its safe `updated_at` marker is retained only in memory. There is no global decrypted-credential cache, no cross-request reuse, no restoration of deleted credentials, and no job snapshot mutation. A replacement after resolution affects later resolutions, not the already-created in-memory context.

## Live Generation Usage

The resolver is not imported or called by `POST /api/videos`, the worker, provider adapters, or n8n. Current generation continues using the existing environment-based path. Stored credentials remain limited to the existing Settings connection-test flow.

## n8n Payload Compatibility

No n8n workflow files or payload construction changed. No secrets or credential contexts are sent through existing n8n webhooks, workflow inputs, job payloads, or execution metadata by this checkpoint.

## brief_json Compatibility

`brief_json` construction is unchanged. No credential values, ciphertext, account metadata, credential source changes, or execution context fields are added.

## Verification

- Focused credential, crypto, credential CRUD, connection-test, and routing tests: `46 passed`.
- Full backend suite: `119 passed` via `pytest backend/tests -q`.
- Frontend production build: `npm run build` passed.
- Resolver tests run with `-s`: `15 passed` with no secret-bearing output.
- Production application-source scans found no test secrets, ciphertext literals, or credential assignments in `backend/app` or `frontend/src`.
- No database migration was added.

## Security Review

The new resolver passed isolated security review for redaction, no fallback, no cache, safe errors, no persistence, and no provider/network calls. Settings secret fields now omit values from dataclass repr. Existing repository-wide risks remain: the checked-in runtime `.env`, utility scripts with credential-like material, and existing n8n execution-data handling require separate rotation and hardening work.

## Compatibility Review

Read-only compatibility review confirmed:

- `POST /api/videos` is unchanged.
- Generate frontend behavior is unchanged.
- Snapshots, `brief_json`, public responses, and Settings credential tests are unchanged.
- Existing provider execution remains in n8n.
- No workflow, callback, authentication, or multi-user changes were made.

## Unresolved Limitations

- The resolver is intentionally not connected to runtime execution.
- Cloudflare availability and runtime credentials remain governed by the existing n8n environment path.
- No approved existing Pexels environment variable is present, so only stored Pexels resolution is available.
- Existing n8n workflows may retain provider secrets in execution data; fixing that requires a separate workflow/security checkpoint.
- The workspace is not a Git repository, so VCS-based baseline diff verification was unavailable.
