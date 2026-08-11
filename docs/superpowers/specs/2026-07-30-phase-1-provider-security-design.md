# ClipCraft Phase 1 Provider Security Design

## Scope

ClipCraft is permanently a single-user, self-hosted application. It does not
support multiple accounts, shared workspaces, account ownership, or user-scoped
resources. Browser-facing FastAPI routes may remain unauthenticated by design,
but application services must bind to localhost or a private network and must
not be exposed publicly.

Phase 1 establishes secure local provider credentials, a dynamic provider/model
registry, global application preferences, provider connection testing, job-time
provider snapshots, safe FastAPI-to-n8n boundaries, secret redaction, and
compatibility with the existing generation pipeline.

Phase 1 does not change the Generate UI, Settings UI, Pexels implementation,
NVIDIA generation, dynamic n8n provider routing, or the current generation
sequence.

Implementation will be split into independently verifiable checkpoints:

1. Document and test the current local application/data flow and deployment
   exposure.
2. Add encryption primitives and a versioned credential envelope.
3. Add the provider/model registry and global preference resolution.
4. Add one-record-per-provider credential CRUD, masking, and safe errors.
5. Add provider connection tests with transient decryption and redaction.
6. Add provider/model/visual-source/credential-reference job snapshots while
   preserving environment-based provider compatibility.
7. Add the signed n8n callback boundary, security tests, and a final review.

Each checkpoint must pass its focused tests before the next begins. No
migrations or production behavior changes begin until this revised
specification is approved.

### Checkpoint 1 implementation notes

- The encryption service is standalone and has no database, API, provider, or
  n8n dependency.
- `AI_CREDENTIAL_ENCRYPTION_KEY` is loaded as strict base64 and must decode to
  exactly 32 bytes. Missing or invalid values raise a safe configuration error;
  no runtime key generation or fallback exists.
- The envelope format is
  `cc-aes-gcm:v1:<key-version>:<base64url(nonce)>:<base64url(ciphertext+tag)>`.
- AES-GCM receives associated data
  `clipcraft-credential-v1\\n<provider_id>` so ciphertext cannot be moved
  between providers.
- The current checkpoint changes no schema, endpoint, job payload, provider
  default, workflow, or generation behavior.

### Checkpoint 2 implementation notes

- Additive migration `007_ai_provider_credentials.sql` creates one global row
  per canonical `provider_id`; it does not alter or backfill existing jobs.
- Credential CRUD uses the narrow `DatabaseClient` credential methods and the
  AES-GCM service from Checkpoint 1.
- API responses contain masked metadata only. Replacement uses an atomic
  provider-keyed upsert and clears prior test metadata without starting a
  connection test.
- Stored credentials are not read by provider adapters in this checkpoint.
  Existing environment-based credentials and generation defaults therefore
  remain unchanged.

### Checkpoint 3 implementation notes

- `POST /api/ai/credentials/{provider_id}/test` tests only the stored
  credential record; it never falls back to environment credentials.
- Provider test adapters make at most one low-cost request with a five-second
  timeout and return fixed normalized statuses/messages. Raw provider bodies,
  authorization headers, and plaintext credentials are never returned or
  logged.
- Gemini tests use a lightweight model-list request. Cloudflare tests use an
  account/model metadata request and require encrypted `account_id` metadata.
  Pexels uses a one-item curated request. NVIDIA remains safely
  `not_implemented` because no supported adapter exists in the codebase.
- Test metadata is persisted only when the original `updated_at` and encrypted
  ciphertext still match. Deletion or replacement during a test results in no
  stale metadata write.

### Checkpoint 4 implementation notes

- Add nullable text columns to `public.video_jobs`: `text_provider`,
  `text_model`, `visual_source`, `image_provider`, `image_model`,
  `credential_source`, and `provider_configuration_version`.
- New API-created jobs receive a snapshot of the already-resolved provider/model
  selections. Existing rows, legacy n8n-created rows, and historical data are
  not backfilled.
- `brief_json` remains the generation input contract and is not changed. The
  snapshot is audit metadata only; workers and n8n continue using existing
  fields and payloads.
- Snapshots contain only provider, model, source, credential-source, and
  configuration-version strings. No credential plaintext or ciphertext is
  stored.

### Checkpoint 5 implementation notes

- Add singleton table `public.ai_application_preferences` with boolean key
  `id = true`; no `user_id` or per-provider rows are used.
- GET returns persisted values when present and canonical current defaults when
  the singleton row is absent.
- PUT validates provider/model capability selections through the canonical
  registry and validates visual/Pexels preference values without changing
  generation resolution.
- PUT is a full normalized replacement: omitted fields resolve to canonical
  defaults, while explicitly supplied invalid values are rejected. GET
  revalidates persisted values and fails safely if stored configuration is
  corrupt.
