# Phase 5 Checkpoint 6B: WF18 Custom Image Integration

## Status

**LIVE_RECONCILIATION_COMPLETE**

Repository implementation and verification are complete. WF05 and WF18 were reconciled against the original live backup and current live API state, imported with preserved IDs and active states, and verified through controlled legacy/internal execution and rollback. `IMAGE_EXECUTION_MODE=legacy` remains the default.

The controlled probes used the existing Cloudflare image provider and therefore consumed provider calls. No unrelated workflow was modified, and no Pexels integration was started.

## Repository Implementation

### Files Changed

- `clipcraft/workflows/05-generate-scene-images.json`
  - `Prepare Items` now creates one `request_id` UUID per scene item using `randomUUID()`.
  - Existing `job_id`, `scene_id`, `scene_index`, and `image_prompt` fields remain unchanged.
- `clipcraft/workflows/18-ai-generate-image.json`
  - Added legacy-default `Initial Image Execution Mode?` gate.
  - Added credential-free `Build Internal Image Request` path.
  - Added per-attempt `Image Execution Mode?` gate after `Prepare Provider Attempt`.
  - Added `Prepare Internal Image Request`.
  - Added `Assign Internal Request ID`.
  - Added `CUSTOM.clipCraftImageExecute` node reference using the existing encrypted credential.
  - Added `Adapt Internal Image Result` to convert BinaryData into the existing evaluator shape.
  - Added `Preserve Request ID` after the unchanged response normalizer.
  - Existing Cloudflare HTTP node, evaluator, retry gate, normalizer, and downstream output contract remain intact.
- `clipcraft/tests/test_workflow_integration.py`
  - Added request-ID, mode-gate, branch exclusivity, BinaryData adapter, retry, request preservation, and downstream contract tests.
- `clipcraft/docker-compose.yml`
  - Added `IMAGE_EXECUTION_MODE=${IMAGE_EXECUTION_MODE:-legacy}`.
- `clipcraft/.env.example`
  - Added `IMAGE_EXECUTION_MODE=legacy`.
- `clipcraft/.env`
  - Added `IMAGE_EXECUTION_MODE=legacy`.
- `docs/superpowers/reports/2026-08-02-phase-5-checkpoint-6b-wf18-custom-image-integration.md`

No backend, frontend, renderer, TTS, caption, manifest, public API, database, Pexels, NVIDIA, or Gemini image files were changed.

## Mode Gate

### Legacy mode

`IMAGE_EXECUTION_MODE` unset, empty, invalid, or any value other than the exact string `internal`:

Workflow Trigger
  -> Initial Image Execution Mode? (legacy branch)
  -> Build Request
  -> Validate Input
  -> Prepare Provider Attempt
  -> Image Execution Mode? (legacy branch)
  -> Call Provider API
  -> Evaluate Provider Result
```

The existing Cloudflare request, credential environment variables, retry evaluator, and normalized output remain available exactly as before.

### Internal mode

Only `IMAGE_EXECUTION_MODE=internal` selects:

Workflow Trigger
  -> Initial Image Execution Mode? (internal branch)
  -> Build Internal Image Request
  -> Validate Input
  -> Prepare Provider Attempt
  -> Image Execution Mode? (internal branch)
  -> Prepare Internal Image Request
  -> Assign Internal Request ID
  -> ClipCraft Image Execute
  -> Adapt Internal Image Result
  -> Evaluate Provider Result
```

The internal path bypasses the legacy `Build Request` node, so it does not evaluate or materialize `CLOUDFLARE_AI_TOKEN`, the legacy Authorization header, or the legacy Cloudflare URL. It uses only the encrypted `ClipCraft Internal API` credential through the custom node.

No automatic fallback exists. Internal failures remain in the existing evaluator/retry path and never switch to the legacy provider branch.

## Request IDs and Retries

- WF05 creates one cryptographically random UUID per scene item before WF18 is called.
- The UUID is not derived from `job_id`, `scene_id`, or `scene_index`.
- WF18 preserves the upstream request ID on the first internal attempt.
- `Assign Internal Request ID` creates a fresh UUID when `retryCount > 0`, so each internal provider-call retry receives a new request ID.
- The internal adapter carries the exact request ID through the evaluator result.
- `Preserve Request ID` adds the exact ID to the final normalized WF18 result without exposing it through the frontend contract.
- Existing retry count and maximum retry behavior remain unchanged.

## BinaryData Mapping

`ClipCraft Image Execute` emits n8n BinaryData as `binary.image`. `Adapt Internal Image Result`:

1. Reads the BinaryData buffer with `this.helpers.getBinaryDataBuffer(0, 'image')`.
2. Rejects non-PNG MIME for this PNG-only downstream path.
3. Converts the validated buffer to the existing evaluator shape:

{
  "success": true,
  "result": { "image": "<base64>" },
  "provider": "cloudflare",
  "model": "<model>",
  "requestId": "<uuid>",
  "statusCode": 200,
  "errors": null,
  "retryable": false
}
```

The existing `Evaluate Provider Result` and `Normalize Response` nodes then produce the unchanged WF18 envelope consumed by WF05:

success
type: image
imageBase64
format: png
provider
model
retryCount
timestamp
context.jobId
context.sceneId
context.sceneIndex
```

## Persistence and Renderer Compatibility

- WF05 `Save Image File` remains unchanged.
- Persisted path remains `/data/jobs/{jobId}/scene-{NN}.png`.
- Existing scene ordering remains `scene_index.asc`.
- Existing `scenes.local_image_path` and `assets` writes remain unchanged.
- WF08 manifest generation remains unchanged.
- WF09 renderer inputs and manifest paths remain unchanged.
- JPEG is rejected by the internal WF18 adapter because current downstream persistence is explicitly PNG-only. The custom node still supports JPEG at its reusable boundary; JPEG workflow integration requires a separate approved conversion or downstream contract checkpoint.

## Verification

- Workflow integration tests: **76 passed**.
- Focused WF18 integration tests: **22 passed**.
- Custom-node tests: **28 passed**.
- Backend image endpoint tests: **20 passed**.
- Full backend suite: **262 passed**.
- Frontend build: passed (`tsc -b && vite build`).
- Docker Compose parse: passed (`docker compose config --quiet`).
- Custom-node package build and pack verification: passed during Checkpoint 6A and unchanged by this checkpoint.
- Targeted secret/log scans: no hardcoded signing secret/provider token values and no logging calls found in the new internal path or custom-node source.

## Reviews

### Security

Post-edit review found no high- or medium-severity blockers. Confirmed:

- Internal mode bypasses legacy provider credential construction.
- Internal branch contains no provider token or Authorization header.
- Custom node uses only the encrypted `ClipCraft Internal API` credential.
- HMAC, private-host restrictions, no redirects, timeout handling, response caps, and BinaryData validation remain active.
- No prompt, image bytes, base64 image, signing secret, nonce, signature, account identifier, or raw provider body is logged by the internal path.

### Compatibility

Post-edit review found no high- or medium-severity blockers. Confirmed:

- Legacy and internal branches are mutually exclusive.
- Retries re-enter the per-attempt gate and remain in the selected mode.
- Request IDs are generated and propagated correctly.
- BinaryData is adapted back to the unchanged WF18/WF05 JSON contract.
- Persistence and renderer paths remain unchanged.

### Rollback

Repository and live rollback are explicit and safe through `IMAGE_EXECUTION_MODE=legacy`; the legacy branch remains present and is the configured default. Live rollback was verified after the internal probe.

## Live Deployment and Verification

**Completed through authenticated API v1.**

Health access was available:

- `GET http://localhost:5680/healthz` returned HTTP 200.

Workflow/owner access status:

- UI login/password: failed.
- API-key `/api/v1/*` workflow access: verified for read, write, activation, deactivation, export, and deletion.
- Basic auth: no valid credentials supplied; not successfully verified separately.
- Owner credentials: unavailable; not attempted with guessed credentials.
- Legacy `/rest/*` access remains unauthorized; it was not required for the approved API-v1 checkpoint.

No credentials were guessed, reset, replaced, or exposed. No n8n database replacement or authentication reset was performed. The following were completed:

- Three-way reconciliation used the original live backup, current live API definitions, and repository workflows.
- WF05 ID `gazJuTcoSGqYdGze` and WF18 ID `18` remained stable and active.
- Fresh pre-import rollback exports were captured under `clipcraft/backups/n8n-recovery/20260801-231151Z/workflow-exports/pre-import-live/`.
- `ClipCraft Image Execute` and the encrypted `ClipCraft Internal API` credential were confirmed in the running image/API.
- Final legacy execution used one provider call and no custom node; final internal execution used one custom-node call and no legacy provider node.
- BinaryData, imageBase64, scene context, request ID, JPEG payload compatibility, and immediate legacy rollback were verified.

## Readiness

**LIVE_RECONCILIATION_COMPLETE**

Live deployment reconciliation and controlled verification are complete. The internal path is optional and not enabled by default; legacy mode remains active. Production default cutover is not part of this checkpoint.

## Migration Summary

