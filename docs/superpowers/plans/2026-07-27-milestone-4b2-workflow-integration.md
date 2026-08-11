# Milestone 4B.2 Workflow Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate the repository n8n workflows with the complete lease, stage-ledger, retry, idempotency, and regeneration contracts.

**Architecture:** Use repository JSON transformation helpers to preserve existing stage business logic while replacing public stage webhooks with internal workflow triggers, adding fenced RPC boundaries, and converting WF03 orchestration to Execute Workflow calls. Keep WF16 unchanged and prohibit runtime operations.

**Tech Stack:** Python, JSON n8n workflow definitions, Supabase PostgREST RPC contracts, pytest.

---

### Task 1: Add failing integration contract tests

**Files:**
- Create: `clipcraft/tests/test_workflow_integration.py`
- Test: `clipcraft/tests/test_workflow_integration.py`

- [ ] Assert WF03 claims with lease duration and calls internal stage workflows.
- [ ] Assert WF04-WF09/WF14 use internal triggers and fenced RPC nodes.
- [ ] Assert WF12/WF13 call only `enqueue_regeneration` for mutation.
- [ ] Assert no edited stage workflow contains public webhook or Respond to Webhook nodes.
- [ ] Run `pytest clipcraft/tests/test_workflow_integration.py -q` and observe expected failures.

### Task 2: Implement repository workflow integration

**Files:**
- Create: `milestone4b2_integrate.py`
- Modify: `clipcraft/workflows/03-video-job-worker.json`
- Modify: `clipcraft/workflows/04-generate-script-and-scenes.json`
- Modify: `clipcraft/workflows/05-generate-scene-images.json`
- Modify: `clipcraft/workflows/06-generate-narration.json`
- Modify: `clipcraft/workflows/07-build-captions.json`
- Modify: `clipcraft/workflows/08-build-render-manifest.json`
- Modify: `clipcraft/workflows/09-render-video.json`
- Modify: `clipcraft/workflows/12-regenerate-scene.json`
- Modify: `clipcraft/workflows/13-regenerate-video.json`
- Modify: `clipcraft/workflows/14-error-handler.json`

- [ ] Add normalized context and internal Execute Workflow boundaries.
- [ ] Add begin, external-attempt reservation, heartbeat, finalize, and failure RPC nodes.
- [ ] Replace direct regeneration mutation with idempotent enqueue RPCs.
- [ ] Never touch `clipcraft/workflows/16-resolve-asset-paths.json`.

### Task 3: Verify and produce evidence

**Files:**
- Create: `milestone4b2_validate.py`
- Create: `artifacts/milestone-4b2-*.json`

- [ ] Run workflow JSON parsing and integration tests.
- [ ] Run the existing full test suite.
- [ ] Generate repository-only evidence with publication and execution gates false.
