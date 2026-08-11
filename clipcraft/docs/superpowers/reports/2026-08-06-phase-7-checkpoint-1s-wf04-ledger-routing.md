# Checkpoint 1S: Reconcile WF04 `Generate Script and Scenes` to the new `begin_job_stage` ledger states

- **Date:** 2026-08-06
- **Project:** clipcraft-ai (live: `dpcytfpqhxpqufcsivkh`)
- **Scope gate:** Checkpoint 1R approval → WF04 route reconciliation (provider-free probe only).
- **Status:** Live applied, repo↔live parity verified, route bug found and fixed, provider-free ledger probe passed all 8 states. No provider-backed/production generation run this deployment.

## Objective
Update live WF04 (`dWTF2UGXX3R73PDW`, `Generate Script and Scenes`) so it consumes the 1R `begin_job_stage` ledger states and routes each one deterministically through the stage wrapper, without fallthrough, preserving `cachedOutput` and the trusted run-token contract.

## Constraint set (1S)
- Modify **only WF04** nodes (Normalize/Hash/Merge stage context + stage-lane routing).
- No fallthrough — every state must reach exactly one terminal.
- `cachedOutput` preserved on the cached path.
- `runToken` consumed only for `STARTED`.
- Safe stop for non-executable states (`CACHED_SUCCESS` → return cached, `RUNNING` → return already-running, failure lanes → stage failure).
- Do NOT modify WF02/03/05–18, providers, renderer, TTS, migrations, frontend, custom nodes.

## Real bug discovered and fixed
The three WF04 stage-lane routing IF nodes (`Stage Started?`, `Route Cached?`, `Route Running?`) used `operator.operation: "equal"`. n8n's V2 If node boolean filter switch (`n8n-workflow/dist/esm/node-parameters/filter-parameter.js`, `case 'boolean'`) only supports `equals`, `notEquals`, `true`, `false`, `empty`, `notEmpty`. The unrecognized `equal` matched **no** case → the condition always evaluated false → every state (including `STARTED`) fell through to `Return Stage Failure`. There was effectively no working start/provider route.

Confirmed three ways:
1. Read the container source: `filter-parameter.js` boolean case list.
2. Isolated IF round-trips on live n8n: `equals` routes TRUE branch; `equal` routes FALSE branch deterministically.
3. Live probe before fix: `STARTED` returned failure terminal, `Stop Provider` unreachable.

Fix: `patch_ops.py` rewrote `operator.operation` `"equal"` → `"equals"` in both the top-level nodes and the `activeVersion.nodes` of `clipcraft/workflows/04-generate-script-and-scenes.json` (3 routing IF nodes × 2 copies).

Note: the same latent `"equal"` exists on live queue-worker IF nodes (`Job Claimed?`, `Images OK?`, `Render OK?`). Those are out of 1S scope and were NOT modified; they are pre-existing and are logged as a follow-up.

## Applied
- Repo file `clipcraft/workflows/04-generate-script-and-scenes.json` updated with the `equals` fix (top-level and activeVersion).
- Redeployed to live via `PUT /api/v1/workflows/dWTF2UGXX3R73PDW`.
- Live verified: `active=true`, `versionCounter=58`, `versionId=d583be4e-72c7-4123-b097-6b86539b9fe1`, 37 nodes.
- Repo↔live parity check: 37/37 node names equal, connections equal, all stage-lane node payloads (`Normalize Stage Context`, `Hash Stage Input`, `Merge Stage Context`, `Stage Started?`, `Route Cached?`, `Route Running?`, `Return Cached Stage`, `Return Already Running`, `Return Stage Failure`) byte-identical.

## Provider-free WF04 ledger probe (live)
New probe `clipcraft/scripts/controlled_wf04_ledger_state_no_provider_probe.js` runs all 8 states against a live WF04-shaped temporary workflow, validates the safe node set by SHA-256 code pins, then deletes the temp workflow. No providers, no renderer, no TTS, no production video.

SHA-256 code pins (real, computed from the repo nodes):
- `Begin Stage Fixture` = `43d53780e6c4f253f341feb616a1db81faadfadc25a276d84c11cabf331bc2a8`
- `Stop Provider` = `711b1c62e0611d9fd492e493c106cb066e1e217a8c5b5a14a71580bcffaa43e2`
- `Unwrap Probe Input` = `bc9619e56df0ba8eb86dd237401f80f02c353dd6cdcc7cd474ce1b44d74c8272`
- `Normalize Stage Context` = unchanged from prior checkpoint
- `Merge Stage Context` = `133a2fff…` (unchanged, matches 1R probe)

| State | Result |
|---|---|
| STARTED | PASS — routed to Stop Provider, `stoppedAtProvider` true |
| CACHED_SUCCESS | PASS — cached path, output preserved |
| RUNNING | PASS — already-running safe stop |
| FAILED | PASS — failure_previous lane |
| INPUT_HASH_MISMATCH | PASS — failure_mismatch lane |
| INVALID_ITEM_KEY | PASS — failure_invalid_key lane |
| UNKNOWN_OUTCOME | PASS — failure_unknown lane |
| NOT_A_STATE | PASS — fail-closed (HTTP 500, n8n `{"message":"Error in workflow"}`) |

Fail-closed assertion is a **non-2xx status** (n8n does not echo the JS error text from the last node); if the `WF04_LEDGER_STATE_UNSUPPORTED` string is present it is also checked.

## Tests
- `tests/test_workflow_integration.py::test_wf04_ledger_state_probe_pins_desired_route_chain` — probe exists, pins cover the code-node set, all 8 terminal states + fail-closed asserted. Passed.
- `tests/test_workflow_integration.py::test_wf04_ledger_route_if_nodes_use_equals_boolean_operator` (new regression guard) — the 3 routing IF nodes use `equals`; no new-style boolean IF uses `equal`. Passed.
- Full local regression (excluding env/network-dependent suites): **148 passed**.
- 1R probe rerun post-deploy: PASS (`runTokenMatches=true`, `inputHashMatches=true`, `stageHashInputAbsent=true`, `providerCalls=0`).

## Safety state
- Live DB: 0 non-terminal jobs, 0 leased rows, 0 `job_stage_runs`.
- Temp workflows used by probes and the IF round-trip experiments were deleted (verified: no `Phase 7*` / `IF*` workflows remain).
- No provider-backed or production generation was started.

## Backups
- `backups/precheckpoint-1s_repo-wf04_20260806.json` (pre-fix repo snapshot).
- `backups/post-checkpoint-1s_wf04_20260806.json` (post-fix live snapshot, version 58).

## Rollback path
If the `equals` fix is ever proven incorrect, restore `backups/precheckpoint-1s_repo-wf04_20260806.json` (pre-fix) — but note the pre-fix routing is the broken `equal` state, so rollback would re-introduce the fallthrough bug. Rollback status: NO.

## Next checkpoint
Proceed to Phase G/H (provider-free end-to-end video generation) or continue with the pre-existing queue-worker `"equal"` IF follow-up. No provider-backed generation was started in this checkpoint.
