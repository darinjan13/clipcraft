# WF17/WF18 Canonical Contract Design

## Status

Approved for implementation by the project owner.

## Goal

Make the repository WF17 and WF18 workflows the canonical implementation of the approved provider-request, validation, error, retry, and normalized-response contracts without runtime interaction during this milestone.

## Authority

1. Verified active caller requirements.
2. `docs/TESTING_STRATEGY.md`.
3. `docs/ARCHITECTURE_DECISIONS.md`.
4. `docs/WORKFLOW_CATALOG.md`.
5. Approved implementation requirements.
6. `clipcraft/shared-contract.md` as historical reference only.

## Verified Consumers

- WF01 parses WF17 text from `result`.
- WF04 parses WF17 text from `result` as generated script JSON.
- WF05 consumes WF18 `imageBase64` and requires caller context for `jobId`, `sceneId`, and `sceneIndex`.
- WF12 consumes WF18 `imageBase64`; its own context is sufficient for persistence.
- WF03 observes wrapper `success` and error information from WF04/WF05.
- `functional_tests.py` verifies Build Request contracts and will be extended to verify normalized responses.

## Canonical Topology

```text
Workflow Trigger
  -> Build Request
  -> Validate Input
       true  -> Call Provider API
       false -> Handle Validation Error
  Call Provider API -> Normalize Response
  Normalize Response -> Retry Decision
       retry -> bounded retry state -> Call Provider API
       finish -> normalized output
```

The retry path must not form an uncontrolled cycle. Retry state is explicit and bounded at two retries. The final normalized response is emitted after success, provider failure, validation failure, or retry exhaustion.

## Runtime Trigger Compatibility

The local n8n runtime requires workflow-trigger nodes to declare
`parameters.events: ["update"]`. This field is part of the canonical
repository definitions for WF17 and WF18 because n8n rejects empty trigger
parameters during public-API publication.

## Response Envelope

Every normalized response includes:

- `success`: boolean discriminator.
- `type`: `text` for WF17 or `image` for WF18.
- `retryCount`: integer count of completed retry attempts.
- `timestamp`: ISO-8601 UTC timestamp.
- Optional `_testCorrelationId`, only when supplied by the caller.
- Optional `context`, only when verified caller context exists.
- No credentials, provider headers, authorization values, or raw provider response bodies.

### WF17 Success

```json
{
  "success": true,
  "type": "text",
  "result": "<generated text>",
  "provider": "<provider name>",
  "model": "<model name or null>",
  "retryCount": 0,
  "timestamp": "<UTC ISO-8601>",
  "_testCorrelationId": "<only when supplied>"
}
```

### WF18 Success

```json
{
  "success": true,
  "type": "image",
  "imageBase64": "<base64 data>",
  "format": "png",
  "provider": "<provider name>",
  "model": "<model name or null>",
  "retryCount": 0,
  "timestamp": "<UTC ISO-8601>",
  "context": {
    "jobId": "<only when supplied>",
    "sceneId": "<only when supplied>",
    "sceneIndex": 1
  },
  "_testCorrelationId": "<only when supplied>"
}
```

WF18 context normalization:

- `job_id` or `jobId` becomes `context.jobId`.
- `id`, `scene_id`, or `sceneId` becomes `context.sceneId`.
- `scene_index` or `sceneIndex` becomes `context.sceneIndex`.
- Omit `context` when none of these verified fields exists.
- Do not emit historical aliases at the top level.

### Validation Failure

```json
{
  "success": false,
  "type": "text|image",
  "error": {
    "type": "VALIDATION_ERROR",
    "code": "<stable validation code>",
    "message": "<safe message>",
    "retryable": false,
    "source": "workflow"
  },
  "retryCount": 0,
  "timestamp": "<UTC ISO-8601>",
  "_testCorrelationId": "<only when supplied>"
}
```

Validation codes include `MISSING_PROMPT`, `INVALID_PROMPT_TYPE`, `INVALID_METADATA`, and `UNSUPPORTED_PROVIDER`.

### Provider Failure

```json
{
  "success": false,
  "type": "text|image",
  "error": {
    "type": "PROVIDER_ERROR",
    "code": "PROVIDER_CONFIG_MISSING|PROVIDER_HTTP_ERROR|PROVIDER_RESPONSE_INVALID|UNSUPPORTED_PROVIDER",
    "message": "<sanitized message>",
    "retryable": true,
    "source": "<provider name>"
  },
  "retryCount": 1,
  "timestamp": "<UTC ISO-8601>",
  "_testCorrelationId": "<only when supplied>"
}
```

### Retry Exhaustion

```json
{
  "success": false,
  "type": "text|image",
  "error": {
    "type": "RETRY_EXHAUSTED",
    "code": "MAX_RETRIES_EXCEEDED",
    "message": "Provider request failed after the maximum retry count",
    "retryable": false,
    "source": "<provider name or workflow>"
  },
  "retryCount": 2,
  "timestamp": "<UTC ISO-8601>",
  "_testCorrelationId": "<only when supplied>"
}
```

## Request Contracts

WF17 Build Request output must have exactly:

```text
isValid, provider, url, headers, body
```

WF17 Cloudflare body:

```json
{
  "messages": [],
  "max_tokens": 5000,
  "temperature": 0.6
}
```

WF18 Build Request output must have exactly:

```text
isValid, provider, url, headers, body
```

WF18 Cloudflare body:

```json
{
  "prompt": "<prompt>"
}
```

The correlation marker and caller context must not appear in provider headers or provider bodies.

## Validation Rules

- Prompt must be a nonempty string after trimming.
- Metadata, when present, must be a plain object.
- Top-level metadata takes precedence over body metadata, including top-level `null`.
- Unsupported providers fail before provider invocation.
- Missing provider configuration fails without exposing secret values.
- Invalid input must never reach `Call Provider API`.

## Caller Migration

- WF01: consume only `result`; handle structured failure before parsing text.
- WF04: consume only `result`; stop persistence on structured failure and return safe wrapper failure.
- WF05: consume only `imageBase64` and `context.jobId/context.sceneId/context.sceneIndex`; stop persistence on failure.
- WF12: consume only `imageBase64`; stop persistence on failure.
- WF03: extract structured `error.message`, `error.code`, and `error.type` safely.
- Functional tests: assert normalized success, validation failure, provider failure, retry exhaustion, timestamp, context, and correlation isolation.

## Documentation Migration

Update `docs/WORKFLOW_CATALOG.md`, `docs/TESTING_STRATEGY.md`, and `clipcraft/shared-contract.md` so the canonical contract is explicit and the old response shapes are marked historical. Update `docs/CURRENT_STATE.md` after static validation.

## Validation

No n8n, Supabase, Cloudflare, webhook, workflow, credential, or SQLite action is permitted in this milestone. Static validation must include JSON parsing, required node/topology checks, expression/string checks, retry-bound checks, and Python syntax compilation for the updated test file.
