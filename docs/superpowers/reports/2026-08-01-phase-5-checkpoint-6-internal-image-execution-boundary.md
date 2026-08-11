# Phase 5 Checkpoint 6: Internal Image Execution Boundary

## Status

**Complete. A private, HMAC-protected `POST /internal/ai/image/execute` endpoint now provides Cloudflare FLUX.1 scene-image generation through the existing provider stack, with zero changes to n8n, WF17, WF18, live text execution, `TEXT_EXECUTION_MODE`, the public API, the frontend, or the database.**

This checkpoint establishes the image-side analog of the text execution boundary from Checkpoint 4. The endpoint mirrors `/internal/ai/text/execute` exactly in transport security, request validation, routing, credential resolution, execution, and error normalization, and is verified by 20 focused tests plus the full backend suite (262 passed), the clipcraft contract suite (72 passed), the frontend build, and the custom n8n node suite (17 passed). Four read-only reviews (security, architecture, workflow-contract, code/test quality) completed; all findings are low-severity or design notes.

## Scope

- Add `backend/app/services/internal_image_execution.py` (new, mirrors `internal_text_execution.py`).
- Add `POST /internal/ai/image/execute` to `backend/app/main.py` (`include_in_schema=False`), reusing the shared `NonceStore`, `verify_internal_signature`, and `InternalExecutionFailure` normalization.
- Add `backend/tests/test_internal_image_execution.py` (20 tests).
- Do NOT change: WF05, WF18, WF17, any n8n workflow, `TEXT_EXECUTION_MODE`, the text execution path, public `/api/*` routes, the frontend, the database, or the legacy Cloudflare image path. Do NOT create the custom image n8n node (deferred to a later checkpoint).

## Files Changed

- `backend/app/services/internal_image_execution.py` (new)
- `backend/app/main.py` (service registration + route)
- `backend/tests/test_internal_image_execution.py` (new)
- This report.

## Request Contract

`InternalImageExecutionRequest` (`extra="forbid"`, `protected_namespaces=()`):

```json
{
  "job_id": "<uuid>",
  "provider_id": "cloudflare",
  "model_id": "@cf/black-forest-labs/flux-1-schnell",
  "credential_source": "environment | stored",
  "operation": "image_generation",
  "input": {
    "prompt": "A cat on a chair",
    "image_prompt": "...", "imagePrompt": "...",
    "visual_prompt": "...", "visualPrompt": "...",
    "scene_id": "scene-1", "scene_index": 0,
    "width": 512, "height": 512,
    "steps": null, "seed": null
  },
  "routing_version": "1",
  "request_id": "<uuid>"
}
```

- Prompt is resolved with the documented precedence `prompt ?? image_prompt ?? imagePrompt ?? visual_prompt ?? visualPrompt`, matching the deployed WF18 prompt contract (see `clipcraft/video-tools/sanitize_image_prompts.py`). At least one non-empty prompt is required (`model_validator`), else 422.
- `width`/`height`/`steps`/`seed` are accepted and validated (width/height ≤ 2048, steps ≤ 50, seed ≤ 2^32-1) but are **reserved, forward-compatible metadata**: the shared `CloudflareAdapter` whitelists only `prompt` for `image_generation`, so they are not yet forwarded to the provider. `scene_id`/`scene_index`/`width`/`height` are echoed in the response for caller correlation. Forwarding generation parameters to Cloudflare is deferred to a later checkpoint (would require touching shared `adapters.py`/`cloudflare_execution.py`).
- Top-level and nested `extra="forbid"` reject credential/URL/header smuggling with 422 and no content leakage.

## Response Contract

`InternalImageExecutionResponse` (normalized snake_case, mirrors the text endpoint):

```json
{
  "request_id": "<uuid>", "job_id": "<uuid>",
  "provider_id": "cloudflare",
  "model_id": "@cf/black-forest-labs/flux-1-schnell",
  "capability": "image_generation", "status": "completed",
  "image_base64": "<base64 PNG>", "format": "png",
  "width": 512, "height": 512,
  "scene_id": "scene-1", "scene_index": 0,
  "elapsed_ms": 123.45, "routing_version": "1"
}
```

- `image_base64` is validated as decodable base64, non-empty, and bounded (decoded size ≤ 4 MB) before it is returned (`_validate_image_payload`); invalid/empty/oversized payloads map to `AI_RESPONSE_INVALID` / `AI_RESPONSE_EMPTY` (502).
- **Envelope decision (resolved during review).** The endpoint returns the normalized internal JSON contract, not the WF18 wire envelope. WF18's `Normalize Response` emits `{success, imageBase64, format, context:{jobId,sceneId,sceneIndex}}`, and WF05's `Save Image File` consumes `response.imageBase64` + `response.context.*`. The endpoint does not reproduce that envelope because (a) consistency with the established text boundary contract, and (b) the translation layer lives in the custom n8n node, exactly as `ClipCraftTextExecute` maps the text endpoint's `request_id`/`job_id`/`text` into WF17's `success`/`content`/`provider` shape (`src/nodes/ClipCraftTextExecute/ClipCraftTextExecute.node.js:165-197`). A future `ClipCraftImageExecute` node maps `image_base64`→`imageBase64`, `provider_id`→`provider`, `model_id`→`model`, and wraps `{job_id,scene_id,scene_index}` as `context`. WF05/WF18 remain untouched.

