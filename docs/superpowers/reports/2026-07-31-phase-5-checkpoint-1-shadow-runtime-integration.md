# Phase 5 Checkpoint 1: Shadow Runtime Integration

## Status

Implemented shadow integration without replacing the legacy generation path.

The legacy pipeline remains authoritative. Shadow routing, credential resolution, request preparation, and optional provider execution run after job persistence. Shadow output is discarded and cannot alter the API response, job state, workflow state, callback payloads, or generated media.

## Files Changed

- `backend/app/config.py`
  - Added `shadow_provider_execution: bool = False`.
  - Reads `SHADOW_PROVIDER_EXECUTION`, defaulting to disabled.
- `backend/app/services/ai/shadow_execution.py`
  - Added `ShadowExecutionRunner` and safe `ShadowMetrics`.
  - Wires `DryRunProviderRouter`, `CredentialResolver`, `ExecutionContext`, adapters, and `ProviderExecutor`.
  - Registers existing Gemini and Cloudflare execution handlers.
- `backend/app/main.py`
  - Instantiates the runner in `create_app()`.
  - Invokes `_shadow()` after job persistence and directory creation.
  - Swallows shadow failures before returning the unchanged queued response.
- `backend/tests/test_shadow_execution.py`
  - Added focused shadow-mode, failure-isolation, security, timing, feature-flag, and API compatibility tests.

No frontend files, workflow JSON, callback payload, database migration, job schema, or n8n contract files changed.

## Shadow Execution Flow

```text
POST /api/videos
  -> validate existing request
  -> resolve existing provider selection
  -> persist queued job and create job directory
  -> ShadowExecutionRunner.run()
      -> DryRunProviderRouter.resolve()
      -> CredentialResolver / ExecutionContext
      -> ProviderAdapter validation
      -> ProviderExecutor.prepare()
      -> if disabled: record ready/failed safe metrics and stop
      -> if enabled: ProviderExecutor.execute()
      -> discard ExecutionResult output
  -> return existing queued Video response
```

The persisted `job_id` is propagated into the shadow `ExecutionContext` and executor metadata. Shadow execution does not update the database or call `WorkflowClient`.

## Feature Flag

Environment variable:

```text
SHADOW_PROVIDER_EXECUTION=false
```

Default behavior is disabled. With the flag disabled, no registered provider handler is invoked and no provider quota is consumed. Routing, credential resolution, adapter validation, and executor preparation still run for validation purposes.

With the flag enabled, registered Gemini and Cloudflare handlers may perform provider calls. Their normalized outputs are discarded immediately. The legacy pipeline remains authoritative.

## Execution Lifecycle

Disabled mode records safe metrics with lifecycle state:

```text
prepared -> validated -> ready
```

Preparation failures are represented as `failed` metrics.

Enabled mode records:

```text
prepared -> validated -> ready -> executing -> completed
```

or:

```text
prepared -> validated -> ready -> executing -> failed
```

The runner preserves the existing executor lifecycle and does not introduce a duplicate provider execution path.

## Observability

`ShadowMetrics` contains only:

- `provider_id`
- `model_id`
- `capability`
- lifecycle `state`
- routing duration
- credential-resolution duration
- preparation duration
- execution duration when enabled
- normalized safe error category

Metrics do not contain prompts, API keys, tokens, decrypted credentials, authorization headers, provider responses, raw HTTP payloads, job content, or database identifiers. The route currently discards the metrics because no metrics sink exists in the existing application; no unsafe logging was introduced.

Unknown custom error codes are normalized to `execution_error`.

## Failure Isolation

Shadow routing, credential, adapter, preparation, provider, timeout, and custom-adapter failures are isolated. They produce empty/failed safe metrics and do not interrupt the existing request path.

The `_shadow()` boundary additionally catches any unexpected runner failure. A successful legacy job insert still returns HTTP `202` with the existing queued response.

## Compatibility Verification

Verified unchanged:

- `POST /api/videos` response model and status code.
- Existing `VideoDraft` and `Video` behavior.
- `brief_json` construction and persistence.
- Job status and lifecycle fields.
- Callback payloads.
- n8n workflow files and contracts.
- Frontend behavior and API calls.
- Database schema and migrations.
- Legacy provider and workflow execution behavior.

The provider-selection fields already present in `VideoDraft` and frontend payloads predate this checkpoint and were not changed here.

## Focused Test Results

```text
129 passed
```

Covered:

- Disabled feature flag.
- Enabled feature flag.
- No provider handler invocation while disabled.
- Routing and credential failures.
- Provider execution failures and timeouts.
- Safe timing metrics.
- Safe metric contents.
- Provider output discard.
- Unsupported Pexels routing remains isolated.
- `POST /api/videos` response compatibility.
- Shadow exception isolation at the API boundary.

## Full Verification

- Full backend suite: `202 passed` via `pytest backend/tests -q`.
- Frontend production build: `npm run build` passed.
- No workflow JSON changes.
- No migration changes.
- No callback or frontend source changes.
- No provider call occurs when the flag is disabled.

## Review Results

### API Contract

Response contract is preserved. Existing provider-selection request fields were pre-existing and unchanged by this checkpoint.

### Architecture

The shadow path is additive and runs after persistence. It uses the existing router, resolver, context, adapter, and executor abstractions. It does not replace or mutate the legacy path. The persisted job ID is preserved in shadow execution metadata.

### Security

No shadow logging or raw payload capture was introduced. Secrets remain inside runtime credential handling and are not present in metrics or API responses. Default execution is disabled. Custom handler error categories are normalized.

### Compatibility

Existing API, execution, routing, credential, workflow-contract, and frontend build verification passed. No frontend, workflow, callback, schema, or migration changes were made.

### Testing

Focused shadow tests cover the required flag, failure, timing, output-discard, and compatibility behaviors. Full backend and frontend verification passed.

## Remaining Integration Work

- Decide whether to add a production metrics sink for safe `ShadowMetrics`; this checkpoint intentionally keeps metrics internal and non-user-visible.
- Consider moving enabled shadow execution off the synchronous request path if production latency requirements require it.
- Future checkpoints may integrate shadow results into controlled diagnostics, but must preserve legacy authority.
- Pexels and NVIDIA execution remain intentionally unimplemented.
- Legacy execution remains unchanged and is not removed.
