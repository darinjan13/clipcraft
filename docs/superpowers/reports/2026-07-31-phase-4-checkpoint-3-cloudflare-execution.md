# Phase 4 Checkpoint 3: Cloudflare Text/Image Execution

## Status

Implemented as an isolated callable backend execution plugin with two capabilities (text and image). Not wired into `POST /api/videos`, live generation, or n8n.

## Files Changed

- `backend/app/services/ai/cloudflare_execution.py` — new file
- `backend/app/services/ai/adapters.py` — added CloudflareAdapter parameter validation
- `backend/tests/test_cloudflare_execution.py` — new file (25 tests)
- `backend/tests/test_provider_adapters.py` — minor fix to adapter freeze test

The legacy `cloudflare_text_provider.py` remains unchanged. No frontend, Settings, database, migration, FastAPI route, n8n, workflow, callback, or live generation files were changed.

## Capabilities

### Text Generation (`@cf/meta/llama-3.1-8b-instruct`)
- Supported parameters: `prompt`, `system_prompt`, `temperature` (0–2), `max_tokens` (positive int)
- Request body: `{"messages": [...], "max_tokens": ..., "temperature": ...}`
- Response: extracts `result.response`, rejects empty or missing text

### Image Generation (`@cf/black-forest-labs/flux-1-schnell`)
- Supported parameters: `prompt` only
- Request body: `{"prompt": "..."}`
- Response: extracts `result.image` as base64 text, rejects empty or missing image

## Execution Architecture

The isolated flow per capability is:

```text
RoutingDecision
  -> CredentialResolver / ExecutionContext
  -> CloudflareAdapter
  -> ProviderExecutor
  -> CloudflareTextExecution or CloudflareImageExecution
  -> injected CloudflareTransport
```

Both capabilities share the same transport and registration function.

## HTTP Transport

- Client: `httpx.AsyncClient`
- Endpoint: `https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}`
- The model path segments are appended directly (Cloudflare model IDs like `@cf/meta/llama-3.1-8b-instruct` form valid nested URL paths)
- Timeout: 60 seconds by default
- Redirects: disabled
- Response size: bounded to 4 MiB
- No request or response body logging

## Authentication

Authentication requires two pieces:
- **API key**: resolved to `SecretStr` from environment (`CLOUDFLARE_AI_TOKEN`) or stored credential
- **Account ID**: resolved from environment (`CLOUDFLARE_ACCOUNT_ID`) or stored credential metadata

Both are resolved by the `CredentialResolver` into `ResolvedProviderCredential` (which has an `account_id` field). At transport time, the API key is sent via `Authorization: Bearer` header and the account ID is embedded in the URL path.

No fallback occurs between environment and stored strategies. Both pieces must be present or execution fails with `credential_resolution_error`.

## Named Error Mappings

- `invalid_request`: HTTP 400
- `invalid_credentials`: HTTP 401
- `permission_denied`: HTTP 403
- `timeout`: HTTP 408 or client timeout
- `rate_limited`: HTTP 429
- `unavailable`: HTTP 5xx or connection failure
- `provider_error`: other non-success HTTP status or `success: false` in body
- `malformed_response`: invalid JSON or missing result
- `empty_response`: empty text or image in result

Messages are fixed safe text and never include raw Cloudflare bodies, URLs, API keys, authorization data, prompts, or account IDs.

## Credential Behavior

Environment and stored Cloudflare credentials are resolved through the existing `CredentialResolver`. The `ResolvedProviderCredential.account_id` field is read at execution time. Both `api_key` and `account_id` must be present.

The credential validation at the adapter level (`prepare_execution_context`) checks that a credential exists for the provider. Runtime validation additionally checks that `account_id` is populated.

## Registration

```python
register_cloudflare_executions(registry, transport=optional_test_transport)
registers "cloudflare" → "text_generation" and "cloudflare" → "image_generation"
```

There is no application composition-root registration, so no production caller can execute Cloudflare accidentally.

## Verification

- Cloudflare execution tests: **25 passed**
- Focused framework/adapter/routing/credential tests: **113 passed**
- Full backend suite: **186 passed** via `pytest backend/tests -q`
- Frontend production build: `npm run build` passed
- No `POST /api/videos`, frontend, n8n, workflow, database, or live generation changes
- No live Cloudflare request was performed
