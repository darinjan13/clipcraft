# Repository Map

## Top-Level Directories

| Path | Responsibility | Status |
|---|---|---|
| `clipcraft/` | Primary-looking 18-workflow implementation, Supabase migrations, TTS, video tools, Docker stack | Current candidate; canonical status not formally declared |
| `n8n-video-factory/` | Older/alternate 14-workflow implementation, docs, Docker, Supabase, renderer, tests | Legacy or alternate; retain until authoritative boundary is decided |
| `n8n-video-factory-v1/` | Earlier partial implementation and standalone schema | Explicitly incomplete Phase 1 |
| `backups/` | Historical workflow exports, ID maps, migration artifacts, reports, and SQLite backups | Historical; do not treat as runtime source |
| `migrations/` | Root-level n8n history repair migration script | Operational/debug artifact; not application Supabase migrations |
| `__pycache__/` | Generated Python bytecode | Generated; not source |

## Primary `clipcraft/` Tree

| Path | Responsibility |
|---|---|
| `clipcraft/workflows/` | WF01-WF18 JSON definitions and workflow catalog |
| `clipcraft/supabase/migrations/` | PostgreSQL schema, queue/retry RPCs, canonical asset-path RPCs |
| `clipcraft/supabase/run-migrations.sh` | Migration runner using `psql` or Supabase CLI |
| `clipcraft/video-tools/` | Asset paths, manifest validation, FFmpeg rendering and render test |
| `clipcraft/tts/` | Flask TTS server, Dockerfile, Python requirements |
| `clipcraft/tests/` | Asset-path tests and sample manifest |
| `clipcraft/docker-compose.yml` | Primary two-service local stack |
| `clipcraft/docker/` | n8n Dockerfiles and image configuration |
| `clipcraft/Dockerfile.n8n-patched` | Alternate patched n8n image build |
| `clipcraft/.env.example` | Primary environment variable template |
| `clipcraft/.env` | Environment-specific secrets/configuration; contents not inspected or documented |
| `clipcraft/shared-contract.md` | Job, asset, API, TTS, render, provider, and security contracts |
| `clipcraft/IMPLEMENTATION_REPORT.md` | Implementation metrics, decisions, validation claims, remaining work |
| `clipcraft/workflow-validation-report.json` | Generated/static workflow validation report |
| `clipcraft/apply-all-patches.js` | Patch utility; mutation status not established |

## Root Scripts

Root Python/JavaScript/shell files are mostly audits, diagnostics, migration helpers, n8n activation/remediation tools, and historical experiments. Important categories:

- `functional_tests.py`: current API-only functional-test implementation; not executed.
- `apply_remediation.py`, `patch_wf16*.py`, `reimport_wf16.py`, `recreate_wf.py`: workflow mutation/remediation tools; do not run without explicit approval.
- `verify_*.py`, `validate_*.py`, `integrity_check.py`, `final_audit.py`: structural/audit tools with mixed API/database assumptions.
- `audit*.py`, `forensic.py`, `check_*.py`, `extract_*.py`: diagnostic and historical inspection scripts.
- `test_*.py`, `run_wf18_test.py`, `activate_and_test.py`: historical or runtime-oriented tests; many use `/rest` and/or SQLite.
- `backups` and `pre_migration_backup.py`: backup artifacts and backup tooling.

No root package manifest, lockfile, CI configuration, or Git worktree was found.

## Workflow Files

The primary workflow set is `clipcraft/workflows/01-*.json` through `18-*.json`. See `WORKFLOW_CATALOG.md` for the full inventory and identifier distinctions.

## Generated and Sensitive Files

- `.env` files are environment-specific and sensitive.
- `backups/**/database.sqlite` is sensitive operational state and was not accessed.
- `__pycache__/` is generated.
- Workflow validation reports and exports are generated or historical unless explicitly identified otherwise.

## Likely Entry Points

- Local stack: `clipcraft/docker-compose.yml`.
- n8n workflow import/deployment: workflow JSON files and repository operational documentation.
- Public application API: WF01-WF15 webhook workflows.
- TTS service: `clipcraft/tts/server.py`.
- Rendering: `clipcraft/video-tools/render_video.py`.
- Functional verification: root `functional_tests.py` after runtime approval.

## Authority Warning

There are three implementation trees and multiple backup generations. No manifest declares which tree is authoritative. Do not delete or merge copies until that conflict is resolved.
