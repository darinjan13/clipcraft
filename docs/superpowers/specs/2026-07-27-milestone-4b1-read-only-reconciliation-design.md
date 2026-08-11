# Milestone 4B.1 Read-Only Reconciliation Design

## Scope

Implement a self-contained offline validator and read-only n8n reconciliation generator. The authoritative decisions remain the three Milestone 4A.1 artifacts and the user-approved PRESERVE GATES resolution.

## Components

- `milestone4b1_validate.py` parses and structurally validates exactly five Milestone 4B.1 JSON artifacts without network access.
- `milestone4b1_reconcile.py` reads canonical repository JSON and the authoritative 4A.1 artifacts, performs only documented n8n public API GET requests with `X-N8N-API-KEY`, takes preflight and postflight snapshots, and writes exactly the requested five artifacts.

## Safety

The generator has no mutation, execution, webhook, provider, Supabase, TTS, renderer, or production-job code paths. Publications, activations, repairs, archival, and WF16 identity selection are never attempted. Contradictory approved Execute Workflow references produce a stop condition in the report rather than a repair.

## Evidence

The output records fresh snapshot timestamps and digests, canonical parity recomputed from the same fresh snapshot, all stored Execute Workflow references and cycles, duplicate/orphan candidates, pre/post state and definition equality, an operation audit, blocked publication evidence, preserved WF16 state, and the preserved Milestone 4B `DO_NOT_BEGIN` gate.

## Test Flow

Create the offline validator first and run it to demonstrate failure because the five artifacts do not exist. Then implement and compile the generator, run it once, compile the validator, and run the validator. No root test script or existing potentially mutating script is executed.