- Preferences are configuration-only in this checkpoint. `POST /api/videos`,
  job snapshots, provider adapters, n8n payloads, and workflows continue using
  existing environment/registry defaults.
- The preferences table is backend service-role-only with RLS enabled and no
  browser-role grants.

## Approved Single-User Decisions

### Application boundary

- No Supabase Auth, JWT verification, JWKS cache, bearer-token requirement,
  `get_current_user` dependency, owner column, cross-user authorization, or
  user-scoped credential/preference model is part of Phase 1.
- The browser may call FastAPI without user authentication because the product
  is single-user and self-hosted.
- FastAPI, n8n, Supabase, and the renderer must not be publicly exposed.
  Docker/service ports bind to localhost or a configured private interface by
  default; deployment documentation must call out any intentional exposure.
- The Supabase service-role key remains backend/n8n-only. It is never sent to
  the browser or included in API errors.

### Global credential model

- There is one credential record per provider, with no `user_id`, owner field,
  or account relationship.
- Credentials are encrypted at rest with AES-256-GCM.
- API responses expose only provider ID, configured/enabled status, last four
  characters, last test metadata, and safe status/error fields.
- Plaintext secrets are never stored in jobs, logs, events, normal API
  responses, browser localStorage/sessionStorage, n8n environment variables,
  or n8n execution data.
- Settings may later replace or delete a provider credential. Confirmation is a
  frontend UX concern, not an API authorization mechanism.

### Global preference model

- There is one global application settings record, with no user ownership
  fields.
- It stores default text provider/model, visual source, image provider/model,
  and future Pexels media type/orientation defaults.
- A singleton constraint prevents duplicate preference rows.

### Internal callback authentication

- n8n callbacks use HMAC-SHA256 with the dedicated
  `N8N_CALLBACK_SIGNING_SECRET`.
- Required headers are `X-ClipCraft-Timestamp`, `X-ClipCraft-Nonce`, and
  `X-ClipCraft-Signature`.
- The signature is the lowercase hex HMAC-SHA256 digest over the exact bytes of:
  `timestamp + "\\n" + nonce + "\\n" + raw request body`.
- Verification uses constant-time comparison and rejects timestamps outside a
  five-minute tolerance.
- Nonces use a dedicated replay-protection table/cache with atomic insertion,
  a unique nonce constraint, and expiry. A duplicate nonce is rejected.
- Static internal keys without replay protection and unsigned callback headers
  are not accepted.

### Encryption-key behavior

- `AI_CREDENTIAL_ENCRYPTION_KEY` is a cryptographically random 32-byte key,
  base64-encoded in the environment or secrets manager.
- It is validated during application startup when present. It is never
  automatically generated, committed to the repository, or replaced with a
  placeholder/default key.
- The application may start without the key so existing environment-based
  generation remains available. Credential save, replacement, decryption, and
  connection-test operations fail closed when it is missing or invalid.
- The versioned envelope is defined before records are written:
  `cc-aes-gcm:v1:<key-version>:<base64url(nonce)>:<base64url(ciphertext+tag)>`.
- AES-GCM uses a 12-byte random nonce and associated data
  `clipcraft-credential-v1\\n<provider_id>`. The key version is retained for
  controlled rotation.

### Service-role handling

- Backend Supabase access remains centralized in narrowly scoped client methods.
- User-facing routes must not introduce generic unrestricted mutation helpers;
  each operation must name its intended table and allowed fields even though
  this is a single-user application.
- Service-role headers are redacted from logs. Raw service-role/database errors
  are normalized before reaching the browser.
- Existing RLS configuration is not repurposed for user ownership. RLS is not
  treated as the application authorization model for this single-user product.

### n8n environment-access risk

- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` remains an unresolved risk because Code
  nodes can access environment secrets. Before a later phase, assess whether it
  can be changed to `true` without breaking workflows.
- Until that assessment, do not add BYOK secrets to n8n environment variables,
  normal workflow input, or execution output. Document execution-data retention
  and secret-redaction risks.

### Audit logging boundaries

Security audit events may record credential configured, replaced, deleted,
connection test attempted/completed, normalized test status, and callback
rejection. They must never record plaintext credentials, ciphertext,
authorization headers, complete provider response bodies, or decrypted
metadata.

## Current Flow Map

### Frontend to FastAPI

- The frontend calls `http://127.0.0.1:8000` through
  `frontend/src/features/videos/api/videoService.ts`.
- Requests currently have no browser authentication, which is intentional for
  the single-user local deployment.
- `POST /api/videos` sends the raw `VideoDraft` to FastAPI.
- Provider secrets are not currently sent by the frontend; future credential
  writes belong to dedicated Settings operations and must use masked responses.

