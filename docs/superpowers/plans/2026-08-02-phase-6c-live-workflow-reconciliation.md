# Phase 6C Live Workflow Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile WF05 and WF18 from the original live backup, current live API state, and repository definitions, then perform a controlled API import and legacy/internal/rollback verification without changing the default execution mode.

**Architecture:** Use the original live exports as the baseline for intentional operational behavior, the current API exports as the authoritative current-state check, and repository workflows as the source for approved 6B/6C architecture. Preserve live IDs, credential IDs, active state, and environment-specific metadata while merging only explicitly classified functional differences. Use the validated n8n `/api/v1/*` API and disposable backups; never mutate unrelated workflows.

**Tech Stack:** n8n 2.29.7, authenticated n8n API v1, JSON workflow exports, PowerShell/Docker health checks, Python pytest suites, Vite build.

---

### Task 1: Capture and compare all reconciliation inputs

**Files:**
- Read: `clipcraft/workflows/05-generate-scene-images.json`
- Read: `clipcraft/workflows/18-ai-generate-image.json`
- Read: `clipcraft/backups/n8n-recovery/20260801-231151Z/workflow-exports/live-current/WF05-live.json`
- Read: `clipcraft/backups/n8n-recovery/20260801-231151Z/workflow-exports/live-current/WF18-live.json`
- Read via API: `/api/v1/workflows/gazJuTcoSGqYdGze` and `/api/v1/workflows/18`

- [x] Confirm backup and current API definitions match before any import.
- [x] Record node IDs, counts, connections, expressions, credentials, settings, IDs, version metadata, and active states.
- [x] Stop if the current live definitions differ from the original backup in an unexplained way.

### Task 2: Build classified merged definitions

**Files:**
- Create: `clipcraft/backups/n8n-recovery/20260801-231151Z/workflow-exports/reconciled/WF05-reconciled.json`
- Create: `clipcraft/backups/n8n-recovery/20260801-231151Z/workflow-exports/reconciled/WF18-reconciled.json`
- Modify: `docs/superpowers/reports/2026-08-02-phase-5-5-deployment-recovery.md`
- Modify: `docs/superpowers/reports/2026-08-02-phase-5-checkpoint-6b-wf18-custom-image-integration.md`

- [x] For WF05, preserve live targeted-scene filtering, no-pending guard, JPEG/BinaryData behavior only if it does not conflict with the approved repository renderer contract; restore repository stage orchestration and request-ID generation.
- [x] For WF18, use the repository 18-node mode-gated custom-node architecture, preserving live ID `18`, active state `true`, execution order, and live runtime metadata.
- [x] Preserve WF18 credential reference to the existing `ClipCraft Internal API` credential ID.
- [x] Record every difference as repository improvement, intentional live modification, obsolete implementation, or conflict requiring merge.
- [x] Validate JSON syntax, node IDs, graph connections, expressions, credential references, environment references, and no unrelated workflow content.

### Task 3: Import and verify only WF05 and WF18

**Files:**
- Read: reconciled workflow JSON files
- Modify via API only: live WF05 and WF18

- [x] Export a fresh rollback copy of current live WF05/WF18 immediately before import.
- [x] Update WF05 and WF18 through API v1 while preserving IDs and live active states.
- [x] Verify node counts, IDs, graph connections, custom node type, credential ID/name, active states, and workflow list count.
- [x] Stop immediately on ID, credential, caller-contract, renderer-contract, BinaryData-contract, or unexpected-drift changes.

### Task 4: Controlled legacy, internal, and rollback verification

**Files:**
- Read/modify only approved runtime configuration and workflow execution inputs
- Modify via API: WF18 mode/configuration as required for controlled execution

- [x] Keep `IMAGE_EXECUTION_MODE=legacy` and run the controlled legacy image execution.
- [x] Verify one provider call, expected BinaryData/imageBase64, renderer-facing contract, scene ordering, filename, and MIME.
- [x] Temporarily use `IMAGE_EXECUTION_MODE=internal` and run the controlled internal execution.
- [x] Verify custom node, HMAC/backend/Cloudflare path, BinaryData adapter, renderer compatibility, request ID, no duplicate provider call, and no secrets.
- [x] Restore `IMAGE_EXECUTION_MODE=legacy` and verify rollback immediately.
- [x] Stop on duplicate provider calls, missing BinaryData, contract drift, unexpected secrets, or any failed assertion.

### Task 5: Run final verification and publish status

**Files:**
- Modify: `docs/superpowers/reports/2026-08-02-phase-5-5-deployment-recovery.md`
- Modify: `docs/superpowers/reports/2026-08-02-phase-5-checkpoint-6b-wf18-custom-image-integration.md`

- [x] Run workflow validation, workflow contract tests, backend suite, frontend build, secret scan, security review, and compatibility review.
- [x] Record reconciliation decisions, imported workflows, legacy/internal/rollback evidence, remaining drift, and default mode.
- [x] Set final status to `LIVE_RECONCILIATION_COMPLETE` only if every required verification passes and internal mode is not enabled by default.
