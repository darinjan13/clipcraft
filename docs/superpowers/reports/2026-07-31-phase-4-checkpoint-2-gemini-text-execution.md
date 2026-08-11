# Phase 4 Checkpoint 2: Gemini Text Execution

## Status

Implemented as an isolated callable backend execution plugin. It is not wired into `POST /api/videos`, live generation, or n8n.

## Files Changed

- `backend/app/services/ai/gemini_execution.py`
- `backend/app/services/ai/provider_executor.py`
- `backend/app/services/ai/adapters.py`
- `backend/tests/test_gemini_execution.py`
- `backend/tests/test_provider_executor.py`

The legacy `gemini_text_provider.py` remains unchanged and is not replaced by this checkpoint.

No frontend, Settings, database, migration, FastAPI route, n8n, workflow, callback, or live generation files were changed.

## Gemini Execution Architecture

The isolated flow is:

```text
RoutingDecision
  -> CredentialResolver / ExecutionContext
  -> GeminiAdapter
  -> ProviderExecutor
  -> GeminiTextExecution
  -> injected GeminiTransport
```

`ProviderExecutor` remains provider-agnostic. Gemini-specific URL construction, authentication, request construction, response parsing, and error mapping live in `gemini_execution.py`.

Registration uses the existing `ProviderExecutionRegistry`:

```python
register_gemini_execution(registry, transport=optional_test_transport)
```

There is no application composition-root registration, so no production caller can execute Gemini accidentally.

## HTTP Transport

- Client: existing `httpx.AsyncClient` dependency.
- Method: `POST`.
- Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/{encoded_model}:generateContent`.
- Model path segments are URL-encoded without rewriting the raw model ID.
- Timeout: 60 seconds by default, explicitly configurable in the Gemini execution component.
- Redirects: disabled.
- Response size: bounded to 4 MiB.
- Request and response bodies are not logged.
- Transport failures normalize to timeout or unavailable errors.

## Authentication

The existing `GEMINI_API_KEY` environment name and stored credential strategy are honored through `ExecutionContext`. The key is sent only at transport time using the `x-goog-api-key` header. It is not placed in the URL, prepared payload, normalized result, error message, or logs.

No fallback occurs between environment and stored strategies.

## Supported Request Parameters

GeminiAdapter accepts only:

- `prompt`
- `system_prompt`
- `temperature`
- `max_tokens`

The Gemini request uses `contents`, optional `systemInstruction`, and `generationConfig`. No speculative parameters, streaming, tools, uploads, grounding, or history were added.

Prompt semantics remain caller-controlled; no hidden system prompt or prompt rewrite is introduced.

## Normalized Result Model

Successful execution returns generic `ExecutionOutput` metadata:

- provider ID
- exact model ID
- capability
- extracted text
- finish reason
- allowlisted numeric usage metadata
- safe provider request ID when supplied
- elapsed milliseconds

Raw Gemini responses, request bodies, headers, credentials, safety annotations, and database identifiers are excluded.

Text is concatenated from text parts only. Missing candidates, malformed content, non-text-only parts, and empty text are failures rather than successful empty output. `MAX_TOKENS` remains available as a finish reason for truncated output.

## Lifecycle Transitions

Preparation reaches:

```text
prepared -> validated -> ready
```

Registered Gemini execution reaches:

```text
prepared -> validated -> ready -> executing -> completed
```

Transport/provider failures reach a normalized failed result:

```text
prepared -> validated -> ready -> executing -> failed
```

Unregistered execution remains `execution_not_implemented`.

## Error Mappings

Gemini and transport failures normalize to:

- `invalid_request`: HTTP 400.
- `invalid_credentials`: HTTP 401.
- `permission_denied`: HTTP 403.
- `timeout`: HTTP 408, client timeout, or timeout transport failure.
- `rate_limited`: HTTP 429.
- `unavailable`: HTTP 5xx or connection failure.
- `blocked_response`: Gemini prompt feedback block.
- `malformed_response`: invalid JSON, missing candidates, or malformed content.
- `empty_response`: no usable text parts.
- `provider_error`: other non-success provider responses.
- `execution_error`: invalid execution metadata or unexpected execution failure.

Messages are fixed safe text and never include raw Gemini bodies, URLs, API keys, authorization data, or prompts.

## Credential Behavior

Environment and stored Gemini credentials are tested through the existing resolver-generated `ExecutionContext`. The execution plugin reads the matching in-memory `SecretStr` only at transport invocation. No credential is cached globally, persisted, returned, or placed in the prepared request.

## Live Request

No live Gemini request was performed. All transport calls were injected fakes. No provider quota was consumed.

## Verification

- Focused Gemini/framework/adapter/routing/credential tests: `88 passed`.
- Full backend suite: `161 passed` via `pytest backend/tests -q`.
- Frontend production build: `npm run build` passed.
- Production-source scan found no query-string API-key construction, logs, or secret literals in the new Gemini execution module.
- Log-output fixture tests produced no secret-bearing output.

## Architecture Review

Read-only architecture review passed. The generic executor remains provider-independent; Gemini transport and parsing are isolated in the provider-specific plugin. The execution registry is injectable and no production composition root is modified.

## Security Review

The new path uses header authentication, safe fixed errors, bounded response handling, `SecretStr` runtime credentials, and no request/response logging. Existing repository risks remain outside scope, including the legacy provider’s query-key implementation, n8n execution-data retention, and existing unauthenticated infrastructure.

## Compatibility Review

The following remain unchanged:

- `POST /api/videos` contract and behavior.
- Live generation and environment-based n8n execution.
- `brief_json` and snapshot behavior.
- n8n payloads and workflow files.
- Frontend and Settings behavior.
- Cloudflare, Pexels, and NVIDIA behavior.
- Legacy Gemini provider implementation.

## Remaining Limitations

- Gemini execution is isolated and has no production caller by design.
- The legacy `GeminiTextProvider` remains a separate implementation with its previous behavior; migrating it is future work and would require a separate compatibility decision.
- No Gemini response schema validation beyond safe text extraction and usage allowlisting was added.
- Retries, cancellation, streaming, structured application output validation, and runtime integration remain future work.
- No Cloudflare, Pexels, NVIDIA, frontend, or n8n execution was started.