1. Backend runtime completion: internal image endpoint completed in Checkpoint 6.
2. Text runtime completion: internal text endpoint and WF17 custom-node migration completed in Checkpoints 5A/5B.
3. Image runtime completion: WF18 repository integration is complete; live integration is pending access.
4. Custom n8n nodes completed: text and image nodes share one credential and shared signing/transport infrastructure.
5. Internal endpoints completed: text and image private HMAC endpoints are available.
6. Remaining legacy components: WF18 legacy Cloudflare HTTP branch remains active and is the default.
7. Technical debt: current downstream image persistence is PNG-only; request deduplication is not implemented; live n8n access and deployment verification are outstanding.
8. Security observations: internal mode now avoids legacy provider credential materialization; HMAC, private-host, BinaryData, size, MIME, and error-redaction controls are in place.
9. Performance observations: BinaryData avoids duplicate base64 JSON storage, but adapter conversion necessarily creates the existing WF18 base64 envelope for WF05 compatibility.
10. Recommended production cutover order: obtain n8n access, export/hash backup, confirm node/credential, validate legacy, run one isolated internal execution, verify persistence/renderer, rollback to legacy, then seek explicit approval before changing the default.
11. Estimated remaining work: live backup/import/activation and controlled verification only for this checkpoint; later work may address PNG/JPEG format generalization, retry idempotency, and default cutover.
12. Blockers before enabling internal execution by default: valid n8n owner/API access, live rollback backup, confirmed encrypted credential, controlled successful image execution, and explicit production cutover approval.

## Phase 5 Checkpoint 6C: Live Access Recovery

### Authentication Mode Discovered

- n8n version/image: `2.29.7`, container `clipcraft-n8n`.
- Basic Auth is explicitly disabled: `N8N_BASIC_AUTH_ACTIVE=false`.
- Built-in owner/user management is therefore the expected authentication mechanism.
- An `N8N_API_KEY` environment entry exists, but its validity is unverified and prior API-key workflow REST calls were rejected.
- `N8N_ENCRYPTION_KEY` is configured in the running container; its value was never printed.
- n8n is exposed on `0.0.0.0:5680` over HTTP and `/healthz` returned HTTP 200.
- No reverse proxy was found in the active Compose deployment.

### Recovery Method Used

No authentication recovery command was executed. The installed n8n image exposes `user-management:reset`, but the verified command resets user state and reassigns ownership. Because the checkpoint forbids destructive credential resets and no valid owner/API credential was available, the reset was not run.

Known access results:

- UI/password login: failed.
- API-key REST access: rejected/unauthorized.
- Basic Auth: disabled; no valid Basic Auth credentials supplied.
- Owner credentials: unavailable and not guessed.
- Internal workflow REST export: unauthorized.

No passwords, API keys, cookies, or environment secret values were guessed, printed, committed, or added to the report.

### Backup Location and Verification

Before any recovery action, a protected local backup was created at:

```text
backups/n8n-recovery/20260801-231151Z/
```

Captured areas:

- `n8n-data/`: full copy of the persistent `/root/.n8n` data volume.
- `database/`: SQLite database copy after n8n was stopped cleanly.
- `docker-compose/`: Compose and n8n Dockerfiles.
- `env/`: protected environment files, not copied into this report.
- `custom-nodes/`: current custom-node package.
- `workflow-exports/`: repository WF05/WF18 definitions.
- `checksums/`: SHA-256 checksums for non-secret workflow/config files.

Verification:

- 27 non-empty n8n-data files copied.
- Total copied n8n-data size: 475,969,650 bytes.
- SQLite database copy: 433,889,280 bytes.
- Non-secret checksum manifest exists and is non-empty.
- SQLite WAL/SHM files were present during the initial read-only inspection and were checkpointed/removed after the clean n8n stop; the database copy was taken only after that stop.
- The named volume `clipcraft_n8n_data` and configured encryption key were retained. No volume deletion or database replacement occurred.

n8n was restarted using the same Compose service and same named volumes after backup; health returned HTTP 200.

### Live State Export

Not performed. Workflow REST access remains unauthorized, so current live WF05/WF18 IDs, names, active states, version IDs, credential references, and unrelated live changes could not be safely exported or compared.

### Import Status

Not performed. WF05 and WF18 were not imported, activated, overwritten, deleted, or recreated.

The running image also lacks `ClipCraftImageExecute.node.js`; loading it requires rebuilding the custom-node n8n image, which was not performed because authenticated live workflow access and pre-import verification remain blocked.

### Credential Attachment Status

Not verifiable live. Repository WF18 references the existing encrypted `clipCraftInternalApi` credential by name/id, but live credential existence and decryptability could not be checked without authenticated workflow access.

### Controlled Execution and Rollback

Not performed. No legacy or internal WF18 execution was run, no harness was created, no Cloudflare image call was made, no asset or renderer output was created, and no live mode was changed. `IMAGE_EXECUTION_MODE` was absent from the running container, which resolves to the repository’s legacy behavior, while the repository Compose/.env configuration remains explicitly `legacy`.

Rollback verification is therefore pending. The repository legacy branch remains intact and the local pre-recovery data backup is retained.

### Final 6C Status

**BLOCKED_AUTH_RECOVERY**

Repository implementation is ready, storage/encryption backup is verified, and n8n health is restored. Live access recovery requires an authorized owner credential or scoped valid API key. The supported owner reset path was intentionally not used because it would be a destructive authentication-state operation under this checkpoint’s constraints.
