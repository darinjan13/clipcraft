# Current State

## Current Milestone

WF17/WF18 canonical contract implementation and controlled local runtime verification. Provider-path testing remains a separate approval milestone.

## Completed According to Repository Evidence

- Primary `clipcraft/` source contains 18 workflow JSON files.
- Supabase schema and queue/retry/asset-path migrations exist.
- Local TTS service and video-tools renderer exist.
- Asset-path tests exist.
- API-only functional-test architecture and static contract checks are implemented in root `functional_tests.py`.
- The seven modified workflow JSON files parse successfully.
- `py -3 -m py_compile functional_tests.py` passes.
- Static canonical contract checks pass; runtime tests are disabled by default.
- Live WF17/WF18 were aligned through the documented public n8n API and both remain active.
- All approved validation-only cases passed with execution evidence showing no provider or retry nodes.

## Active Work

- Preparing the provider-call approval checkpoint; valid provider paths remain unexecuted.

## Blockers

- Valid Cloudflare provider and retry paths remain intentionally unexecuted.
- The repository is the primary engineering source of truth; `clipcraft/` is the canonical local-development runtime configuration.
- Configuration discovery found the primary `clipcraft/.env` and `clipcraft/docker-compose.yml` define the local n8n base as `http://localhost:5680` (`5680:5678` host/container mapping).
- Public API authentication, exact live workflow identities, topology, execution payload shape, and cleanup operations were verified.
- Existing runtime scripts use hard-coded cookie login through undocumented `/rest` endpoints; those credentials and endpoints are not used for public verification.

## Known Defects and Risks

- The n8n runtime required `Workflow Trigger.parameters.events = ["update"]`; this compatibility field is now present in both canonical repository files.
- A webhook wrapper must unwrap `body` before invoking internal WF17/WF18 to preserve top-level correlation and WF18 context fields.
- Milestone 3A replaces future-node retry inference with explicit item-level `retryCount` state and an `Evaluate Provider Result` decision node.
- Milestone 3B corrects exhaustion classification so non-retryable provider errors remain `PROVIDER_ERROR`.
- WF16 is documented as a shared dependency but has no current primary caller.
- Public webhook authentication is inconsistent or absent in source.
- RLS policies are not present in the primary migration.
- n8n runs as root and permits node environment access in the primary Compose configuration.
- HTTP is used instead of TLS in local/deployment configuration.
- No CI/CD or formal rollback process exists in repository evidence.
- Legacy trees contain divergent provider and workflow implementations.

## Unresolved Assumptions

See `TESTING_STRATEGY.md` and `AI_HANDOFF.md` for runtime assumptions concerning execution timestamps, trigger input preservation, public API envelopes, and provider contracts.

## Next Recommended Task

Request approval for the controlled Cloudflare provider test matrix. Do not run valid generation, provider-failure, or retry tests without that approval.

## Definition of Done for This Milestone

- Explicit runtime workflow IDs and exact names are confirmed.
- WF17/WF18 live topology matches the approved validation/error-path contract.
- Public API scopes and execution payload shape are confirmed.
- Functional matrix runs with exact correlation and safe diagnostics.
- Every disposable parent is cleaned up and deletion is verified.
- Results and residual assumptions are recorded.