### FastAPI to Supabase

- `backend/app/clients.py` uses `SUPABASE_URL` and
  `SUPABASE_SERVICE_ROLE_KEY` for REST requests.
- The service-role key is used for reads and writes and bypasses normal RLS
  enforcement.
- `video_jobs`, `scenes`, `assets`, and event tables are queried directly
  through REST.
- Several existing lifecycle RPCs are bypassed by direct PATCH/DELETE
  operations.

### FastAPI to n8n

- `WorkflowClient` can call n8n webhooks, but `POST /api/videos` currently
  inserts the job directly and does not dispatch through
  `WorkflowClient.create_job`.
- Status and result reads call n8n webhooks on demand.
- No authenticated inbound n8n callback endpoint currently exists.

### n8n to Supabase

- n8n uses environment-held service-role credentials in HTTP Request nodes.
- Queue and stage workflows call Supabase RPCs and REST endpoints directly.
- n8n receives job/provider selections and opaque credential references, never
  decrypted provider secrets.

## A. Provider Registry and Preferences

- The backend owns one reviewed provider/model registry with capabilities,
  required credential type, supported visual sources, and availability state.
- Each provider entry has `provider_id`, `display_name`, `provider_type`,
  `capabilities`, `requires_credential`, `credential_type`, `enabled`,
  `implemented`, `models`, and `default_model`.
- Each model entry has `model_id`, `display_name`, `capability`, `implemented`,
  `enabled`, `deprecated`, and optional description/context metadata.
- Provider and model IDs remain separate raw strings. Model IDs are never
  rewritten into `provider:model`; IDs containing colons remain unchanged.
- The read-only API exposes `/api/ai/providers`,
  `/api/ai/providers/{provider_id}`, and `/api/ai/models` with optional
  `capability` and `provider_id` filters. Responses include safe availability
  metadata only and never include credentials or environment values.
- Model IDs remain registry-validated because catalogs can change.
- The frontend consumes registry/availability metadata and must not own hardcoded
  provider arrays in a later UI phase.
- Global preferences resolve defaults for text provider/model, visual source,
  image provider/model, and future Pexels defaults.
- Saved job snapshots remain readable when a model becomes deprecated or
  unavailable.

### Current registry entries

| Provider | Type | Capabilities | Implemented | Models |
|---|---|---|---|---|
| `gemini` | text | text, image | text only | `gemini-2.5-flash`; planned `gemini-2.5-flash:image-preview` |
| `cloudflare` | text | text, image | text and image | `@cf/meta/llama-3.1-8b-instruct`; `@cf/black-forest-labs/flux-1-schnell` |
| `nvidia` | text | text, image | planned | planned NVIDIA text and image model IDs |
| `pexels` | stock_media | stock_media | planned | no model ID; stock search is not model-based |

Implemented status describes backend support, not whether an environment-based
credential is configured. A provider/model can be present in the registry and
remain unavailable until its implementation or credential configuration exists.

### Adding future providers and models

1. Add one immutable provider entry to the canonical registry.
2. Add model entries under that provider using raw provider-native model IDs.
3. Set `implemented`, `enabled`, and `deprecated` explicitly; do not infer
   availability from an API key or environment value in registry metadata.
4. Add validation and response tests, including provider/model mismatch and
   secret-leakage assertions.
5. Add an adapter only when the provider is implemented. Do not change existing
   job payload field names or defaults as part of registry-only work.

## B. Credential-Security Design

### Storage

- Store one row per provider in `ai_provider_credentials`.
- Store `encrypted_secret`, optional encrypted provider metadata, last four
  characters, enabled state, status, test timestamps, safe test status, and
  `updated_at`.
- Never store plaintext provider secrets, authorization headers, or decrypted
  provider metadata.
- A unique provider ID constraint prevents duplicate credential rows.

### API masking

- List/get returns provider ID, configured/enabled state, last four characters,
  last-tested timestamp/status, and safe error metadata only.
- Create/replace accepts a new plaintext secret over the local/private API,
  encrypts it immediately, and returns masked metadata only.
- Replacement atomically encrypts the new value, updates metadata, and
  invalidates prior test status.
- Delete removes encrypted secret and metadata and is idempotent for the one
  global record.

### Connection tests

- Decrypt only immediately before a provider test and hold plaintext only for
  the shortest possible scope.
- Use short timeouts and minimal non-expensive requests.
- Never include authorization headers or raw provider response bodies in logs or
  API errors.
- Persist only normalized status and a safe error code/message.

### Key rotation

- New writes use the active encryption key version.
- Existing rows retain their key version.
- Rotation is a separate controlled operation that decrypts/re-encrypts
  server-side and never returns secrets.
