# Phase 2 Checkpoint 1: Settings UI

## Status

Approved and complete.

## Files Changed

- `frontend/src/features/settings/api/queryKeys.ts`
- `frontend/src/features/settings/api/settingsService.ts`
- `frontend/src/features/settings/types.ts`
- `frontend/src/features/settings/components/ProviderConnectionCard.tsx`
- `frontend/src/features/settings/components/CredentialDialog.tsx`
- `frontend/src/features/settings/components/PreferencesSection.tsx`
- `frontend/src/features/settings/pages/SettingsPage.tsx`
- `frontend/src/components/ui/Modal.tsx`
- `frontend/src/components/ui/Toast.tsx`
- `frontend/src/components/ui/Input.tsx`
- `frontend/src/components/ui/Select.tsx`

No backend, n8n, workflow, or Generate files were changed for this checkpoint.

## Route And Components

The existing `/settings` route now renders:

- Provider Connections: registry-driven provider cards with configure, test, and delete actions.
- Generation Defaults: text provider/model, image provider/model, and visual-source preferences.
- Workspace: existing local workspace controls, preserved unchanged in behavior.

Supporting components include `ProviderConnectionCard`, `CredentialDialog`, `PreferencesSection`, and shared modal, toast, input, and select primitives.

## Backend Endpoints Consumed

- `GET /api/ai/providers`
- `GET /api/ai/credentials`
- `PUT /api/ai/credentials/{provider_id}`
- `POST /api/ai/credentials/{provider_id}/test`
- `DELETE /api/ai/credentials/{provider_id}`
- `GET /api/settings/preferences`
- `PUT /api/settings/preferences`

## Credential And Preference Behavior

- Credentials are entered through password inputs and submitted only to the backend.
- Secrets are never placed in browser storage, URLs, logs, or rendered responses.
- Existing credentials are represented by masked metadata only.
- Test and delete operations invalidate the credential query and show toast feedback.
- Preferences load asynchronously, initialize the form once, track dirty state, validate selections, and save through the preferences endpoint.
- Preferences remain informational for generation and do not change backend routing.

## Accessibility Improvements

- Modal dialogs include dialog semantics, descriptions, initial focus, Escape handling, and focus containment.
- Toasts use appropriate live-region roles.
- Inputs, selects, buttons, switches, and read-only fields have labels or accessible names and visible focus states.
- Settings tabs support roving tab focus plus Arrow, Home, and End keyboard navigation.
- Error and unavailable states use accessible alert/status text.

## Availability Filtering

Provider and model choices require enabled, implemented, capability-compatible entries. Available entries are preferred; an existing unavailable selection may remain visible for transparent editing and is marked as requiring credentials. Deprecated models are excluded.

## Verification

`npm run build` passed, including TypeScript compilation and the Vite production build.

The frontend has no configured test or lint scripts; only `dev`, `build`, and `preview` scripts exist.

## Compatibility Confirmation

Generate, n8n, backend behavior, existing generation requests, and workflow contracts remain unchanged. Stored credentials and preferences are not used to route generation in this checkpoint.

## Known Limitations

- Provider routing and stored credential use during generation remain future work.
- Preferences are not yet consumed by backend generation.
- Pexels and NVIDIA integrations are not implemented.
- Frontend automated test and lint infrastructure is absent.
- Existing Generate model selection still requires the separate Checkpoint 2 colon-containing model ID fix.
