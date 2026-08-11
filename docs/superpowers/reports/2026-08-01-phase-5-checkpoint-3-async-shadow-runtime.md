# Phase 5 Checkpoint 3: Asynchronous Shadow Runtime

## Status

Implemented asynchronous, non-authoritative shadow dispatch using FastAPI/Starlette `BackgroundTasks`.

The legacy generation pipeline remains authoritative. `POST /api/videos` persists the job, schedules shadow validation, and returns the existing `202` response without waiting for shadow routing, credential resolution, preparation, comparison, or provider execution.

## Files Changed

- `backend/app/main.py`
  - Added the existing FastAPI `BackgroundTasks` dependency to `POST /api/videos`.
  - Replaced the inline `_shadow(...)` call with `background_tasks.add_task(...)` after job persistence and directory creation.
  - Preserved the existing `_shadow()` failure boundary and all existing arguments/snapshots.
- `backend/tests/test_async_shadow_runtime.py`
  - Added scheduling, response-isolation, and background-call execution tests.

No changes were made to:

- Legacy generation execution.
- `ShadowExecutionRunner` routing, credential, adapter, executor, or comparison behavior.
- n8n workflows or callback contracts.
- Frontend source or API behavior.
- Database schema, migrations, job lifecycle, or `brief_json`.
- Provider cutover, Pexels, or NVIDIA execution.

## Background Execution Architecture

```text
POST /api/videos
  -> existing request validation
  -> existing provider selection and snapshot
  -> existing job persistence
  -> existing job directory creation
  -> BackgroundTasks.add_task(_shadow, immutable request snapshot)
  -> immediately return existing queued Video response

Background task
  -> _shadow failure boundary
  -> ShadowExecutionRunner.run_with_comparison()
  -> routing
  -> credential resolution
  -> adapter preparation
  -> optional provider execution
  -> comparison
  -> discard report
```

The scheduled callable is synchronous, so Starlette executes it through its background-task worker mechanism. This keeps the existing `asyncio.run()` usage inside a worker thread rather than invoking it from an active event loop.

No Redis, Celery, RabbitMQ, Kafka, custom queue, or other external infrastructure was introduced.

## Dispatch Mechanism

The route now receives `BackgroundTasks` and schedules `_shadow` only after:

1. The existing database insert succeeds.
2. The existing job directory is created.

The route does not call `future.result()`, await shadow work, or otherwise block on the scheduled callable.

The existing `_shadow()` helper still catches all shadow failures. There is no retry loop, so failed background work is best-effort and cannot retry infinitely.

## Execution Lifecycle

The existing lifecycle is unchanged:

```text
prepared -> validated -> ready
```

When `SHADOW_PROVIDER_EXECUTION=true`:

```text
prepared -> validated -> ready -> executing -> completed/failed
```

The existing `SHADOW_RUNTIME_COMPARISON` behavior is preserved. Comparison consumes safe legacy/shadow metadata and discards its report. Provider outputs remain discarded.

## Feature Flags

Existing flags are unchanged:

```text
SHADOW_PROVIDER_EXECUTION=false
SHADOW_RUNTIME_COMPARISON=true
```

With provider execution disabled, background work performs only routing, credential resolution, adapter validation, preparation, and comparison. It does not call providers.

## Failure Isolation

Background failures cannot:

- Fail `POST /api/videos`.
- Change the returned `Video` response.
- Change job status, progress, or lifecycle.
- Modify callbacks or n8n state.
- Modify generated media.
- Trigger an infinite retry loop.

The already-persisted queued job remains the legacy pipeline’s responsibility.

## Observability

Existing safe metrics and comparison metrics remain unchanged:

- Routing duration.
- Credential-resolution duration.
- Preparation duration.
- Shadow execution duration.
- Comparison outcome.
- Normalized error category.

No prompts, provider responses, credentials, authorization headers, raw payloads, or raw exceptions are logged or returned. Metrics and reports remain internal and discarded because no approved durable metrics sink exists.

## Latency Comparison

Before this checkpoint, `POST /api/videos` called `_shadow()` inline and could wait for provider timeouts. After this checkpoint, the route schedules `_shadow()` and returns the queued response without waiting for it.

Verification proves dispatch is scheduled after persistence and that the response is produced independently of the shadow callable. No live provider request was performed, so no external provider latency benchmark was taken.

Starlette `TestClient` may wait for background tasks as part of test teardown; that is a test-client behavior and does not reintroduce inline execution in the production request handler.

## Compatibility Verification

Verified unchanged:

- `POST /api/videos` response schema and `202` status.
- Existing job insertion and queued status.
- Existing provider snapshots and `brief_json`.
- Legacy generation authority.
- n8n workflow files and contracts.
- Callback behavior.
- Frontend behavior and build.
- Database schema and migrations.
- Job lifecycle and media behavior.

The workspace has no Git metadata, so an authoritative VCS diff was unavailable. Read-only compatibility review found no new contract changes.

## Focused Tests

```text
149 passed
```

Coverage includes:

- POST schedules shadow work after persistence.
- POST does not invoke shadow work inline.
- Background callable dispatch execution.
- Background failure response isolation.
- Existing shadow and comparison behavior.
- Existing execution, routing, and credential behavior.

## Full Verification

- Full backend suite: `222 passed` via `pytest backend/tests -q`.
- Frontend production build: `npm run build` passed.
- No workflow changes.
- No database changes.
- No callback changes.
- No frontend changes.

## Review Results

### Architecture Review

FastAPI/Starlette background tasks are the smallest existing in-process mechanism. No new queueing infrastructure was introduced. The legacy response and job path remain authoritative.

### Concurrency Review

The synchronous shadow callable now runs after response dispatch through the background-task worker mechanism. Existing `asyncio.run()` remains confined to that synchronous worker callable. No provider execution is performed in the request handler.

### Execution Review

Routing validation, credential resolution, adapter preparation, executor lifecycle, feature flags, comparison, safe metrics, and output discard are preserved.

### Security Review

The background task receives only the existing immutable selection/snapshot and required service dependencies. No prompt content is added. Existing `SecretStr` handling and safe metrics remain in force. `_shadow()` catches failures without logging raw exceptions or provider data.

### Compatibility Review

Existing API tests, shadow tests, comparison tests, workflow compatibility checks, and frontend build pass. No n8n, callback, database, schema, or frontend files were modified.

## Readiness Assessment For Live Provider Cutover

**Not ready for provider cutover.** This checkpoint only removes shadow work from the request path.

Remaining operational limitations:

- FastAPI background tasks are process-local and non-durable; shutdowns or crashes can drop shadow work.
- Multiple workers do not coordinate background shadow capacity.
- Explicitly enabling `SHADOW_PROVIDER_EXECUTION` still performs duplicate provider calls and can incur duplicate quota/cost.
- Shadow execution remains best-effort and metrics are discarded without a durable sink.
- A durable worker or approved metrics pipeline would be required for production-grade shadow observability.

The implementation is ready for continued asynchronous validation, not legacy replacement or live provider cutover.