- Changing the active key before a rotation operation exists is a documented
  breaking operational action and must not be silently attempted.

## C. Database Migration Plan

### `ai_provider_credentials`

- `id uuid primary key default gen_random_uuid()`
- `provider_id text not null unique`
- `encrypted_secret text not null`
- `encrypted_metadata text null`
- `secret_last_four text null`
- `enabled boolean not null default true`
- `status text not null default 'unconfigured'`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- `last_tested_at timestamptz null`
- `last_test_status text null`
- `last_test_error_safe text null`

### `ai_application_preferences`

- `id boolean primary key default true check (id = true)`
- `default_text_provider text null`
- `default_text_model text null`
- `default_visual_source text null`
- `default_image_provider text null`
- `default_image_model text null`
- `default_pexels_media_type text null`
- `default_pexels_orientation text null`
- `updated_at timestamptz not null default now()`

### Integrity constraints

- Add CHECK constraints for credential status, enabled state where relevant,
  credential source, visual source, supported Pexels media types/orientations,
  and connection-test status.
- Model IDs remain registry-validated rather than frozen in database CHECK
  constraints.
- Add `updated_at` triggers or ensure every update path sets timestamps.

### Job snapshots

Add nullable compatibility columns to `video_jobs` for:

- `text_provider`
- `text_model`
- `visual_source`
- `image_provider`
- `image_model`
- `pexels_media_type`
- `pexels_orientation`
- `credential_source`
- `credential_reference`
- `provider_configuration_version`

Snapshots contain provider/model/source selections and an opaque credential
reference only. They never contain decrypted credentials. Existing rows remain
readable because new columns are nullable and environment-based provider
defaults remain available to the n8n path.

Do not remove, convert, or repurpose the existing nullable `video_jobs.user_id`
column during Phase 1. It is legacy compatibility data, not an ownership model.

### RLS and exposure

- Do not add user-ownership RLS policies or an owner column.
- Keep database tables inaccessible to the browser except through the backend
  service boundary.
- Verify required tables are intentionally exposed to the backend Data API and
  not accidentally exposed to public browser clients.

## D. FastAPI-to-n8n Service Boundary

- Browser-facing FastAPI routes may remain unauthenticated only because the app
  is single-user and network-restricted.
- Internal callback endpoints are separate from browser routes and require the
  HMAC signature, timestamp, and nonce rules above.
- Callback payloads are normalized before persistence; secrets, authorization
  headers, and complete provider responses are discarded.
- n8n receives safe provider selections and opaque credential references only.
- Decrypted provider credentials must not be inserted into n8n execution input,
  events, or callbacks.

## E. Testing Plan

### Credential security

- AES-GCM round trips plaintext only in memory and rejects tampered envelopes.
- Missing/invalid encryption key fails closed for credential operations while
  non-BYOK generation remains available.
- Save/replacement never returns or persists plaintext.
- Masked responses contain last-four metadata only.
- Delete is idempotent and removes encrypted material.
- Connection tests use short timeouts and persist only safe normalized results.

### Registry/preferences/snapshots

- Provider/model capability filtering is correct.
- Invalid provider/model combinations return `422`.
- Duplicate credential/provider and preference singleton writes are rejected or
  safely resolved.
- Defaults resolve safely and job snapshots contain no secrets.
- Existing environment-based provider credentials remain compatible.

### Callback and network boundary

- Missing, malformed, stale, incorrectly signed, replayed, and duplicate-nonce
  callbacks are rejected.
- Signature comparison is constant-time and uses the raw request body.
- Service-role headers and provider authorization headers are redacted from
  logs.
- Provider response bodies and secrets are absent from API errors, jobs, event
  messages, callback payloads, and execution data.
- Deployment checks confirm FastAPI, n8n, Supabase, and renderer are not bound
  to public interfaces by default.

### Concurrency

- Simultaneous credential replacement does not leave partial ciphertext.
- Credential deletion during a connection test produces a safe result.
- Duplicate global preference creation is handled atomically.
- Replaying the same callback or using one nonce twice is rejected.

## Phase 1 Exit Criteria

- Provider credentials are encrypted at rest and masked at the API boundary.
- The provider/model registry and global preferences are safe API concepts.
- Job snapshots contain only provider/model/source/reference metadata.
- Internal n8n callbacks have replay-resistant HMAC authentication.
- Secrets are absent from logs, jobs, events, browser storage, and n8n data.
- Existing environment-based generation and the current generation sequence are
  unchanged.
- FastAPI, n8n, Supabase, and renderer exposure is documented and private by
  default.
- Backend tests cover the security cases above.
- No Settings UI or credential migration is started before this specification
  is approved.