## Implementation Notes

- `InternalImageExecutionService` reuses, without reimplementation: `DryRunProviderRouter`, `RoutingConfiguration`, `RoutingDecision`, `CredentialResolver`, `ExecutionContext`, `ProviderExecutor`, `ProviderExecutionRegistry`, `default_adapter_registry`, the registered `CloudflareImageExecution`, and the `_routing_failure`/`_credential_failure`/`_execution_failure`/`InternalExecutionFailure` helpers imported from `internal_text_execution.py`.
- Routing drives the image slot from the request (`provider_id`/`model_id`, `visual_source="ai"`) and fixes the text slot to `cloudflare`/`@cf/meta/llama-3.1-8b-instruct`. The router requires a valid, available text pair; the Cloudflare text model is always available (its availability does not depend on env keys), so the image endpoint works with only Cloudflare configured and does not impose a Gemini-key requirement. The text slot is never executed.
- The route handler mirrors the text handler: content-length pre-check + actual-body size cap (1 MB, 413) before HMAC, required `X-ClipCraft-*` headers (401 `INTERNAL_AUTH_REQUIRED`), `verify_internal_signature` against the shared `app.state.internal_nonce_store` (401 replay / 403 invalid signature), `model_validate_json` (422), then `execute` with `InternalExecutionFailure` mapping and a final generic 502 catch. No body/signature/nonce/prompt/image content is ever logged.

## Verification

- Backend: `py -m pytest` → **262 passed** (20 new image-endpoint tests).
  - New tests cover: hidden-from-OpenAPI + missing auth, oversized body, environment happy path, stored-credential happy path (encryption round-trip, no env fallback), prompt-beats-alias + alias precedence + alias fallback, missing prompt, whitespace-only prompt, top-level and nested extra-field rejection, unknown provider/model, nonce replay, invalid signature (403), invalid/empty base64 (502), provider error normalization (401, no leak), exact internal route count (only text+image, both hidden), and cross-route shared nonce store.
- clipcraft contracts: `py -m pytest clipcraft/tests` → **72 passed**.
- Frontend: `npm run build` → success (no frontend changes; regression guard).
- Custom n8n node: `npm test` → **17 passed** (no node changes; regression guard).
- Secret/log scan: no `logging`/`print` in new files; no secrets (`N8N_INTERNAL_SIGNING_SECRET` value, credential id, Cloudflare tokens) present in changed files; tests assert no secret leakage in responses.

## Read-Only Reviews

1. **Security review** — no high/medium issues. HMAC flow, replay protection, single shared NonceStore, secret non-leakage, `extra="forbid"`, size caps, and normalized errors all confirmed. Low/info items only (shared-code NonceStore capacity semantics, exception-string classification, unreachable decoded-size redundancy, hardcoded `format: "png"`, validated-but-unforwarded params) — none new to this checkpoint.
2. **Architecture review** — "no duplication / no public change" constraint **holds**. Every component reused; no second auth/routing/credential/executor system; route is `/internal/*` and `include_in_schema=False`; diff confined to `main.py`, `internal_image_execution.py`, and the test file. Low items: near-verbatim route boilerplate (acceptable parity with text route), hardcoded text slot (deliberate), dead `RegistryValidationError` catch (pre-existing in text service).
3. **Workflow-contract review** — request-side fully compatible (alias union + precedence). Result-side not drop-in with WF18/WF05 wire envelope by design; translation is the future node's job (see Response Contract). Cloudflare `result.image` handling and size caps confirmed. No workflow files referenced or modified.
4. **Code/test-quality review** — high parity with text endpoint; coverage adequate for a security-sensitive endpoint; deterministic, no flakiness. Low gaps (top-level extra-field, prompt-beats-alias, 403 signature path) were added after review.

## Compliance with Hard Stops

- No live n8n workflow modified (WF05, WF17, WF18 and all others untouched).
- No custom image n8n node created.
- No `TEXT_EXECUTION_MODE` change; text execution path untouched.
- No public API, frontend, database, or migration changes.
- No legacy Cloudflare image path removed.
- No live provider call performed; **no Cloudflare image quota consumed** (all execution tests use a fake transport).

## Next Steps (future checkpoints)

- Wire a custom `ClipCraftImageExecute` n8n node (mirroring `ClipCraftTextExecute`) to call this endpoint and translate the normalized response into the WF18/WF05 envelope.
- Optionally forward `width`/`height`/`steps`/`seed` to Cloudflare by extending the shared `CloudflareAdapter` image whitelist and `CloudflareImageExecution` body (shared-code change; outside this checkpoint's boundary).
