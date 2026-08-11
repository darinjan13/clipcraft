# ClipCraft AI Agent Handoff

## What This Is

ClipCraft AI is a local-development n8n-centered short-form vertical video pipeline. The repository is the primary engineering source of truth, and the `clipcraft/` Docker/n8n stack is the canonical development runtime. Two alternate trees and historical backups also exist.

## Read First

1. `docs/CURRENT_STATE.md`
2. `docs/PROJECT_CONTEXT.md`
3. `docs/SYSTEM_ARCHITECTURE.md`
4. `docs/WORKFLOW_CATALOG.md`
5. `docs/TESTING_STRATEGY.md`
6. `clipcraft/IMPLEMENTATION_REPORT.md`
7. `clipcraft/shared-contract.md`
8. `functional_tests.py`

## Current Milestone

WF17 and WF18 functional verification and remediation closure.

## Accepted Decisions

- Use documented public n8n APIs instead of SQLite/internal database access.
- Use disposable parent workflows for approved functional tests.
- Correlate asynchronous child executions with `_testCorrelationId`.
- Treat provider request shapes as contracts.
- Never expose secrets in diagnostics.
- Prefer repository evidence and label unknowns explicitly.
- Require validation output and runtime evidence separately.
- Retain `Workflow Trigger.parameters.events: ["update"]`; the local n8n runtime rejects empty trigger parameters during public-API updates.
- Retry state must remain in the current item as `retryCount`; never use `$('Retry').all()` or future-node execution history.
- `retryExhausted` is true only for retryable provider failures with `retryCount >= 2`; non-retryable failures remain `PROVIDER_ERROR`.

## Prohibited Without Explicit Approval

- Do not enable runtime API tests during onboarding or static review. Running the default static-only mode is allowed.
- Do not contact n8n, Supabase, Cloudflare, TTS, or other runtime services without approval.
- Do not modify production workflows.
- Do not access SQLite or `execution_entity`/`execution_data`.
- Do not use undocumented `/rest` endpoints in new tooling.
- Do not modify credentials or `.env` configuration.
- Do not delete legacy trees or backup artifacts.

## Environment Assumptions

Runtime tests require explicit `N8N_BASE_URL`, `N8N_API_KEY`, `WF17_ID`, `WF18_ID`, `WF17_EXPECTED_NAME`, `WF18_EXPECTED_NAME`, Cloudflare settings, timeout, polling, skew, and page-bound configuration. Actual values are not documented here.

## Current Blockers

- Valid provider and retry paths remain intentionally unexecuted.
- Runtime public API scopes, workflow identity, topology, and validation response envelopes are verified.
- Repository and live WF17/WF18 definitions match after public-API alignment.
- The repository is the engineering source of truth; `clipcraft/` is the canonical local-development runtime configuration.
- No separate production deployment should be assumed.
- Configuration discovery found the primary local n8n URL as `http://localhost:5680` from `clipcraft/.env` and the primary Compose port mapping.
- Live IDs `17` and `18` were discovered by exact workflow name through the authenticated public API; repository IDs were not assumed.
- Existing cookie-login `/rest` scripts remain prohibited and were not used.

## Last Validated State

- `py -3 -m py_compile functional_tests.py` passed during the latest implementation pass.
- Static canonical contract checks passed with runtime invocation disabled.
- All seven modified workflow JSON files parsed successfully after caller migration.
- Eleven validation-only runtime executions passed with provider and retry nodes absent.
- Disposable parent workflows were deleted and verified with HTTP 404.

## Next Safe Action

Request approval for the controlled Cloudflare provider test matrix. Do not run valid generation, provider-failure, or retry tests without that approval.

## Documentation Rule

After every meaningful change, update the affected documentation, record exact validation commands/results, identify conflicts and unknowns, and do not claim runtime success from static evidence.

## Working Principles

- Repository evidence overrides assumptions.
- Documentation is the project's memory.
- Never guess runtime state.
- Verify before modifying production.
- Prefer public APIs over internal access.
- Separate verified facts from assumptions.
- Update documentation whenever new facts are discovered.
- Never bypass engineering safeguards for convenience.
