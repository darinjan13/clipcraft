# Phase 3 Checkpoint 4: Provider Adapter Framework

## Status

Implemented and verified as an architecture-only layer. No provider execution or n8n routing was started.

## Files Changed

- `backend/app/services/ai/adapters.py`
- `backend/tests/test_provider_adapters.py`

No frontend, FastAPI route, routing, credential resolver, database, snapshot, `brief_json`, provider execution, or workflow files were changed.

## Adapter Interface

`ProviderAdapter` defines the common provider boundary:

- `capabilities()`
- `supports(capability)`
- `validate_request(capability, request)`
- `prepare_request(capability, request)`
- `prepare_execution_context(context)`
- `health()`

The interface only validates and prepares immutable safe metadata. It does not execute providers, resolve credentials, decrypt secrets, log, persist, or call n8n.

Prepared request payloads are deeply frozen. Credential-shaped fields, nested secret aliases, headers, and non-string keys are rejected before preparation.

## Adapter Registry

`AdapterRegistry` maps `provider_id` to a `ProviderAdapter` and provides:

- safe registration
- duplicate registration rejection
- adapter lookup
- provider ID enumeration

`default_adapter_registry()` registers the initial four providers. Future providers can register an adapter without changing the registry implementation or router.

## Provider Implementations

All implementations are stubs:

- `GeminiAdapter`: text generation and connection-test preparation; image generation is rejected.
- `CloudflareAdapter`: text generation, image generation, and connection-test preparation.
- `PexelsAdapter`: stock-media and connection-test preparation only; no search or download.
- `NVIDIAAdapter`: registered with no operational capabilities and safely rejects operations as unsupported.

Provider-specific validation currently covers prompt/query requirements, Gemini system-prompt typing, and Pexels media type/orientation values. No provider API request is made.

## Capability Model

Capabilities are additive string identifiers:

- `text_generation`
- `image_generation`
- `stock_media`
- `connection_test`

Adapter capability support is separate from the canonical provider registry’s declarative availability and implementation flags. Consumers must continue honoring registry/model availability and `adapter.supports()` before any future execution.

## Routing Interaction

The adapter registry is not imported by `ProviderRouter` and does not alter routing. The current flow remains:

```text
RoutingConfiguration -> ProviderRouter -> RoutingDecision
```

The adapter framework is an available future boundary only; no live route invokes it.

## Execution Interaction

`prepare_execution_context()` accepts the existing internal `ExecutionContext`, verifies provider membership and credential presence, and returns only:

- provider ID
- credential strategy
- routing version
- safe job ID

It never returns or serializes credential values. The adapter layer does not construct or resolve credentials.

## Future Executor Boundary

The intended future flow is:

```text
Generate
  -> ProviderRouter
  -> CredentialResolver
  -> ExecutionContext
  -> ProviderAdapter
  -> Future Executor
```

The Future Executor is deliberately not implemented. Provider APIs, retries, cancellation, result contracts, and transport behavior remain future work.

## Verification

- Focused adapter tests: `16 passed`.
- Full backend suite: `135 passed` via `pytest backend/tests -q`.
- Frontend production build: `npm run build` passed.
- Static inspection found no HTTP, SDK, subprocess, workflow, credential-resolution, or decryption dependency in `adapters.py`.

## Compatibility Review

Read-only compatibility review passed:

- No FastAPI route or public response changes.
- No frontend changes.
- No generation behavior changes.
- No routing or credential-resolver integration.
- No snapshot, `brief_json`, or database changes.
- No n8n workflow or payload changes.
- Existing provider connection-test behavior remains separate.

## Architecture Review

The framework provides a single adapter interface and provider-ID registry while preserving the existing text/image provider interfaces and routing/credential seams. Stub preparation is isolated from execution. The registry is intentionally separate from the canonical declarative provider registry to avoid mixing metadata with runtime adapter objects.

## Security Review

Adapters do not call providers, resolve credentials, decrypt secrets, log, persist, or send data to n8n. Prepared request payloads reject nested and aliased credential fields and are deeply immutable. Prepared execution metadata excludes secrets and account metadata.

Existing repository-wide n8n execution-data and checked-in credential risks remain outside this checkpoint and require separate security remediation.

## Remaining Work

- Implement reviewed provider-specific adapters only when execution is approved.
- Define the Future Executor interface, result/error contract, timeouts, retries, and cancellation.
- Reconcile adapter capabilities with canonical registry availability and implementation metadata.
- Add a backend image adapter only after an approved provider execution contract exists.
- Implement dynamic routing and n8n integration in a later approved checkpoint.

No provider execution, n8n routing, workflow modification, frontend change, authentication, or multi-user work was started.
