# Phase 5 Checkpoint 2: Runtime Comparison & Validation

## Status

Implemented an additive, non-authoritative runtime comparison layer.

The legacy generation path remains the source of truth. Comparison metadata is generated after the existing job persistence step, never persisted, never returned to users, and never used to gate or alter legacy execution.

## Files Changed

- `backend/app/config.py`
  - Added `shadow_runtime_comparison: bool = True`.
  - Reads `SHADOW_RUNTIME_COMPARISON`, defaulting to enabled.
- `backend/app/services/ai/runtime_comparison.py`
  - Added immutable `RuntimeMetadata`, `ComparisonMetric`, and `RuntimeComparisonEngine`.
- `backend/app/services/ai/shadow_execution.py`
  - Added `ShadowRunReport`.
  - Preserved the existing `run()` tuple return.
  - Added `run_with_comparison()` for internal comparison reports.
  - Compares legacy routing metadata with shadow routing/lifecycle metadata.
- `backend/app/main.py`
  - Builds safe legacy metadata from the persisted routing snapshot.
  - Passes it to `run_with_comparison()` after job persistence.
  - Continues discarding the report inside the existing failure-isolation boundary.
- `backend/tests/test_runtime_comparison.py`
  - Added pure comparison tests.
- `backend/tests/test_shadow_execution.py`
  - Added runner integration, flag, API-isolation, mismatch, and output-discard coverage.

No frontend files, n8n workflows, callback contracts, database migrations, schemas, job lifecycle code, or provider execution modules were changed.

## Comparison Architecture

```text
POST /api/videos
  -> existing validation and selection
  -> persist queued job and routing snapshot
  -> legacy path remains authoritative
  -> build safe legacy RuntimeMetadata
  -> ShadowExecutionRunner.run_with_comparison()
      -> shadow routing
      -> credential resolution
      -> adapter validation and preparation
      -> optional shadow provider execution
      -> build safe shadow RuntimeMetadata
      -> RuntimeComparisonEngine.compare()
      -> return ShadowRunReport internally
  -> discard report
  -> return existing queued Video response
```

The comparison engine is pure. It does not validate providers, resolve credentials, access the database, execute providers, or inspect payloads/results.

The existing `ShadowExecutionRunner.run()` behavior remains unchanged for existing callers and tests. `run_with_comparison()` is an internal reporting wrapper around the same execution flow, not a duplicate provider implementation.

## Safe Comparison Metadata

`RuntimeMetadata` contains only:

- `provider_id`
- `model_id`
- `capability`
- `routing_version`
- optional lifecycle `state`

`ComparisonMetric` contains only safe comparison fields:

- normalized outcome
- normalized mismatch category
- provider/model IDs
- capability
- optional legacy/shadow states

The comparison layer never receives or stores prompts, provider responses, images, credentials, authorization headers, raw request bodies, raw response bodies, or arbitrary exception messages.

## Comparison Outcomes

Supported outcomes:

- `match`
- `mismatch`
- `skipped`
- `validation_failed`

Supported mismatch/skip categories:

- `provider`
- `model`
- `capability`
- `routing_version`
- `state`
- `legacy_unavailable`
- `shadow_unavailable`
- `comparison_disabled`
- `invalid_metadata`

Comparison order is deterministic:

```text
provider -> model -> capability -> routing_version -> state
```

Missing lifecycle state is treated as unavailable rather than an automatic mismatch. This allows comparison against the existing legacy path, which does not expose an equivalent provider execution lifecycle summary.

## Feature Flags

Comparison flag:

```text
SHADOW_RUNTIME_COMPARISON=true
```

It defaults to enabled. Disabling it produces `skipped / comparison_disabled` metrics.

Provider execution remains separately controlled by the existing flag:

```text
SHADOW_PROVIDER_EXECUTION=false
```

When provider execution is disabled, comparison still validates routing and preparation but never calls a provider. Comparison does not require provider execution.

## Legacy Compatibility

Legacy metadata is constructed from the same resolved selection and persisted snapshot used by the existing route:

- text provider/model
- image provider/model when AI visuals are selected
- visual source normalization
- provider configuration version converted to the shadow routing version

The comparison layer does not alter that snapshot. It does not update jobs, statuses, `brief_json`, callbacks, media, workflow payloads, or frontend responses.

## Failure Isolation

Comparison failures are contained by the existing `_shadow()` boundary. Routing failures produce validation-failed internal comparison results; missing comparison sides produce skipped results; malformed metadata is validation-failed. None of these outcomes can change the `202` response or legacy job state.

## Focused Test Results

```text
33 passed
```

Coverage includes:

- matching provider/model/capability/routing metadata
- provider mismatch
- model mismatch
- capability mismatch
- routing-version mismatch
- lifecycle-state mismatch
- missing legacy metadata
- missing shadow metadata
- invalid metadata
- comparison disabled
- default-enabled comparison flag
- shadow execution disabled without provider handler invocation
- shadow provider output not present in metrics
- shadow execution failure and timeout isolation
- API response isolation
- secret/content exclusion

## Full Verification

- Focused comparison/shadow/execution/routing/credential tests: `146 passed`.
- Full backend suite: `219 passed` via `pytest backend/tests -q`.
- Frontend production build: `npm run build` passed.
- No workflow JSON changes.
- No database migration changes.
- No callback or frontend source changes.

## Review Results

### Execution Review

Comparison performs no provider execution. Provider execution remains controlled solely by `SHADOW_PROVIDER_EXECUTION`. When disabled, registered handlers are not invoked.

### Compatibility Review

The current API, legacy job persistence, `brief_json`, frontend, workflow, callback, and database contracts remain unchanged by this checkpoint. The workspace has no Git metadata, so an authoritative VCS diff was unavailable.

### Architecture Review

The comparison engine is pure and additive. It compares the persisted legacy routing snapshot with shadow routing/lifecycle metadata and discards the result. No duplicate provider implementation was added.

### Testing Review

Comparison outcomes and mismatch categories are directly tested. Shadow execution and API isolation remain covered by the prior checkpoint tests. Full backend and frontend verification passed.

### Security Review

No comparison or shadow path logs or serializes prompts, provider outputs, credentials, authorization headers, raw payloads, or raw provider errors. Runtime metadata type validation rejects malformed values before comparison.

## Readiness Assessment For Live Cutover

**Not ready for live cutover.** This checkpoint intentionally does not replace the legacy pipeline.

Remaining risks and follow-ups:

- Enabling `SHADOW_PROVIDER_EXECUTION=true` performs a second provider call path and can consume provider quota or incur duplicate cost.
- Enabled shadow execution remains synchronous inside `POST /api/videos` and can increase request latency up to provider timeout limits.
- Comparison results are currently discarded because no approved safe metrics sink exists.
- The legacy path does not expose a complete equivalent provider execution summary, so lifecycle comparison is limited when legacy state is unavailable.
- Pexels and NVIDIA remain intentionally unimplemented.

The system is ready for continued non-authoritative validation, not for replacing or cutting over from legacy generation.
