# Engineering Guide

## Scope

This guide applies to the primary `clipcraft/` implementation until an authoritative deployment boundary is chosen.

## Coding Standards

- Keep production code ASCII unless an existing file requires otherwise.
- Prefer small, explicit functions and stable data contracts.
- Do not introduce compatibility layers without a concrete persisted-data or external-consumer need.
- Preserve existing workflow naming and node responsibilities unless a reviewed change explicitly changes the contract.
- Python changes should be statically compiled with `py -3 -m py_compile <file>` when applicable.
- Do not modify legacy copies during a primary-tree change without documenting why.

## Workflow Standards

- Treat workflow JSON as production code.
- Use stable node names and explicit connection topology.
- Keep provider calls behind the intended provider abstraction.
- Validate external input before side effects.
- Preserve canonical job and asset contracts.
- Use Supabase RPCs for queue claiming and retry state transitions.
- Do not hard-code credentials or bearer tokens.
- Do not assume repository labels are live n8n IDs.

## API Standards

- Prefer documented public APIs.
- Do not use `/rest` in new functional or production tooling.
- Validate IDs, asset types, and path inputs.
- Do not assume invalid input must return HTTP 400 unless the workflow contract proves it.
- Return safe, stable response shapes.

## Security Rules

- Secrets belong in environment configuration, never workflow JSON or logs.
- Never print API keys, bearer tokens, raw provider headers, or raw response bodies.
- Keep service-role keys server-side.
- Keep download authentication in headers, not query strings.
- Preserve UUID and path-traversal validation.
- Treat public webhook authentication as an unresolved production risk until proven.

## Error Handling

- Distinguish configuration, authentication, transport, malformed data, assertion, timeout, and cleanup failures.
- Preserve the original failure when cleanup also fails.
- Sanitize error messages before returning them to clients or test result JSON.
- Ensure retry counters are explicitly propagated and bounded.

## Testing Standards

- Static validation is not runtime validation.
- Use explicit assertions that cannot be disabled, not Python `assert` statements for functional checks.
- Correlate asynchronous executions with unique markers.
- Bound polling and pagination.
- Verify cleanup after disposable resource creation.
- Test provider request URL, headers, body, and normalized keys as contracts.
- Do not access n8n SQLite for functional verification.

## Configuration Rules

- Keep configuration names documented in `.env.example` or the relevant test documentation.
- Require explicit workflow IDs and expected names for runtime tests.
- Validate URLs and numeric values before any side effect.
- Never edit `.env` during routine engineering work.

## Review and Production-Change Process

1. State the product goal and affected boundaries.
2. Inspect repository evidence before changing behavior.
3. Identify conflicts and assumptions.
4. Write or update the relevant design/contract documentation.
5. Make the smallest change that satisfies the approved scope.
6. Run static validation first.
7. Obtain explicit runtime approval before contacting n8n, Supabase, providers, or production workflows.
8. Report exact files, commands, results, and unresolved risks.

## Rollback Expectations

- Preserve pre-change workflow exports before approved workflow mutations.
- Preserve migration order and verify database state before and after migrations.
- Do not delete alternate copies during cleanup without an approved canonical-source decision.
- A formal production rollback procedure is **UNKNOWN** and must be established before deployment automation.
