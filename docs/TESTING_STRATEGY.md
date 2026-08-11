# Testing Strategy

## Test Layers

### Unit and Pure-Function Tests

The primary repository has asset-path tests in `clipcraft/tests/test_asset_paths.py`. These compare path behavior against the documented canonical contract. Additional unit coverage for workflow contract builders and safe diagnostics is **UNKNOWN**.

### Static Verification

- Python syntax: `py -3 -m py_compile <file>`.
- Workflow JSON and topology validation: existing validation scripts/reports, not necessarily all reproducible from a clean environment.
- Secret scans and Compose validation are reported in `clipcraft/IMPLEMENTATION_REPORT.md`, but were not rerun during onboarding.

### Structural Workflow Verification

Structural verification should inspect workflow names, source identifiers, trigger types, node names, connections, provider URLs, active flags in source, and caller references. It must distinguish repository JSON from live n8n state.

### Functional Testing

Root `functional_tests.py` performs static contract checks by default. Runtime API tests require explicit `CLIPCRAFT_ENABLE_RUNTIME_TESTS=true` plus `N8N_API_KEY`, `N8N_BASE_URL`, `WF17_ID`, `WF18_ID`, expected names, provider settings, and validated timing/page configuration.

Milestone 2 verified the local public API configuration, discovered live workflow identities by exact name, aligned both workflows, and executed the approved invalid-input matrix. Valid provider and retry paths remain intentionally unexecuted.

The suite must verify target identity before creating parents, use public workflow/execution endpoints, correlate with `_testCorrelationId`, bound execution pagination, and clean up every created parent.

### Integration and End-to-End Testing

Credentialed end-to-end tests are explicitly listed as remaining work in `clipcraft/IMPLEMENTATION_REPORT.md`. They require a running stack, valid Supabase credentials/data, Cloudflare credentials, local TTS readiness, and an approved runtime window.

### Security Testing

Security testing should cover webhook authentication, service-role exposure, download path traversal, internal API-key enforcement, error redaction, RLS policies, execution-data retention, and container privileges.

## Current WF17/WF18 Matrix

### WF17 Valid

- Top-level prompt.
- Body prompt fallback.
- Top-level prompt wins over body prompt.
- Body `systemPrompt` fallback.
- Top-level `systemPrompt` wins over body value.
- Top-level metadata wins over body metadata.
- Body metadata fallback.

### WF18 Valid

- Top-level prompt.
- Body prompt fallback.
- Top-level prompt wins over body prompt.
- Top-level metadata wins over body metadata.
- Body metadata fallback.

### Both Workflows Invalid

- Missing prompt.
- Whitespace-only prompt.
- Non-string prompt.
- Null metadata.
- Array metadata.
- String metadata.
- Numeric metadata.
- Boolean metadata.
- Top-level null metadata overriding valid body metadata.
- Unsupported provider.

Invalid executions require `Build Request`, `Validate Input`, `Handle Validation Error`, and `Normalize Response`, and must not execute `Call Provider API`. Static checks also assert UTC timestamps, structured error sources, bounded retries, marker isolation, and WF18 context fields.

The default static-only command is `py -3 functional_tests.py`. It parses all
seven modified workflow files, checks caller topology and deprecated aliases,
validates representative normalized success/error fixtures, and reports
runtime API tests as `SKIP`. Runtime tests require explicit opt-in with
`CLIPCRAFT_ENABLE_RUNTIME_TESTS=true`.

The local n8n runtime rejects an empty `Workflow Trigger` configuration during
public-API publication. Static and runtime checks therefore require
`parameters.events` to equal `["update"]` in both WF17 and WF18.

Retry tests must assert item-level `retryCount` progression `0 -> 1 -> 2`,
three maximum provider attempts, explicit `Increment Retry` execution, and
the absence of `$('Retry').all()` or any future-node state lookup.
They must also distinguish retryable exhaustion from non-retryable provider
failure: `retryExhausted` requires `retryableProvider` and `retryCount >= 2`.

## Provider Contract Assertions

WF17 and WF18 provider request output must have exactly `isValid`, `provider`, `url`, `headers`, and `body` keys. WF17 body contains `messages`, `max_tokens: 5000`, and `temperature: 0.6`. WF18 body contains `prompt`. `_testCorrelationId` must not appear in provider output, headers, or body.

## Cleanup and Correlation

- Create the disposable parent only after target identity checks pass.
- Store the created parent ID immediately after successful creation.
- Correlate child executions by exact marker and timestamp.
- Deactivate, delete, and verify `404`/`410` in `finally`.
- Report cleanup failures separately and force a nonzero exit.

## Prohibited Methods

- n8n SQLite inspection for functional evidence.
- `execution_entity` or `execution_data` queries.
- Undocumented `/rest` endpoints in new functional tooling.
- Selecting arbitrary latest executions without exact correlation.
- Mutating WF17/WF18 solely to support testing.
- Printing credentials or raw sensitive response bodies.
