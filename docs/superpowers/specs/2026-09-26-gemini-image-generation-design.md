# Gemini Image Generation — Design

## Context

Cloudflare Workers AI free quota (10,000 neurons/day) is exhausted, blocking
scene image generation. A live probe of Gemini image generation on the
project's key (`gemini-2.5-flash-image` via `generateContent`) returned
`429 RESOURCE_EXHAUSTED` with free-tier limit 0: the model id resolves, but
the key has no image quota without billing. The user chose to enable Google
billing, then have Gemini images implemented with per-video provider choice
in the frontend picker.

Codebase hooks already present: `GEMINI_IMAGE_ENABLED` / `GEMINI_IMAGE_MODEL`
config (currently unread), registry entry `gemini-2.5-flash:image-preview`
(`implemented=False`, "Reserved for future use"), WF18 internal execution
mode (live: `IMAGE_EXECUTION_MODE=internal`), and the `ClipCraftImageExecute`
custom node. The internal image endpoint dispatches purely by
provider/model, and the frontend picker reads the registry dynamically.

## Decisions (approved)

- Approach A: native backend-only implementation; no frontend, workflow, or
  n8n changes.
- Provider role: user picks per video; no default switch, no fallback chain.
- Billing is a prerequisite: live probe + E2E run only after billing is on.
  If the probe still shows quota 0, stop before E2E.

## 1. Model lineup

Text (registry entries only, same `generateContent` call, no new code):
- `gemini-2.5-flash` (unchanged default)
- `gemini-2.5-flash-lite` (fast/cheap drafts)
- `gemini-2.5-pro` (best quality)

Image (new execution path):
- `gemini-2.5-flash-image` (supported; default when enabled)

Excluded: Imagen (`:predict` API, a second integration, not flexibility) and
deprecated models. The reserved id `gemini-2.5-flash:image-preview` is
replaced by the real image id; nothing in job data references it (only the
`test_gemini_image_capability_remains_unsupported` test does, which is
rewritten by this work).

## 2. Architecture (four units, each mirroring an existing counterpart)

1. `GeminiImageExecution` in `backend/app/services/ai/gemini_execution.py`:
   posts `generateContent` with `responseModalities: [TEXT, IMAGE]`,
   extracts `candidates[0].content.parts[].inlineData.data` (base64),
   enforces the existing 4MB cap and transport-injection pattern for tests.
2. `GeminiAdapter` gains `image_generation` with prompt-only params
   (mirrors Cloudflare's image branch).
3. Registry: image entry `implemented=True`; availability gated on the
   currently dead `GEMINI_IMAGE_ENABLED` / `GEMINI_IMAGE_MODEL` config
   (default model `gemini-2.5-flash-image`), so the picker lists it only
   when enabled. New text models are available whenever the key exists,
   same rule as today.
4. Registration: `register("gemini", "image_generation", ...)` so the
   internal image endpoint, routing validation, and credential resolution
   work unchanged.

## 3. Data flow

Picker (`provider_id=gemini`, `model_id=gemini-2.5-flash-image`) → WF18
internal request → credential resolution (environment key, same as text) →
routing validation (registry implemented + flag-gated available) → adapter
(prompt-only) → `GeminiImageExecution` → base64 through the existing
`InternalImageExecutionResponse` shape. New text models flow through the
untouched text path. No branch on provider name exists anywhere in this
chain.

## 4. Error handling

Same taxonomy as sibling executors, no new codes: bad key →
`invalid_credentials`, billing/quota → `quota_exceeded`, 429 →
`rate_limited`, empty/blocked/no-inlineData → `empty_response` /
`blocked_response` / `malformed_response`, oversize capped. No secrets in
logs (existing redaction pattern).

## 5. Testing

- Rewrite `test_gemini_image_capability_remains_unsupported` into a support
  matrix mirroring the Cloudflare image tests: success extracts base64,
  empty/malformed/blocked shapes rejected, HTTP errors normalized,
  transport timeout safe.
- Adapter image params: prompt required, extras rejected.
- Registry: flag off → image unavailable with text available; flag on →
  image available with configured model.
- Internal image endpoint with a gemini selection.
- Full backend suite stays green except the two known pre-existing
  credential-code failures (`AI_CREDENTIAL_INVALID` vs
  `AI_CREDENTIAL_MISSING` in the stored-credential fallback tests).

## 6. Verification gate (in order)

1. Unit/integration tests green.
2. Live probe against the billing-enabled key returns an image (not 429).
   If quota is still 0, stop here.
3. Full E2E video with Gemini images, then a frame check per project rule.

## Out of scope

Imagen or other non-`generateContent` image APIs, automatic fallback
chains, default-provider switches, frontend or workflow changes, and any
change to Cloudflare/NVIDIA/Pexels behavior.
