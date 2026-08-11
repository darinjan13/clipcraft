# Milestone 4B.2 Workflow Integration Design

## Goal

Make the repository n8n workflow definitions represent the complete fenced pipeline architecture without publishing, activating, or executing runtime jobs.

## Architecture

WF03 claims a job and carries a normalized orchestration context containing the job id, worker id, lease token, attempt number, and pipeline revision. Each stage workflow is an internal Execute Workflow target, begins a durable stage run, reserves the correct external-attempt counter before side effects, and finalizes success or failure through the foundation RPCs. Stage workflows return the context and ledger result to WF03.

Regeneration workflows are public request adapters only: they validate a client request and call `enqueue_regeneration`; they do not mutate job state directly or invoke providers. WF14 owns stage failure classification and calls `fail_job_stage`. WF16 is unchanged.

## Contracts

- `claim_next_video_job` is the only queue acquisition path.
- `heartbeat_video_job`, `release_video_job`, and `acknowledge_cancel_video_job` are lease-fenced by worker, token, attempt, and revision.
- `begin_job_stage` is idempotent by `(job, revision, stage, item_key, input_hash)`.
- `reserve_stage_external_attempt` owns provider, TTS, renderer, database, filesystem, and workflow delivery counters.
- `finalize_stage_success` and `fail_job_stage` require both lease and stage run tokens.
- Regeneration uses only `enqueue_regeneration` and client request idempotency.
- Internal stages have `workflowTrigger`, not public webhooks or Respond to Webhook nodes.

## Verification

Static tests inspect every edited workflow for trigger type, Execute Workflow references, RPC names, required context fields, idempotency expressions, retry ownership, regeneration enqueue-only behavior, and unchanged WF16 content. Existing foundation and asset-path tests remain mandatory.
