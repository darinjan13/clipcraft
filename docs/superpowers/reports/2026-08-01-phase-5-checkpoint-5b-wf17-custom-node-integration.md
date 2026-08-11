# Phase 5 Checkpoint 5B: WF17 Custom-Node Integration

## Status

**Complete. WF17 now integrates the approved `CUSTOM.clipCraftTextExecute` custom node as an exclusive `internal` branch, `TEXT_EXECUTION_MODE` defaults to `legacy`, and both branches were verified with controlled live executions.**

The HMAC signing blocker from Checkpoint 5 is resolved by the Checkpoint 5A custom node. This checkpoint wires that node into WF17 behind a single environment-gated branch, pins the encrypted live credential, re-imports the workflow into the live n8n instance, and verifies both the internal and legacy paths end to end against the live backend and live Cloudflare.

## Scope

- `clipcraft/workflows/17-ai-generate-text.json`: add an `internal` branch gated by `$env.TEXT_EXECUTION_MODE === "internal"`.
- Caller and downstream contracts (WF01, WF04) remain unchanged. WF17 still returns the same normalized shape (`success`, `type: "text"`, `result`, `provider`, `model`, `retryCount`, `timestamp`).
- `TEXT_EXECUTION_MODE` defaults to `legacy`, so production traffic is unaffected until an operator opts in.
- Cloudflare remains the only text provider in the internal branch. Gemini routes through the backend are implemented but not enabled in this checkpoint.

## Files Changed

- `clipcraft/workflows/17-ai-generate-text.json`
- `clipcraft/tests/test_workflow_integration.py`
- `clipcraft/docker-compose.yml`
- `clipcraft/.env`
- `backups/5b-live-wf17/17-ai-generate-text-live-backup.json` (pre-import live backup)
- `backups/5b-live-wf17/17-ai-generate-text-live-import.json` (import copy with live credential)
- `backups/5b-live-wf17/5b-controlled-test-harness.json` (temporary controlled-test harness, removed from live)
- This report.

## WF17 Node Layout (15 nodes)

```text
Workflow Trigger
  -> Build Request
  -> Validate Input
     true -> Prepare Provider Attempt
             -> Text Execution Mode?  ($env.TEXT_EXECUTION_MODE === "internal")
                internal -> Prepare Internal Request
                           -> ClipCraft Text Execute (CUSTOM.clipCraftTextExecute)
                           -> Adapt Internal Result
                legacy   -> Call Provider API (HTTP, direct Cloudflare)
                           -> Adapt Legacy Result
             -> Evaluate Provider Result
             -> Retryable Failure?
                true  -> Increment Retry -> Prepare Provider Attempt
                false -> Normalize Response
     false -> Handle Validation Error -> Normalize Response
```

Node ids:

- `wf17-mode-...000000000011` — `Text Execution Mode?`
- `wf17-internal-prepare-...000000000012` — `Prepare Internal Request`
- `wf17-internal-node-...000000000013` — `ClipCraft Text Execute`
- `wf17-internal-adapt-...000000000014` — `Adapt Internal Result`
- `wf17-legacy-adapt-...000000000015` — `Adapt Legacy Result`

## Mode Behavior

The `Text Execution Mode?` IF node compares `$env.TEXT_EXECUTION_MODE` against the literal `internal`.

- Not set or anything other than `internal` -> legacy branch (`Call Provider API`).
- `internal` -> internal branch (`Prepare Internal Request` -> custom node).

`TEXT_EXECUTION_MODE` is plumbed through compose as:

```yaml
- TEXT_EXECUTION_MODE=${TEXT_EXECUTION_MODE:-legacy}
```

and set in `.env` to `legacy`. The running live n8n container has no `TEXT_EXECUTION_MODE` set, so the gate resolves to legacy by default. A future cutover only requires restarting n8n with the env var set to `internal`; no workflow edit is required.

## Internal Branch Data Flow

`Prepare Internal Request` reads the original caller payload from the `Workflow Trigger` node (`$('Workflow Trigger').first()?.json`), not from its direct input. This is the critical fix discovered during live verification: `Build Request` collapses its input into `{isValid, provider, url, headers, body}`, so a naive `$input` read loses `jobId`, `requestId`, and `prompt`. The internal branch must read the trigger source to preserve caller data.

