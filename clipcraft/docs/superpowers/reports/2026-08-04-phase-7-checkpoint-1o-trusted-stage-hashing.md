# Phase 7 Validation Runner: Checkpoint 1O Trusted Stage Hashing

## Final Status

**HASHING_RECONCILED_PRODUCTION_BLOCKED_WF09**

The n8n Code-node sandbox blocker is reconciled in repository and live WF04-WF09.
All six live stage workflows contain the trusted core Crypto v2 node, and the
deterministic provider-free WF04 probe passed with the exact SHA-256 vector and
no provider or database call. WF09 was restored to its pre-cutover executable
behavior with only the approved trusted-hash path changes.

No production job was created. WF09 also still routes `Workflow Trigger`
directly to `Validate Input`, so its stage ledger, lease fence,
external-attempt reservation, heartbeat, and fenced finalization wrapper are
unreachable. Production generation remains stopped.

## Hash Purpose And Scope

The hash is used for stage idempotency and cache identity, not authentication
or lease fencing, and therefore requires deterministic canonical serialization
plus collision-resistant SHA-256, but no secret key.

Checkpoint 1O intentionally preserved the existing WF04-WF08 canonical bytes:

`JSON.stringify({jobId, pipelineRevision: input.pipelineRevision, stage, itemKey, revision: input.currentRevision ?? input.pipelineRevision})`

WF09 preserved its pre-cutover numeric `pipelineRevision` canonicalization and
legacy/default lease-input behavior while upgrading its prior unhashed canonical
string to SHA-256. This was a runtime-compatibility repair, not the broader effective-input hash
redesign from the idempotency plan. Provider, model, prompt/template, adapter,
and artifact inputs were not added because the active ledger does not currently
enforce immutable input-hash mismatch semantics.

## Root Cause

WF04-WF08 calculated `inputHash` inside `Normalize Stage Context` with:

`require('crypto').createHash('sha256')`

The deployed n8n Code-node sandbox rejects that module with:

`Module 'crypto' is disallowed`

The deployed runtime is n8n `2.29.7` with `n8n-nodes-base@2.29.6`. Its trusted
core `n8n-nodes-base.crypto` v2 node supports string hashing with `SHA256` and
hex output, requires no credentials, preserves input JSON, preserves binary
data, and emits paired items.

## Minimal Fix

The executable top-level path in WF04-WF09 is now:

`Normalize Stage Context -> Hash Stage Input -> Begin Stage`

The WF04-WF08 normalizers:

- Keeps the existing lease validation, stage name, item key, raw revision
  semantics, and canonical property order.
- Emits the canonical string as temporary `stageHashInput`.
- No longer imports `crypto` or calculates `inputHash` in Code.

Pre-cutover live WF09 differed: it accepted legacy snake_case/default lease
context, normalized `pipelineRevision` to a number before canonicalization, and
stored the canonical JSON string directly as `inputHash` without SHA-256. The
repository and live WF09 preserve those input and canonicalization semantics
while emitting `stageHashInput` for Crypto v2.

Each `Hash Stage Input` node:

- Uses `n8n-nodes-base.crypto`, type version `2`.
- Uses action `hash`, type `SHA256`, encoding `hex`.
- Reads `={{ $json.stageHashInput }}`.
- Writes `inputHash`.
- Has no credentials and no continue-on-failure behavior.

Each `Merge Stage Context` now reads the Crypto output, preserves `inputHash`,
and removes temporary `stageHashInput` before downstream processing.

## Deterministic Probe

Probe script:

`clipcraft/scripts/controlled_wf04_run_token_no_provider_probe.js`

Final result:

- HTTP status: `200`
- Run token present: `true`
- Run token matches canonical UUID: `true`
- Input hash: `d10d537471f2b7711d4b537e073982adb05d8e0c7be176995d1b729b549d42f0`
- Input hash matches fixed vector: `true`
- Temporary `stageHashInput` absent downstream: `true`
- Provider calls: `0`

The probe compares the live WF04 Normalize/Hash/Merge nodes to the reviewed
local definitions, pins every temporary Code node by SHA-256, permits only
Webhook, Code, and Crypto node types, rejects credentials, uses bounded
network/Docker timeouts, and verifies temporary-workflow deletion. Final probe
workflow `ZNLCFfZd3ajAspZ9` returned HTTP `404` after cleanup.

No Supabase RPC, provider, TTS, renderer, filesystem artifact, or production job
was invoked by the probe.

## Live Workflows

All workflows remained active and preserved their IDs:

| Workflow | ID | Nodes | Live version |
| --- | --- | ---: | --- |
| WF04 Generate Script and Scenes | `dWTF2UGXX3R73PDW` | 33 | `81d0a327-1fa7-4778-91d2-f2c8274368dd` |
| WF05 Generate Scene Images | `gazJuTcoSGqYdGze` | 25 | `d4ec0ac3-f36b-488b-9470-1177e8ded440` |
| WF06 Generate Narration | `UhWkv3GLHVSpWrMe` | 21 | `aab51253-d639-4c35-9cf6-56669e2ff948` |
| WF07 Build Captions | `dNgYGCqkbwr552EW` | 19 | `41e166ac-2c1c-447f-afdf-6d504f91ddab` |
| WF08 Build Render Manifest | `iik8qVHvgD9xWWjI` | 20 | `cdcaa04f-ea2b-4333-b5d2-c9de72c92d06` |
| WF09 Render AI Video | `gqX0rJ1gqzHCNDso` | 21 | `c2b5d3d7-5cdf-4ab4-abb4-f4ad159bd43a` |

