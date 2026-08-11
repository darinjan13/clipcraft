# Phase 5 Checkpoint 4: Internal Text-Execution Boundary

## Status

Implemented one hidden, HMAC-authenticated FastAPI endpoint for internal Gemini and Cloudflare text execution.

The endpoint is disconnected from live n8n workflows. It is not used by `POST /api/videos`, the frontend, callbacks, or legacy generation. It is a secure execution boundary for a later n8n integration checkpoint.

## Files Changed

- `backend/app/config.py`
  - Added `N8N_INTERNAL_SIGNING_SECRET` as a redacted setting.
- `backend/app/services/internal_auth.py`
  - Added HMAC-SHA256 verification and bounded process-local nonce replay protection.
- `backend/app/services/internal_text_execution.py`
  - Added strict internal request/response models.
  - Added the runtime service using the existing router, resolver, context, adapter, and executor stack.
  - Added normalized error mapping.
- `backend/app/main.py`
  - Added hidden `POST /internal/ai/text/execute`.
  - Initialized the process-local nonce store and internal text service.
  - Added a 1 MiB body limit.
  - No public generation route was changed.
- `backend/app/services/ai/gemini_execution.py`
  - Added normalized HTTP 402 quota mapping.
- `backend/app/services/ai/cloudflare_execution.py`
  - Added normalized HTTP 402 quota mapping.
- `backend/tests/test_internal_auth.py`
  - Added HMAC, timestamp, replay, cleanup, capacity, and concurrency tests.
- `backend/tests/test_internal_text_execution.py`
  - Added endpoint, provider, credential, validation, response, error, redaction, and OpenAPI tests.

No n8n workflow, frontend, callback, database migration, schema, job lifecycle, or `POST /api/videos` contract files were changed.

## Endpoint And Request Contract

Endpoint:

```text
POST /internal/ai/text/execute
```

The route uses `include_in_schema=False`, so it is absent from `/openapi.json`, `/docs`, and `/redoc` route listings.

Expected future private-network address from the current n8n Docker setup:

```text
http://host.docker.internal:8000/internal/ai/text/execute
```

The backend is currently a host-run Uvicorn service; there is no `backend` Docker service hostname. The hostname is documented here rather than hardcoded into application behavior.

Request shape:

```json
{
  "job_id": "uuid",
  "provider_id": "gemini",
  "model_id": "gemini-2.5-flash",
  "credential_source": "environment",
  "operation": "text_generation",
  "input": {
    "prompt": "...",
    "system_prompt": "...",
    "temperature": 0.2,
    "max_output_tokens": 2048,
    "response_format": "text"
  },
  "routing_version": "1",
  "request_id": "uuid"
}
```

The request model forbids extra fields. It does not accept raw API keys, tokens, encrypted credentials, arbitrary URLs, arbitrary headers, or environment variable names.

`response_format` is constrained to `text` or `json` as normalized request metadata. Existing provider adapters remain the authority for supported provider parameters; no new structured-output provider API was invented.

## HMAC Signing Contract

Configuration:

N8N_INTERNAL_SIGNING_SECRET
```

Required headers:

X-ClipCraft-Timestamp
X-ClipCraft-Nonce
X-ClipCraft-Signature
```

The signature is an HMAC-SHA256 hexadecimal digest over:

timestamp + "\n" + nonce + "\n" + raw_request_body
```

Properties:

- Constant-time `hmac.compare_digest` comparison.
- Five-minute maximum timestamp age.
- Five-minute future-timestamp rejection through the same bounded window.
- Missing or blank signing secret fails closed.
- Missing/malformed authentication returns generic `401`/`403` responses.
- Signature, nonce, secret, and raw request body are never logged or returned.
- Request bodies over 1 MiB are rejected before HMAC processing.

The exact raw body is authenticated before JSON parsing, preserving signature accuracy.

## Replay Protection

`NonceStore` is an in-memory, lock-protected store:

- Atomic check-and-consume.
- Expired nonce cleanup on each insertion.
- Default TTL: 300 seconds.
- Default maximum entries: 100,000.
- Duplicate nonce rejection within the validity window.
- Concurrent duplicate requests allow only one successful consume.
- Full capacity rejects new nonces rather than growing memory.

This store is process-local. Restart clears replay history, and multiple workers/replicas do not share nonce state. Multi-instance deployment would require shared atomic storage, intentionally not introduced here.

## Supported Text Providers

Only the implemented text-generation paths are registered:

- Gemini text.
- Cloudflare text.

The endpoint does not support images, Pexels, NVIDIA, speech, embeddings, streaming, tools, or multimodal content.

The endpoint uses the existing:

```text
DryRunProviderRouter
CredentialResolver
ExecutionContext
ProviderAdapter
ProviderExecutor
ProviderExecutionRegistry
```

No provider-specific HTTP implementation was added to the route.

## Credential-Strategy Behavior

`credential_source` is constrained to `environment` or `stored` and is honored exactly.

- `environment` resolves existing `GEMINI_API_KEY`, `CLOUDFLARE_AI_TOKEN`, and Cloudflare account metadata.
- `stored` decrypts the existing stored credential row using the existing encryption service.
- Stored credentials do not fall back to environment credentials.
- Cloudflare stored credentials require encrypted `account_id` metadata.
- No credential IDs, last-four values, account IDs, tokens, keys, or encrypted blobs are returned.

The existing router currently validates availability using environment-oriented settings and rejects `stored` as a routing configuration value. To preserve that existing router contract without redesigning it, the endpoint validates canonical provider/model routing through the router, then applies the requested credential strategy to the resulting immutable decision before calling the existing resolver. Credential resolution itself remains exact and fail-closed.

## Normalized Success Response

```json
{
  "request_id": "uuid",
  "job_id": "uuid",
  "provider_id": "gemini",
  "model_id": "gemini-2.5-flash",
  "capability": "text_generation",
  "status": "completed",
  "text": "...",
  "finish_reason": "STOP",
  "usage": {
    "promptTokenCount": 123,
    "candidatesTokenCount": 456
  },
  "elapsed_ms": 812,
  "routing_version": "1"
}
```

Usage is included only when the existing provider adapter supplies reliable integer usage metadata. Raw provider responses, headers, request bodies, prompts, credentials, and stack traces are excluded.

Successful empty text is rejected rather than returned as a completed result.

## Normalized Errors

Stable endpoint error codes include:

- `INTERNAL_AUTH_REQUIRED`
- `INTERNAL_SIGNATURE_INVALID`
- `INTERNAL_REQUEST_REPLAYED`
- `AI_PROVIDER_UNKNOWN`
- `AI_PROVIDER_DISABLED`
- `AI_PROVIDER_UNAVAILABLE`
- `AI_MODEL_UNKNOWN`
- `AI_MODEL_NOT_ALLOWED`
- `AI_CREDENTIAL_MISSING`
- `AI_CREDENTIAL_INVALID`
- `AI_QUOTA_EXCEEDED`
- `AI_RATE_LIMITED`
- `AI_TIMEOUT`
- `AI_RESPONSE_BLOCKED`
- `AI_RESPONSE_EMPTY`
- `AI_RESPONSE_INVALID`
- `AI_EXECUTION_FAILED`

Responses include a safe `retryable` boolean. HTTP 402 provider responses now normalize to `AI_QUOTA_EXCEEDED`. Provider error bodies are never returned.

## Logging And Redaction

The new endpoint and supporting modules contain no logging or `print()` calls. They do not serialize or return:

- Prompts or system prompts.
- Generated provider text.
- API keys, tokens, or decrypted credentials.
- HMAC signatures or nonces.
- Authorization headers.
- Raw request or provider response bodies.
- Account identifiers.
- Internal stack traces.

The generated text is returned only as the intended normalized success field; it is not logged or placed in error metadata.

The repository has pre-existing broader logging risks outside this checkpoint, including upstream response logging in `clients.py` and n8n execution-data retention. Those paths were not modified because this checkpoint explicitly prohibits workflow and unrelated logging changes.

## Verification

- Internal HMAC/provider focused tests: `62 passed`.
- Full backend suite: `242 passed` via `pytest backend/tests -q`.
- Workflow contract tests: `52 passed` with `PYTHONPATH=.`.
- Frontend production build: `npm run build` passed.
- Internal route absent from OpenAPI verified.
- No live Gemini, Cloudflare, or n8n request was performed.
- No provider quota was consumed by verification.
- Source scan found no logging calls in the new internal modules.

## Review Results

### API Security Review

HMAC verification, exact-body signing, constant-time comparison, timestamp bounds, bounded nonce replay protection, body-size limits, generic errors, credential redaction, and OpenAPI exclusion passed review. Process-local replay limitations and pre-existing repository logging risks remain documented.

### Architecture Review

The endpoint uses the existing provider runtime stack and registered Gemini/Cloudflare execution handlers. It does not call n8n or become authoritative. Existing legacy direct provider modules remain in the repository but are not used by this endpoint; removing them would be unrelated cutover work.

### n8n Contract Review

WF17 and all workflow JSON files remain unchanged. The future n8n address is `http://host.docker.internal:8000/internal/ai/text/execute` for the current host-run backend/containerized n8n setup. No workflow call was added in this checkpoint.

### Compatibility Review

`POST /api/videos`, frontend behavior, shadow/comparison behavior, job lifecycle, `brief_json`, callbacks, database schema, migrations, and n8n contracts remain unchanged. Existing backend, workflow-contract, and frontend build verification passed.

## Process-Local Limitations

- Nonce replay history clears on process restart.
- Multiple backend workers or replicas do not share nonce state.
- No durable idempotency/result cache exists; repeated `request_id` calls may execute the provider again.
- n8n remains responsible for bounded retries.
- Existing global OpenAPI/docs endpoints remain enabled, but this route is excluded from their schema.
- Existing repository-wide upstream response and n8n execution-data logging risks remain outside scope.

## Readiness For n8n Text-Routing Integration

**Ready for a later, controlled n8n text-routing integration checkpoint, not live integration now.**

The secure internal boundary exists, is HMAC-protected, validates canonical providers/models, supports environment/stored credentials, normalizes results/errors, and is disconnected from live workflows. The next checkpoint may add a narrowly scoped WF17 caller only after separately approving n8n payload, retry, execution-data retention, and operational-network decisions.
