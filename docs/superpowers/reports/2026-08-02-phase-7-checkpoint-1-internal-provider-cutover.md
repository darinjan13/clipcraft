# Phase 7 Checkpoint 1: Internal Provider Cutover

## Final Status

**CUTOVER_BLOCKED_RUNTIME**

Internal text and image defaults were applied and both provider-boundary pre-flight probes passed. The single authorized full-video job failed during the initial text stage before image generation, was safely cancelled, and was not rerun. Internal defaults remain configured; no automatic legacy fallback was performed.

## Read-Only Reviews

Six read-only reviews were completed before mutation:

- Deployment readiness and container state.
- Workflow/caller compatibility.
- Rollback feasibility.
- Provider cost and duplicate-call risk.
- Security posture.
- Final test and output verification coverage.

The reviews identified existing residual risks, including unauthenticated public backend endpoints, exposed n8n HTTP/editor configuration, retained legacy credentials, execution-data retention, and renderer deployment drift. No security redesign was authorized in this checkpoint.

## Backup

Backup location:

```text
clipcraft/backups/phase-7-cutover/20260801T184627Z/
```

Verified contents:

- 31 non-empty backup files.
- SQLite backup: 433,889,280 bytes.
- SQLite `PRAGMA integrity_check`: `ok`.
- WF17, WF05, WF18, queue worker, and direct caller workflow exports.
- Credential metadata without secret values.
- Compose configuration, protected environment configuration, Docker files, and custom-node package.
- No secrets were printed in command output or this report.

## Configuration Cutover

Before:

- `TEXT_EXECUTION_MODE=legacy`.
- `IMAGE_EXECUTION_MODE=legacy`.

After:

- `TEXT_EXECUTION_MODE=internal`.
- `IMAGE_EXECUTION_MODE=internal`.

Authoritative path:

```text
clipcraft/.env -> Docker Compose interpolation -> n8n container environment -> workflow $env mode gates
```

Changed files:

- `clipcraft/.env`.
- `clipcraft/.env.example`.
- `clipcraft/workflows/17-ai-generate-text.json`.
- `clipcraft/tests/test_workflow_integration.py`.

The n8n container was recreated without changing its named volume, SQLite database, workflows, credentials, executions, encryption key, or custom-node package.

Final runtime checks:

- n8n health: HTTP 200.
- Backend `/api/health`: HTTP 200.
- Renderer `/health`: `{"status":"ok"}`.
- TTS `/health`: healthy.
- Workflow count: 15.
- Credential count: 1.
- WF17: ID `17`, active, 15 nodes, custom text node present.
- WF05: ID `gazJuTcoSGqYdGze`, active, 27 nodes.
- WF18: ID `18`, active, 18 nodes, custom image node present.

## Pre-Flight

Text pre-flight:

- Probe execution: `25872`.
- Mode: internal.
- `ClipCraft Text Execute`: executed once.
- Legacy `Call Provider API`: not executed.
- Result: normalized successful text output.

Image pre-flight:

- Probe execution: `25876`.
- Mode: internal.
- `ClipCraft Image Execute`: executed once.
- Legacy `Call Provider API`: not executed.
- BinaryData and imageBase64 output: verified.
- Request ID and scene context: preserved.

No credentials, signing secrets, prompts, or image data were printed by the probe scripts.

## Full Video Attempt

Exactly one test job was created:

```text
Job ID: 9edd0fa5-df56-42cb-96a6-4265e37db34d
```

Creation returned HTTP 202 with status `queued`. No second job was created.

Relevant executions:

- Queue worker: `26023`.
- Generate Script and Scenes: `26024`.
- WF17 AI Generate Text: `26025`.

Failure:

- WF17 received no caller `requestId` from the script-stage caller.
- The existing internal preparation code defaulted to `unknown-request`.
- FastAPI correctly rejected the non-UUID request ID.
- `ClipCraft Text Execute` returned safe `AI_EXECUTION_FAILED`.
- The script stage failed before image generation, TTS, captions, manifest, or renderer execution.
- The job was cancelled through the existing cancel endpoint and verified as `cancelled`.

No automatic fallback to legacy was performed.

## Corrective Fix

The smallest compatible fix was applied to WF17:

- `Prepare Provider Attempt` now creates a UUID with `globalThis.crypto.randomUUID()` when the caller omits one.
- Retry attempts receive a fresh UUID.
- `Prepare Internal Request` consumes the attempt-level request ID instead of defaulting to `unknown-request`.
- No prompts, validation rules, provider selection, public payloads, or downstream workflows were changed.
- The live WF17 definition was updated through API v1 while preserving ID `17`, active state, and node count.

Regression test added and verified red/green:

- `test_wf17_internal_attempts_have_valid_request_ids_without_caller_changes`.

## Tests

- Workflow contract suite: **79 passed**.
- Backend suite: **262 passed**.
- Custom-node suite: **28 passed**.
- Frontend production build: passed.
- Docker Compose validation: passed.
- Pre-flight text and image probes: passed.
- Full video: **blocked before completion**.
- FFprobe/output verification: not run because no MP4 was produced.
- Rollback drill: not run because the full-video success prerequisite failed; internal modes remain configured as required by the stop condition.

## Remaining Blockers

1. Re-run of the same cancelled job requires explicit approval after the WF17 request-ID fix; no second job was created automatically.
2. Full end-to-end verification remains pending: images, narration, captions, manifest, renderer, thumbnail, result/download APIs, and final status.
3. Existing security findings remain outside this checkpoint: unauthenticated backend APIs, direct n8n HTTP exposure, public privileged webhooks, service-role workflow access, retained legacy credentials, and execution-data retention.
4. Existing renderer deployment drift and repeated n8n insights metadata errors remain documented and were not changed.

## Final State

- `TEXT_EXECUTION_MODE=internal`.
- `IMAGE_EXECUTION_MODE=internal`.
- Legacy workflow branches remain intact.
- Legacy credentials remain present for emergency rollback.
- No Pexels, NVIDIA, Gemini image, renderer redesign, database migration, frontend redesign, TTS replacement, caption redesign, or cleanup work was started.

Stop here pending approval to rerun the cancelled test job after the request-ID fix.

## Checkpoint 1A

Phase 7 Checkpoint 1A completed its read-only lease-contract audits and prepared an additive reconciliation migration. Final status: **READY_FOR_MIGRATION_APPLICATION**. Live application was not performed because the database-capable execution path was unavailable. See `docs/superpowers/reports/2026-08-02-phase-7-checkpoint-1a-lease-contract-reconciliation.md`.
