# WF17/WF18 Canonical Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make repository WF17/WF18 workflows and their verified callers use the approved validation, provider, retry, and normalized-response contracts.

**Architecture:** Keep provider request construction in Build Request, route validation through an IF node, and centralize all provider/error/final responses in Normalize Response. Retry state is carried explicitly in the workflow item and limited to two retries. WF18 caller context is normalized into an optional context object and consumed by WF05.

**Runtime compatibility:** n8n requires `Workflow Trigger.parameters.events` to
be `["update"]`; both canonical workflow files must retain this field so the
public API accepts the definitions.

**Retry repair:** retry state is carried as item-level `retryCount`; provider
results are evaluated before an explicit `Retryable Failure?` branch, and
`Increment Retry` loops back through `Prepare Provider Attempt`. No node-run
history or future-node expression may determine retry state.

**Tech Stack:** n8n workflow JSON, JavaScript Code/IF/HTTP Request nodes, Python functional-test source, Markdown documentation, Python/JSON static validation.

---

### Task 1: Replace WF17 Workflow Contract

**Files:**
- Modify: `clipcraft/workflows/17-ai-generate-text.json`

- [x] Replace Build Request code with canonical normalization and exact provider keys.
- [x] Add `Validate Input` IF node.
- [x] Add `Handle Validation Error` Code node.
- [x] Add explicit retry-state node/flow with maximum retry count `2`.
- [x] Make Normalize Response emit success, provider failure, and retry-exhausted schemas with UTC timestamp and error source.
- [x] Preserve `_testCorrelationId` only when present in Workflow Trigger input.
- [x] Verify no provider body/header contains correlation or context data.

### Task 2: Replace WF18 Workflow Contract

**Files:**
- Modify: `clipcraft/workflows/18-ai-generate-image.json`

- [x] Replace Build Request code with canonical normalization and exact image body.
- [x] Add the same validation/error topology as WF17.
- [x] Normalize verified caller fields into optional `context.jobId`, `context.sceneId`, and `context.sceneIndex`.
- [x] Add bounded retry state and normalized image/error outputs.
- [x] Preserve marker only when present and exclude it from provider request data.

### Task 3: Migrate Active Callers

**Files:**
- Modify: `clipcraft/workflows/01-chat-message.json`
- Modify: `clipcraft/workflows/03-video-job-worker.json`
- Modify: `clipcraft/workflows/04-generate-script-and-scenes.json`
- Modify: `clipcraft/workflows/05-generate-scene-images.json`
- Modify: `clipcraft/workflows/12-regenerate-scene.json`

- [x] WF01 consume canonical text `result` and handle structured failures before parsing.
- [x] WF03 extract structured error message/code/type without raw payloads.
- [x] WF04 consume canonical text `result`, stop persistence on failure, and return safe wrapper failure.
- [x] WF05 consume canonical `imageBase64` and `context` fields, stopping persistence on failure.
- [x] WF12 consume canonical `imageBase64` and stop persistence on failure.
- [x] Remove deprecated `result.response`, `result.image`, `result.base64`, and top-level context aliases from canonical paths.

### Task 4: Expand Functional Test Definitions

**Files:**
- Modify: `functional_tests.py`

- [x] Add canonical normalized-response assertions.
- [x] Add validation, provider failure, and retry-exhaustion assertions using static execution-data fixtures/helpers only.
- [x] Assert UTC timestamp format and error source.
- [x] Assert marker preservation and provider-request isolation.
- [x] Assert WF18 context behavior.
- [x] Assert bounded retry topology and retry-state propagation through static workflow inspection.
- [x] Keep runtime invocation disabled during this milestone.

### Task 5: Update Contracts and State Documentation

**Files:**
- Modify: `clipcraft/shared-contract.md`
- Modify: `docs/CURRENT_STATE.md`
- Modify: `docs/WORKFLOW_CATALOG.md`
- Modify: `docs/TESTING_STRATEGY.md`
- Modify: `docs/AI_HANDOFF.md`
- Create or modify: `docs/IMPLEMENTATION_LOG.md`

- [x] Mark the old WF17/WF18 response shapes historical.
- [x] Document canonical schemas, context rules, error sources, timestamps, and retry bounds.
- [x] Record implementation changes and static validation evidence.

### Task 6: Static Validation

**Files:**
- Validate all modified JSON, Python, and documentation files.

- [x] Parse every modified workflow JSON file.
- [x] Verify required node names and connection branches.
- [x] Verify invalid input cannot connect to the provider node.
- [x] Verify retry paths are bounded and state increments are explicit.
- [x] Search canonical callers for deprecated aliases.
- [x] Compile modified Python files with `py -3 -m py_compile`.
- [x] Scan modified files for secret patterns.
- [x] Confirm no n8n, Supabase, Cloudflare, webhook, SQLite, or `/rest` operation occurred.