The final live audit confirmed all six use Crypto v2 and contain
`Normalize Stage Context -> Hash Stage Input -> Begin Stage`. Mechanical tests
also confirm WF09 differs from its pre-cutover backup only in Normalize, Merge,
the new Hash node, and the two associated connections.

## Deployment Safety

WF04 backup:

`clipcraft/backups/phase-7-cutover/wf04-run-token-reconciliation-20260804T125204Z.json`

WF05-WF09 coherent backup set:

- `clipcraft/backups/phase-7-cutover/wf05-stage-hashing-20260804T132837Z.json`
- `clipcraft/backups/phase-7-cutover/wf06-stage-hashing-20260804T132837Z.json`
- `clipcraft/backups/phase-7-cutover/wf07-stage-hashing-20260804T132837Z.json`
- `clipcraft/backups/phase-7-cutover/wf08-stage-hashing-20260804T132837Z.json`
- `clipcraft/backups/phase-7-cutover/wf09-stage-hashing-20260804T132837Z.json`

A second coherent backup set at timestamp `20260804T193046Z` captured the
post-bulk-import state before the targeted WF09 restore.

The multi-workflow importer preflights exact live/backup equality, validates the
trusted hash graph, projects only public-API-writable node/settings fields,
preserves full live settings and static data, verifies each update, and performs
bounded reverse rollback for failed or ambiguous updates.

Two initial WF05 PUT attempts returned HTTP `400` before mutation. Controlled
diagnostics proved two public API schema constraints:

- Response-only settings `binaryMode` and `availableInMCP` cannot be sent to
  `workflowSettings`, which has `additionalProperties: false`.
- Export-only node property `outputs` cannot be sent to the public node schema.

The importer was corrected with explicit writable-field projections. A
temporary inactive diagnostic workflow then accepted the projected 25-node WF05
definition with Crypto v2, and the final five-workflow import succeeded. Before
each attempt, all five live workflows matched their backups; failed attempts
reported no rollback errors and changed no workflow.

Final review then compared WF09 against its pre-cutover backup and found that
the successful bulk import included existing repository differences outside
stage hashing, including status projection/update, manifest retrieval, renderer
request, asset persistence, and completion handling. No production execution
used those changes. The approved resolution restored the pre-cutover WF09 and
applied only the trusted Hash node, compatibility-preserving Normalize/Merge
changes, and Normalize-to-Hash-to-Begin wiring. The final import verified and
skipped WF05-WF08 as no-ops and updated only WF09.

## Tests

Fresh verification after all live imports:

- Full ClipCraft Python/workflow suite: `145 passed`
- Custom n8n node suite: `29 passed`
- Provider-free live WF04 probe: passed
- Deployment/probe script syntax checks: passed
- Active jobs: `0`
- Active leases: `0`
- Running n8n executions: `0`
- Temporary probe workflow cleanup: HTTP `404`

Backend suite remains the known unrelated result:

- `261 passed, 1 failed`
- Failure: missing
  `clipcraft/supabase/migrations/009_video_job_configuration_snapshots.sql`

## Repository Changes

- `clipcraft/workflows/04-generate-script-and-scenes.json`
- `clipcraft/workflows/05-generate-scene-images.json`
- `clipcraft/workflows/06-generate-narration.json`
- `clipcraft/workflows/07-build-captions.json`
- `clipcraft/workflows/08-build-render-manifest.json`
- `clipcraft/workflows/09-render-video.json`
- `clipcraft/tests/test_workflow_integration.py`
- `clipcraft/scripts/controlled_wf04_run_token_no_provider_probe.js`
- `clipcraft/scripts/backup_stage_hashing_1o.js`
- `clipcraft/scripts/import_stage_hashing_1o.js`
- `clipcraft/scripts/reconcile_wf09_minimal_1o.js`
- `clipcraft/docs/superpowers/reports/2026-08-04-phase-7-checkpoint-1o-trusted-stage-hashing.md`

No migration, credential, provider mode, custom node, renderer contract, or
container configuration changed.

## WF09 Scope Reconciliation

The temporary broader WF09 cutover was reconciled before any production
execution. Repository and live WF09 now preserve the pre-cutover executable
contract except for the approved trusted-hash changes. This scope issue is
closed.

## New Production Blocker

Live WF09 currently has:

`Workflow Trigger -> Validate Input`

Its stage wrapper exists but is unreachable from the trigger:

`Normalize Stage Context -> Hash Stage Input -> Begin Stage -> Merge Stage Context -> Stage Started?`

Starting a production generation would therefore permit the render path to
bypass the stage ledger and fencing contract. Checkpoint 1P was not started and
no production job was created.

## Additional Ledger Contract Drift

The active `begin_job_stage` implementation also differs from the approved
idempotency plan:

- It stores `input_hash` but does not compare a new hash with the stored hash.
- It never raises `INPUT_HASH_MISMATCH`.
- An existing running row receives a new run token instead of returning
  `RUNNING` with the existing owner.
- A succeeded row returns cached output based only on stage identity.
- WF04 requires a UUID run token after begin, while the cached-success response
  does not provide one.

Because Checkpoint 1O prohibited migrations, this drift was documented rather
than changed. A future effective-input hash redesign must restore the ledger
contract first through a separately reviewed additive migration and SQL tests.

## Production Readiness

- Trusted sandbox-compatible stage hashing: complete for WF04-WF09.
- Controlled production generation: not started.
- First new hard blocker: WF09 trigger bypasses stage fencing.
- Additional blocker: active stage-ledger hash/running/cache semantics drift.
- Pexels integration: must not begin.

Stop after Checkpoint 1O. Do not create a production job until WF09 reachability
and the applicable stage-ledger contract are reconciled and reverified.
