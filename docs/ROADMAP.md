# Roadmap

## Completed or Reported Complete

- Primary 18-workflow source set created.
- Supabase schema, queue claiming, retry functions, and asset-path functions added.
- Python canonical asset-path implementation added.
- Local TTS and FFmpeg rendering components added.
- Static workflow/path/render validation reported in `IMPLEMENTATION_REPORT.md`.
- API-only WF17/WF18 functional-test design implemented but not runtime-approved.

## In Progress

- WF17/WF18 remediation closure and functional verification.
- Repository onboarding and documentation.
- Reconciliation of primary, legacy, backup, and live workflow identities.

## Next

- Read-only public API identity verification after approval.
- Confirm canonical deployment tree.
- Confirm Supabase migration state.
- Validate public webhook authentication and user/job ownership.
- Resolve WF17/WF18 source versus handoff topology conflict.
- Run approved functional matrix only after preconditions pass.

## Later

- Wire Supabase migrations into deployment automation.
- Add credentialed end-to-end coverage.
- Establish CI/CD, monitoring, alerting, and rollback.
- Implement or document the frontend integration.
- Add explicit security and authorization tests.
- Resolve or archive legacy trees after an approved canonical-source decision.

## Proposed, Not Committed

- TLS and authenticated reverse proxy.
- Non-root n8n runtime.
- Explicit RLS policies and user ownership enforcement.
- Provider abstraction tests beyond Cloudflare.
- Formal backup encryption and restore drills.

## Unknown

- Product-market roadmap, user-facing feature priorities, commercial model, and release schedule.
