# Phase 5 Checkpoint 6A: Custom Image Execute Node

## Status

**Complete. `ClipCraft Image Execute` is implemented and packaged alongside `ClipCraft Text Execute`, reusing the existing encrypted credential, deterministic serialization, HMAC signing, private-host transport, timeout handling, response limits, and safe error policy.**

WF18, WF05, live image workflows, backend code, frontend code, public APIs, database schema, renderer, and provider routing were not modified. No live provider call was made and no Cloudflare image quota was consumed.

## Files Changed

- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/src/shared/clipcraftInternal.js` (new shared transport/signing infrastructure)
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/src/nodes/ClipCraftImageExecute/ClipCraftImageExecute.node.js` (new node)
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/src/nodes/ClipCraftTextExecute/ClipCraftTextExecute.node.js` (refactored to consume shared infrastructure without changing its contract)
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/package.json` (registers the second node)
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/test/clipcraft-image-execute.test.js` (new focused tests)
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/test/package-contract.test.js` (two-node manifest assertion)
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/README.md` (package documentation)
- Generated `dist/` files from the package build.

No Dockerfile, compose, credential, workflow JSON, backend, frontend, or database files were changed.

## Implementation Summary

`ClipCraftImageExecute`:

- Uses node name `clipCraftImageExecute` and the existing `clipCraftInternalApi` credential.
- Builds the normalized backend request for `image_generation`:
  - `jobId` → `job_id`
  - `sceneId` → `input.scene_id`
  - optional `sceneIndex` → `input.scene_index`
  - `requestId` → `request_id`
  - provider/model/credential/routing values mapped directly
  - prompt, width, height, seed, and steps mapped into `input`
- Calls `/internal/ai/image/execute` using the shared private-host transport.
- Returns one n8n item per input with `pairedItem` preserved.

## Shared Infrastructure

`src/shared/clipcraftInternal.js` owns:

- Deterministic JSON serialization and 1 MB request protection.
- Exact-body HMAC-SHA256 signing.
- Private-host and DNS-pinning checks.
- No-redirect HTTP transport.
- Timeout handling and response-size protection.
- Shared safe error codes/messages.
- Shared credential-independent transport handling.

The text node now wraps these helpers with its text-specific path and response normalizer. The image node supplies its image-specific path and normalizer. Signing, credential loading, transport, and SSRF logic are not duplicated.

## BinaryData Strategy

The node uses `this.helpers.prepareBinaryData()` and returns:

```js
{
  json: {
    success,
    status,
    type,
    provider,
    model,
    mimeType,
    format,
    width,
    height,
    elapsedMs,
    routingVersion,
    jobId,
    sceneId,
    sceneIndex,
    retryCount,
    timestamp
  },
  binary: { image: preparedBinaryData },
  pairedItem: { item: index }
}
```

The base64 image is never copied into JSON. This avoids a second large copy and keeps downstream image processing n8n-native. The filename is `image.png` or `image.jpg` based on detected MIME.

## MIME Validation

The node strictly validates base64, checks decoded size against 4 MB, and validates magic bytes:

- PNG: `89 50 4E 47 0D 0A 1A 0A` → `image/png`, `.png`
- JPEG: `FF D8 FF` → `image/jpeg`, `.jpg`

Unsupported or malformed image data returns `AI_RESPONSE_INVALID`. Empty data returns `AI_RESPONSE_EMPTY`.

## Security Verification

- Existing encrypted `ClipCraft Internal API` credential reused; no second credential type.
- Exact serialized request bytes are signed and sent unchanged.
- Timestamp, nonce, and signature headers are shared with the backend contract.
- Private-host validation, DNS pinning, no redirects, request caps, response caps, and timeout handling are shared with the text node.
- Provider credentials, signing secrets, signatures, nonces, account identifiers, prompts, raw provider responses, image bytes, and base64 image data are not emitted in JSON errors or logs.
- Error output uses allowlisted codes and static messages.
- Post-implementation security review found no blocking issues. Remaining findings were low severity: optional `sceneIndex` requires the caller to populate it, and JPEG requires a future adapter because current WF05 writes PNG filenames.

## Test Results

- Custom-node suite: **28 passed**.
- Backend image endpoint tests: **20 passed**.
- Full backend suite: **262 passed**.
- Workflow contract tests: **72 passed**.
- Frontend build: passed (`tsc -b && vite build`).
- Package build: passed (`npm run build`).
- Package dry-run: passed (`npm pack --dry-run`); both node files and the shared helper are included in `dist`.
- Source secret/log scan: no logging calls and no credential/test-secret literals found in package source.

Focused coverage includes credential reuse, shared signing, exact request bytes, BinaryData conversion, PNG, JPEG, MIME preservation, width/height, scene index, invalid base64, empty image, unsupported MIME, oversized decoded image, Cloudflare success, timeout, quota, invalid credential, replay, failure normalization, secret redaction, prompt redaction, image redaction, and shared helper usage.

## Workflow Compatibility

WF18 and WF05 remain unchanged. A future image workflow adapter can reconstruct the current WF18 envelope:

| Node output | Future WF18 field |
|---|---|
| BinaryData `image` | `imageBase64` after explicit conversion |
| `success` | `success` |
| `type` | `type` |
| `format`/`mimeType` | `format` |
| `provider` | `provider` |
| `model` | `model` |
| `retryCount` | `retryCount` |
| `timestamp` | `timestamp` |
| `jobId` | `context.jobId` |
| `sceneId` | `context.sceneId` |
| `sceneIndex` | `context.sceneIndex` |

The node is ready for future WF18 integration when the caller supplies `sceneIndex`. PNG output is directly compatible with the current WF05 file-writing assumptions. JPEG support is preserved at the node boundary, but a future workflow adapter must choose an appropriate filename/format because WF05 currently writes every scene as PNG.

The backend currently validates and echoes width/height but forwards only `prompt` through the existing provider adapter. This checkpoint intentionally does not modify backend/provider execution code.

## Readiness

**Ready for a future WF18 integration checkpoint.** This checkpoint does not perform production cutover, modify WF18, modify live image workflows, or consume Cloudflare quota.
