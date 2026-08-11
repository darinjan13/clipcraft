# Phase 2 Checkpoint 2: Generate Provider Selection

## Status

Implemented and verified. This checkpoint stops before dynamic routing or n8n integration.

## Files Changed

- `frontend/src/features/generate/pages/GeneratePage.tsx`
- `frontend/src/features/generate/components/GenerateForm.tsx`
- `frontend/src/features/generate/components/ModelSelector.tsx`
- `frontend/src/features/generate/components/GenerationProgress.tsx`
- `frontend/src/features/videos/types.ts`
- `frontend/src/features/videos/store/useVideoStore.ts`
- `frontend/src/features/videos/api/videoService.ts`
- `frontend/src/components/ui/Progress.tsx`
- `docs/superpowers/reports/2026-07-30-phase-2-checkpoint-1-settings-ui.md`

No backend, n8n, workflow, or authentication files were changed.

## Generate Page Structure

The existing Generate page remains at `/generate` with its existing creative brief, output controls, progress preview, library navigation, and submission flow.

The AI configuration area now provides:

- Separate text provider and text model selects.
- Separate image provider and image model selects.
- Visual source selection using canonical `ai` and `pexels` values.
- Conditional Pexels media type and orientation fields.
- Loading, retry, unavailable-provider, and inline generation-error states.

Pexels is currently disabled because the canonical backend registry reports it as unimplemented and unavailable. No Pexels API calls are made.

## Provider And Model State Design

- `useVideoStore` retains the existing draft plus frontend-only visual-source fields.
- `setDraft` records fields touched by the user.
- `initializeDraft` fills only empty, untouched fields, preventing asynchronous registry or preference responses from overwriting user input.
- Provider changes immediately choose the first valid available model for that provider.
- Model choices are filtered by provider, capability, enabled state, implemented state, deprecation state, and availability.
- No credentials or credential metadata enter the Generate form state.

## Colon-Containing Model ID Fix

The old selector serialized values as `provider:model` and parsed them with `split(':')`, corrupting IDs such as `gemini-2.5-flash:image-preview`.

The selector now stores provider and model as separate state fields. Provider and model option values use the exact opaque raw strings returned by the backend. No delimiter parsing or canonical ID rewriting remains.

IDs including `provider/model:version`, `@cf/provider/model-name`, and `model:variant:version` round-trip unchanged through selection and request preparation.

## Preference Initialization

Generate loads:

- `GET /api/ai/models`
- `GET /api/settings/preferences`

Preference values initialize only untouched fields. Existing draft values take priority. If a preference is unavailable, disabled, deprecated, unimplemented, or mismatched, the frontend falls back to the canonical available registry default and then the first available compatible provider/model. Preference-load failure falls back to canonical registry values.

Changing a provider invalidates only its dependent model selection. Unrelated form fields remain unchanged.

## Existing Snapshot Behavior

Generate does not reopen or rewrite historical jobs. Existing backend regeneration and duplication flows remain unchanged and continue to preserve complete source snapshots. Legacy jobs are not given invented historical provider/model values by this frontend checkpoint.

## Request Fields Actually Sent

The existing `POST /api/videos` request remains in use. The request sends the existing supported fields:

- `title`
- `prompt`
- `duration`
- `style`
- `voice`
- `captions`
- `aspectRatio`
- `text_provider`
- `text_model`
- `image_provider`
- `image_model`

The existing `brief_json` construction and backend validation remain untouched.

## Fields Deliberately Not Sent

These frontend-only fields are stripped before serialization because the current `VideoDraft` API does not support them:

- `visual_source`
- `pexels_media_type`
- `pexels_orientation`

No credentials, masked credentials, or Settings credential responses are sent during generation.

## Accessibility And Responsive Review

- Provider/model controls use separate labeled native selects with fieldset/legend grouping.
- Selects remain keyboard-operable and preserve visible focus states.
- Loading options expose busy state; unavailable-provider states include a Settings link.
- Generate now uses a native form and supports keyboard submission.
- Generation failures have persistent inline alert text in addition to the existing toast.
- Progress exposes status and progressbar semantics, with indeterminate treatment while the request is active.
- CTA controls stack and become full-width on narrow screens.

Read-only accessibility review found no remaining Checkpoint 2 blocker. Existing unrelated AppShell icon-button concerns remain outside this checkpoint.

## Compatibility Review

- `npm run build` passed, including TypeScript compilation and the Vite production build.
- Frontend scripts are limited to `dev`, `build`, and `preview`; no frontend test or lint scripts exist.
- The existing `/api/videos` endpoint and request shape remain in use.
- `brief_json` compatibility remains unchanged.
- Generate, Settings, backend, n8n, and workflow behavior remain otherwise unchanged.
- No stored credential use, provider routing, Pexels calls, NVIDIA generation, workflow modification, authentication, or multi-user behavior was added.

## Remaining Integration Boundary

Dynamic provider routing requires a later backend/workflow checkpoint. That checkpoint must define how visual source, Pexels preferences, stored credential source, and provider/model snapshots are accepted and consumed without changing the existing `brief_json` contract or exposing secrets to the browser.

## Unresolved Limitations

- Pexels is visible only as an unavailable option until the canonical registry marks it implemented and available.
- Visual-source and Pexels selections are retained in frontend state but intentionally do not affect backend generation yet.
- The backend currently reports Cloudflare availability independently of stored Settings credentials, so a later execution may still fail if runtime credentials are absent.
- Existing preview/regeneration/duplication UI flows were not redesigned; their backend snapshot behavior remains the source of truth.
- No live browser, end-to-end API, frontend test, or lint execution was available beyond the successful production build.