The custom node receives a normalized internal request (jobId, requestId, providerId, modelId, credentialSource, routingVersion, prompt, systemPrompt, temperature, maxOutputTokens, responseFormat, timeoutMs) via the encrypted `ClipCraft Internal API` credential, signs it with HMAC-SHA256 over the exact serialized body, and calls:

```text
POST http://clipcraft-backend:8000/internal/ai/text/execute
```

`Adapt Internal Result` converts the node output into the shared evaluator shape (`success`, `result`, `provider`, `model`, `statusCode`, `errors`, `retryable`), which converges into `Evaluate Provider Result` alongside the legacy adapter.

## Node Type Resolution

n8n 2.29 resolves node types as `packageName.nodeType` (split on `.`). Custom-extension nodes belong to the reserved `CUSTOM` package (`n8n-core` `CUSTOM_NODES_PACKAGE_NAME="CUSTOM"`). The working node type is therefore:

```text
CUSTOM.clipCraftTextExecute
```

The bare `clipCraftTextExecute` form fails with `Unrecognized node type: clipCraftTextExecute.undefined`. This is fixed in the canonical workflow and asserted by the integration tests.

## Live Deployment Steps

1. Live backend recreated and healthy:
   - `docker run -d --name clipcraft-backend --network clipcraft ... --env-file clipcraft\.env -e N8N_INTERNAL_SIGNING_SECRET=<48-char secret> python:3.11-slim sh -c "pip install -q . && uvicorn app.main:app --host 0.0.0.0 --port 8000"`
   - Health: `{"status":"ok"}`.
2. Live n8n recreated on the 5A image:
   - `clipcraft-n8n-debug:2.29.7-clipcraft-0.1.0`
   - `N8N_CUSTOM_EXTENSIONS=/opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft/dist` verified in container env.
3. Credential schema verified via `/api/v1/credentials/schema/clipCraftInternalApi`.
4. Live credential created:
   - Name: `ClipCraft Internal API`
   - Type: `clipCraftInternalApi`
   - Id: `byn0eWsH3GMCxFWH`
   - Base URL: `http://clipcraft-backend:8000`
   - Signing secret matches the backend env secret.
   - Encrypted at rest verified directly in `database.sqlite` (`U2FsdGVkX1+...` prefix).
5. Pre-import live WF17 backed up (10 nodes, legacy-only, `active=true`) to `backups/5b-live-wf17/17-ai-generate-text-live-backup.json`.
6. Import copy built with `CUSTOM.clipCraftTextExecute` and the live credential pinned.
7. CLI import succeeded via `n8n import:workflow` (the public REST API rejects read-only fields and custom node types). Import deactivates the workflow; reactivated with `n8n publish:workflow --id=17` (deprecated `update:workflow --active=true` also works). Verified `active=1`, 15 nodes, custom node present with pinned credential.

## Controlled Live Verification

Because WF17 starts with a `workflowTrigger` that emits static data on manual execution, a temporary harness workflow (id 19) was used to call WF17 through an Execute Workflow node exactly as WF01 does, with a controlled payload (jobId `11111111-1111-4111-8111-111111111111`, requestId `22222222-2222-4222-8222-222222222222`, prompt `Reply with exactly: CLIPCRAFT 5B CONTROLLED INTERNAL TEST`, provider `cloudflare`, credentialSource `environment`).

The harness was executed with `n8n execute --id=19 --rawOutput`, overriding the container's task broker port (`N8N_RUNNERS_BROKER_PORT=5681`) to avoid colliding with the running n8n server.

### Internal mode (`TEXT_EXECUTION_MODE=internal`)

Final normalized output:

```json
{
  "success": true,
  "type": "text",
  "result": "CLIPCRAFT 5B CONTROLLED INTERNAL TEST",
  "provider": "cloudflare",
  "model": "@cf/meta/llama-3.1-8b-instruct",
  "retryCount": 0,
  "timestamp": "2026-08-01T09:44:29.776Z"
}
```

Backend log confirmed the internal call reached Cloudflare and returned `200 OK`:

```text
POST /internal/ai/text/execute HTTP/1.1" 200 OK
```

### Legacy mode (`TEXT_EXECUTION_MODE=legacy`)

The same harness executed with the legacy env returned the identical success shape through `Call Provider API` -> `Adapt Legacy Result` -> `Evaluate Provider Result`:

```json
{
  "success": true,
  "type": "text",
  "result": "CLIPCRAFT 5B CONTROLLED INTERNAL TEST",
  "provider": "cloudflare",
  "model": "@cf/meta/llama-3.1-8b-instruct"
}
```

