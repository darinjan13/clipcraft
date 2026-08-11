# Phase 3 Checkpoint 2: Provider Routing Abstraction

## Status

Implemented and verified. The routing layer is dry-run only and is not connected to generation.

## Files Changed

- `backend/app/services/ai/routing.py`
- `backend/tests/test_routing.py`

No frontend, FastAPI endpoint, snapshot, database, provider execution, credential, n8n, or workflow files were changed.

## Interface

The new `ProviderRouter` protocol exposes one method:

```python
resolve(configuration: RoutingConfiguration) -> RoutingDecision
```

The current implementation is `DryRunProviderRouter`. It accepts text provider/model, visual source, image provider/model, credential source, and provider configuration version, then returns normalized safe routing metadata.

Example decision fields:

- `text_provider`
- `text_model`
- `visual_source`
- `image_provider`
- `image_model`
- `credential_strategy: environment`
- `routing_version: 1`

The protocol allows future router implementations without changing GeneratePage.

## Validation

The router reuses canonical registry validation and checks:

- Provider existence.
- Provider enabled and implemented state.
- Provider availability.
- Model ownership and capability.
- Model enabled, implemented, available, and non-deprecated state.
- Supported visual source.
- Complete text and AI-image provider/model pairs.
- Environment-only credential strategy.
- Stable provider configuration version `1`.
- Exact opaque model IDs without delimiter parsing.

Validation failures raise structured `RoutingValidationError` values containing a safe `code` and `message`.

Pexels is rejected by the router while the canonical registry marks it unimplemented. No Pexels execution or credential resolution was added.

## Dry-Run Boundary

The router:

- Does not call providers.
- Does not resolve or decrypt credentials.
- Does not call n8n or `WorkflowClient`.
- Does not write jobs, snapshots, events, files, or database rows.
- Does not modify `POST /api/videos`.
- Does not modify `brief_json` or any workflow payload.

The existing generation path remains unchanged and continues using its current environment-based behavior.

## Tests

Focused routing tests cover:

- Valid AI routing decisions.
- Environment credential strategy.
- Stable routing version.
- Unimplemented Pexels rejection.
- Unknown provider.
- Provider/model mismatch.
- Unavailable provider.
- Unsupported visual source.
- Unsupported credential source.
- Unsupported routing version.

Results:

- Focused routing tests: `8 passed`.
- Full backend suite: `104 passed` via `pytest backend/tests -q`.
- Frontend production build: `npm run build` passed.

The frontend still has no formal test or lint scripts.

## Compatibility Review

Read-only compatibility review confirmed:

- `POST /api/videos` remains unchanged.
- GeneratePage and `videoService.ts` remain unchanged.
- Existing provider validation, snapshots, and public responses remain unchanged.
- No n8n workflow JSON or payload construction changed.
- No provider execution or credential routing changed.
- No routing metadata is exposed publicly.

## Security Review

The routing module contains no network, database, filesystem, provider, or credential-client calls. Decisions contain only non-secret provider/model identifiers and the fixed environment strategy. The only credential-related behavior is registry availability inspection, which checks configured availability without retrieving or exposing secret values.

Existing repository-wide security findings, including pre-existing credential-like material in utility scripts and n8n execution-data risks, remain outside this checkpoint and require a separate security/authentication effort.

## Known Limitations

- The router is intentionally not wired into generation yet.
- Cloudflare availability follows the existing registry semantics and does not independently verify runtime credentials.
- Pexels and NVIDIA remain unavailable until their registry and execution support are implemented.
- Structured routing errors are currently an internal service contract, not a new HTTP endpoint.

## Stop Boundary

No dynamic n8n routing, workflow modification, stored credential resolution, provider execution, callback changes, authentication, or multi-user work was started.
