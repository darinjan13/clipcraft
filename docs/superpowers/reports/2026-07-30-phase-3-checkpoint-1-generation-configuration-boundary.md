# Phase 3 Checkpoint 1: Generation Configuration Boundary

## Status

Implemented and verified. Dynamic provider routing and n8n changes remain deferred.

## Files Changed

- `backend/app/models.py`
- `backend/app/main.py`
- `backend/app/services/ai/provider_registry.py`
- `backend/tests/test_api.py`
- `backend/tests/test_preferences.py`
- `frontend/src/features/videos/types.ts`
- `frontend/src/features/videos/api/videoService.ts`

No migration was required. Existing nullable snapshot migration `009_video_job_configuration_snapshots.sql` already provides the required columns.

## Request Fields Added

`POST /api/videos` now accepts these optional fields:

- `text_provider`
- `text_model`
- `visual_source`
- `image_provider`
- `image_model`
- `credential_source`
- `provider_configuration_version`
- `pexels_media_type`
- `pexels_orientation`

Pexels media fields are accepted at the request boundary for validation but are not persisted because no approved `video_jobs` storage columns exist for them.

## Validation Rules

- Text provider and model must be supplied together for configured requests.
- AI visual requests require a complete image provider/model pair.
- Providers and models are validated through the canonical registry.
- Provider/model relationships, capabilities, enabled state, implemented state, availability, and deprecation are checked.
- Pexels visual source accepts no AI image snapshot values and validates media type/orientation when supplied.
- Visual source must be `ai` or `pexels`.
- Only `credential_source: environment` is accepted because stored credentials are not used for generation.
- `provider_configuration_version` is restricted to the stable value `"1"`.
- Opaque model IDs are never split or rewritten; colon-containing IDs persist exactly.
- Validation failures return structured `{ code, message }` details without registry internals or secrets.

## Snapshot Persistence

- Legacy requests without configuration fields create no invented snapshot.
- Explicit valid configuration is persisted only in the existing nullable snapshot columns.
- AI snapshots persist text and image provider/model identifiers, visual source, `environment`, and version `1`.
- Pexels snapshots persist text configuration, `visual_source: pexels`, `environment`, and version `1`; AI image columns remain null.
- No API keys, credential IDs, encrypted blobs, masked values, account IDs, or provider responses are stored.
- No historical backfill or destructive migration was added.
- Public `Video` responses remain unchanged and do not expose snapshot fields.

## Credential Source Decision

Current jobs explicitly use `credential_source: environment`. The request boundary rejects `stored` because encrypted Settings credentials are not yet consulted during generation. This value records the current execution boundary only and does not claim stored-credential routing.

## Provider Configuration Version

`provider_configuration_version` is the stable non-secret schema/routing boundary version `"1"`. It is not derived from credentials, ciphertext, timestamps, account IDs, or database row IDs.

## Frontend Request Changes

`createVideo` now sends:

- Existing generation fields.
- Exact selected text provider/model.
- Exact selected image provider/model only for AI visuals.
- `visual_source` when selected.
- Pexels media fields only for Pexels visuals.
- `credential_source: environment` and `provider_configuration_version: 1`.

It sends no credentials or masked credential values, omits image fields for Pexels, and preserves the existing submission/progress/error behavior. The Generate UI blocks incomplete selections before submission.

## Regeneration And Duplication

- Complete AI snapshots are copied exactly.
- Complete Pexels snapshots with null AI image columns are copied exactly.
- Legacy or incomplete source rows do not receive invented current defaults.
- Source rows and their existing `brief_json` remain unchanged.
- Colon-containing model IDs remain unchanged through derived jobs.

## n8n Payload Compatibility

No n8n workflow files or webhook payload construction changed. The current FastAPI create path inserts directly into `video_jobs`; it does not call `WorkflowClient.create_job`. Therefore no new snapshot fields are forwarded to n8n, and the existing environment-based execution boundary remains intact.

## brief_json Compatibility

No new visual-source, credential-source, version, or Pexels fields were added to `brief_json`. Existing provider/model keys already present in the current brief construction were preserved unchanged; this checkpoint does not add or remove them. The existing workflow-facing brief structure remains otherwise unchanged.

## Verification Results

- Focused generation/API tests passed during implementation, including validation, Pexels handling, exact colon IDs, legacy behavior, and snapshot copying.
- Backend suite: `96 passed` via `pytest backend/tests -q`.
- Registry, credential, connection, and preferences checks: `41 passed`.
- Frontend production build: `npm run build` passed, including TypeScript compilation and Vite build.
- Frontend has no configured test or lint scripts; no frontend test or lint pass is claimed.
- Production-source secret scan found no literal API-key patterns in `backend/app`, `frontend/src`, or `clipcraft/workflows`.
- Manual n8n inspection confirmed no new payload path or workflow invocation was introduced.

## Compatibility Review

Read-only API-contract, schema, security, and frontend compatibility reviews completed. Legacy request callers remain valid, preferences remain frontend initialization input rather than silent FastAPI defaults, public response shape is unchanged, and no backend routing behavior was added.

## Security Review

The new boundary stores only allowlisted non-secret identifiers and does not place credentials in requests, jobs, snapshots, `brief_json`, n8n payloads, or responses. Existing repository utility scripts contain pre-existing credential-like material identified by the security review; those secrets should be rotated and removed in a separate security/authentication checkpoint and were not modified here.

## Deferred Pexels Persistence Fields

`pexels_media_type` and `pexels_orientation` remain request-only and frontend-retained. Persisting them requires an explicit additive schema decision and future routing need. No `video_jobs` columns were added in this checkpoint.

## Unresolved Limitations

- Stored credentials are still not used by generation.
- Provider/model snapshots are persisted but do not influence execution yet.
- The backend’s existing brief already contains provider/model keys; removing or reshaping them would be a separate compatibility decision.
- Pexels and NVIDIA execution remain unavailable.
- Existing unauthenticated API and broader repository secret findings remain outside this checkpoint.
- No live AI-provider or n8n execution was performed.