### Bug Found And Fixed During Verification

The controlled internal run initially returned `PROVIDER_HTTP_ERROR`. Root cause: `Prepare Internal Request` read `$input.first()`, but `Build Request` collapsed the source so `jobId`/`requestId`/`prompt` came back as `unknown-job`/`unknown-request`/empty, and the backend rejected the request (422). Fix: read the original payload from `$('Workflow Trigger').first()?.json`. Re-imported and re-verified; internal mode then returned `200 OK` with the exact expected text. This is exactly the class of defect static structure tests cannot catch.

### Harness Cleanup

The temporary harness workflow (id 19) was deleted from live n8n after verification. Its definition is retained in `backups/5b-live-wf17/5b-controlled-test-harness.json` for reuse.

## Test Results

```text
ClipCraft package (n8n-custom-nodes/n8n-nodes-clipcraft): 17 passed
ClipCraft workflow integration (tests/test_workflow_integration.py): 18 passed
```

The integration tests assert, among other things:

- The `TEXT_EXECUTION_MODE` / `internal` gate exists on `Text Execution Mode?`.
- The internal branch is `Prepare Internal Request` -> `ClipCraft Text Execute` -> `Adapt Internal Result`.
- The internal and legacy branches are disjoint (no dual provider execution).
- The custom node type is `CUSTOM.clipCraftTextExecute` and uses only the encrypted credential (no signing secret, no `CLOUDFLARE_AI_TOKEN`, no internal path, no `Authorization` in workflow data).
- Raw model ids are preserved through `={{ $json.modelId }}`.
- Both adapters converge into the shared evaluator shape.

## Current Live State

- Live n8n: healthy on `clipcraft-n8n-debug:2.29.7-clipcraft-0.1.0`.
- Live WF17: `active=1`, 15 nodes, `CUSTOM.clipCraftTextExecute` with credential `byn0eWsH3GMCxFWH`.
- Live credential: `byn0eWsH3GMCxFWH` (`ClipCraft Internal API`), encrypted at rest.
- Live backend: healthy, `{"status":"ok"}`, reachable at `http://clipcraft-backend:8000` on the `clipcraft` network.
- `TEXT_EXECUTION_MODE`: not set on the running n8n container (defaults to legacy). `.env` and compose default to `legacy`.
- Supabase `video_jobs`: no active jobs at verification time (safe for the controlled run).

## Security Notes

- The custom node never exposes the signing secret to Code nodes or workflow data.
- WF17 stores only the credential id and name; no base URL, signing secret, Cloudflare token, or signature appears in the workflow file.
- The backend enforces exact raw-body HMAC, constant-time comparison, a timestamp window, and nonce replay protection.
- The internal branch is exclusive to `TEXT_EXECUTION_MODE=internal`; it cannot run while the mode is legacy.

## Rollback

Restore the pre-import live version from the backup:

```text
backups/5b-live-wf17/17-ai-generate-text-live-backup.json
```

Import it with `n8n import:workflow`, reactivate (`n8n publish:workflow --id=17`), and restart n8n. The custom node remains discoverable (safe, inactive) and the live credential remains untouched. No backend, database, frontend, or provider configuration changes were required for 5B and none need rolling back.

## Residual Limitations

- Gemini remains excluded from the internal branch. The backend supports it, but the internal request contract is limited to Cloudflare for this checkpoint.
- Importing a workflow through the n8n CLI deactivates it; reactivation requires a separate `publish`/`update` step and, per n8n messaging, a restart for changes to fully take effect on a running instance.
- The harness-based controlled verification required a temporary workflow and an env override at execute time; it does not replace a real caller-triggered integration test through the live active pipeline.
- Mixed/public DNS rejection and DNS-deadline behavior in the custom node are implemented but were not exercised with a controlled DNS server.
- The live n8n container currently has no `TEXT_EXECUTION_MODE` set; cutover to internal requires setting it and restarting n8n, and should only be done after approving live-traffic cutover.

## Readiness

**Checkpoint 5B is complete: the custom node is integrated into WF17 as an exclusive internal branch, the default remains legacy, caller/downstream contracts are preserved, and both branches passed controlled live end-to-end verification against the live backend and live Cloudflare.**

Provider cutover (setting `TEXT_EXECUTION_MODE=internal` for real traffic) remains a separate, future decision and is not authorized by this checkpoint.
