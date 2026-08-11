# Architecture Decision Records

## ADR-001: Public API Over Internal Database Access

- Status: Accepted
- Context: Earlier diagnostics and tests used n8n internal REST endpoints and SQLite execution tables. The public API exposes supported workflow and execution operations.
- Decision: New functional verification and operational tooling must use documented public n8n APIs. SQLite and internal database tables are prohibited unless a future ADR explicitly approves them.
- Reasons: Supported contract, less coupling to storage implementation, safer portability.
- Consequences: Tests require API-key scopes, API envelope behavior must be validated, and execution retention can limit evidence.
- Rejected alternative: Direct SQLite queries against `execution_entity` and `execution_data`.
- Evidence: Current `functional_tests.py`, installed public API specification, handoff requirements.

## ADR-002: Disposable Workflows for Functional Testing

- Status: Accepted
- Context: Testing production child workflows requires a caller without redesigning the children.
- Decision: Approved functional tests may create disposable parent workflows, invoke them, and always deactivate/delete/verify deletion in cleanup.
- Reasons: Isolates test orchestration from production child definitions.
- Consequences: Tests need workflow-management scopes and robust cleanup ownership.
- Rejected alternative: Mutating WF17/WF18 to add test-only instrumentation.
- Evidence: Current functional-test design and handoff requirements.

## ADR-003: Explicit Execution Correlation

- Status: Accepted
- Context: Child executions are asynchronous and historical execution lists may contain unrelated runs.
- Decision: Add a unique `_testCorrelationId` to each test payload and locate the child through trigger input data. Do not rely on `metadata.parentExecution` as the primary association.
- Reasons: Exact case isolation and independence from internal execution metadata.
- Consequences: Requires runtime confirmation that Execute Workflow preserves unknown fields and public execution data exposes trigger input.
- Rejected alternative: Selecting the latest execution or relying only on parent metadata.
- Evidence: Current `functional_tests.py` and handoff requirements.

## ADR-004: Provider Requests Are Contracts

- Status: Accepted
- Context: Provider URL, headers, body, normalized fields, and retry behavior are integration boundaries.
- Decision: Test provider request objects as explicit contracts. Silent shape changes are regressions unless intentionally approved.
- Reasons: Prevents accidental provider breakage and makes routing behavior reviewable.
- Consequences: Provider credentials must be compared internally without leaking them in diagnostics.
- Rejected alternative: Only asserting workflow success.
- Evidence: WF17/WF18 source JSON, `shared-contract.md`, current functional matrix.

## ADR-005: Production Changes Require Verification

- Status: Accepted
- Context: Static validation can pass while runtime workflows, credentials, or data stores remain incorrect.
- Decision: Significant changes require code evidence, validation output, runtime approval where applicable, and explicit remaining-assumption disclosure.
- Reasons: Avoids claiming runtime success from syntax or structural checks alone.
- Consequences: Work is staged into static and runtime phases.
- Rejected alternative: Treating implementation summaries as proof.
- Evidence: Handoff requirements and `IMPLEMENTATION_REPORT.md` limitations.

## ADR-006: Secrets Must Not Appear in Diagnostics

- Status: Accepted
- Context: Workflow responses, provider errors, and API responses may contain credentials or sensitive data.
- Decision: Never print API keys, bearer tokens, credential values, or raw response bodies that may expose secrets.
- Reasons: Limits accidental credential disclosure through logs and test artifacts.
- Consequences: Failures use safe descriptions instead of raw payloads.
- Rejected alternative: Printing full response objects for debugging.
- Evidence: `shared-contract.md`, current functional-test implementation, handoff requirements.

## ADR-007: Repository Evidence Over Assumptions

- Status: Accepted
- Context: The repository contains multiple implementation trees, backups, conflicting IDs, and no Git authority.
- Decision: Document facts with file evidence, label unsupported details UNKNOWN, and do not silently choose between conflicting copies.
- Reasons: Prevents accidental deployment or deletion of the wrong artifact.
- Consequences: Canonical-source selection is an explicit future decision.
- Rejected alternative: Treating the newest-looking folder or numeric label as authoritative.
- Evidence: `clipcraft/`, `n8n-video-factory/`, `n8n-video-factory-v1/`, and `backups/` inventory.
