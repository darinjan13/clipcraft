# Checkpoint 1T: Restore queue-worker `Images OK?` routing contract and repair invalid IF operators across WF03/05–08/11/15

- **Date:** 2026-08-07
- **Project:** clipcraft-ai (live: `dpcytfpqhxpqufcsivkh`)
- **Scope gate:** Checkpoint 1S approval → queue-worker `"equal"` IF follow-up flagged in 1S, user-ratified extension to WF11/15.
- **Status:** Repaired operators + restored routing contract, deployed to live, repo↔live parity verified, 21-case provider-free runtime probe all PASS, regression green. No provider-backed/production generation this deployment.

## Objective
Repair runtime-invalid `IF` operators on the video-generation pipeline and restore the queue worker's `Images OK?` routing contract so a successful scene-image generation advances the job (`TRUE → Update Progress Narration`) and a provider failure routes to the error lane (`FALSE → Format Images Error`).

## Constraint set (1T)
- Modify **only** IF operator semantics + the two connection swaps that restore the intended routing contract.
- Do **not** modify payloads, response schemas, downstream nodes, retry logic, graph edges (other than the swap), custom nodes, migrations, or frontend.
- Fail-first runtime test before any fix; stop if runtime contradicted the assumed contract.
- All changes provider-free; no production generation.

## Real defects found and fixed (all confirmed by live runtime probes first)

### 1. `equal` → `equals` (unknown-operator failure)
n8n's V2 IF boolean switch (`filter-parameter.js`) only supports `equals`, `notEquals`, `true`, `false`, `empty`, `notEmpty`. The latent `equal` matched **no** case → every condition evaluated false → deterministic fallthrough regardless of the carried value. Fixed `equal`→`equals` on:
- WF03 queue worker: `Job Claimed?`, `Images OK?`, `Render OK?` (top-level + activeVersion nodes).
- WF05/06/07/08 `Stage Started?` (top-level + activeVersion nodes).
- WF11 `Job Completed?` (string compare).
- WF15 `Input Valid?`, `Exist OK?`.

### 2. `larger` → `gt` (numeric compare, WF11 `Job Found?`)
`larger` is not the valid name; the numeric operator is `gt`. Fixed with a real numeric `rightValue: 0`.

### 3. String-instead-of-native typed `rightValue` (WF11/15)
`rightValue` was stored as JSON strings (`"=true"`, `"=0"`) with empty `options:{}`, producing `Wrong type: 'true' is a string but was expecting a boolean` at runtime. Normalized to real boolean/number `rightValue` + `options:{caseSensitive:true, leftValue:'', typeValidation:'strict', version:1}` + `combinator:'and'` — exactly the proven WF04/WF05/pipeline pattern.

### 4. `Images OK?` connection inversion (root intent defect)
Current repo + live had `Images OK?` inverted (`TRUE → Format Images Error`, `FALSE → Update Progress Narration`). All 16 historical queue-worker backups store `TRUE → Update Progress Narration`, `FALSE → Format Images Error`, and WF05 subworkflow returns `{success:true}` on success / `{success:false}` on provider failure. Restored to the historical/contract-correct wiring.

### 5. WF11 `Valid Input?` branch swap
`Valid Input?` was wired inverted (TRUE→Load Job). The `Validate` node contract returns `{error:true}` on invalid request and `{jobId}` on valid; therefore TRUE→`Format 500` (error), FALSE→`Load Job` (success). Ratified by user; branches swapped.

### 6. WF15 `Read File` schema drift (caught during deploy)
Live `15-download-asset.json`'s `Read File` node had lost the required `fileSelector` parameter (fell back to legacy `filePath`), and n8n 2.29.7 rejected publishing it. Restored the clean `{dataPropertyName, options, fileSelector}` form from the pre-deploy live backup.

## Applied
- Repo files updated: `clipcraft/workflows/03-video-job-worker.json`, `05-generate-scene-images.json`, `06-generate-narration.json`, `07-build-captions.json`, `08-build-render-manifest.json`, `11-get-video-result.json`, `15-download-asset.json`.
- Deployed to live via `PUT /api/v1/workflows/{id}` (from live-backup base + repo IF/connection fixes kept in sync with repo), then re-activated.

| Workflow | live ID | version |
|---|---|---|
| Video Job Queue Worker | `1usjkGUZXjFpXZNU` | 38 |
| Generate Script and Scenes | `dWTF2UGXX3R73PDW` | 58 |
| Generate Scene Images | `gazJuTcoSGqYdGze` | 29 |
| Generate Narration | `UhWkv3GLHVSpWrMe` | 16 |
| Build Captions | `dNgYGCqkbwr552EW` | 10 |
| Build Render Manifest | `iik8qVHvgD9xWWjI` | 9 |
| Get AI Video Result | `wCuJOUfs242lrkO3` | 2 |
| Download Video Asset | `q92RjJtxMX48AYHv` | 12 |

- `Images OK?` on live now: TRUE→`Update Progress Narration`, FALSE→`Format Images Error`.
- `Render OK?` on live: TRUE→`Complete Job RPC`, FALSE→`Format Render Error` (unchanged, verified intact).
- Repo↔live parity (IF operator `operation` + `rightValue` + `combinator`+`options`, and the `Images OK?`/`Valid Input?` connection maps) verified byte-equal for all 8 deployed.

## Provider-free runtime probe (live)
Temp workflow per case was created, executed through the deployed IF node config (`conditions`).
- **WF03 `Images OK?`**: `{success:true}`→TRUE, `{success:false}`→FALSE.
- **WF03 `Render OK?`**: success→TRUE, failure→FALSE.
- **WF03 `Job Claimed?`**: id present→TRUE, none→FALSE.
- **WF05–08 `Stage Started?`**: `STARTED`→TRUE, other→FALSE.
- **WF11 `Valid Input?`**: `{error:true}`→TRUE, `{jobId}`→FALSE (with branch swap applied).
- **WF11 `Job Found?`**: count>0→TRUE, count=0→FALSE (numeric `gt`).
- **WF11 `Job Completed?`**: `completed`→TRUE, `processing`→FALSE.
- **WF15 `Input Valid?`/`Exist OK?`: valid→TRUE, invalid/missing→FALSE.

**Result: 21/21 passed.**

## Tests
- New regression guards in `clipcraft/tests/test_if_operator_contract.py` (8 tests): queue worker `Images OK?` wiring matches historical contract; all V2 boolean IFs use `equals` (no `equal`); WF11 branch swap + supported operators; normalized strict rightValue on WF11/WF15. All pass.
- Full `clipcraft/tests` regression: **180 passed** (58 in `test_*integration + contract` targeted subset).
- Backend/n8n-factory: **261 passed** (1 pre-existing unrelated failure — a test points to `009_video_job_configuration_snapshots.sql` which does not exist in the repo migration set; not introduced by this checkpoint).
- `frontend build` (tsc + vite): passes.
- `docker-compose config -q`: valid for both compose files (pre-existing obsolete `version` warning only).
- Secret scan across `clipcraft/workflows`: matches are parameter-name strings (`"name":" apikey"`) and `$env.*` credential references — no literals committed.
- Live health: 15 workflows, 15 active, no probe leftovers.
- Supabase: `video_jobs` = 46 cancelled + 1 failed, 0 queued/processing; `job_stage_runs` empty; no active leases. No jobs were disturbed.

## Backups
- `backups/checkpoint-1t-pre-operator-repair_20260807_024327/` — pre-repair repo copy of all workflows.
- `backups/checkpoint-1t-live-pre-deploy_20260807_034713/` — pre-deploy live GET snapshots (incl. the known-good `15` with `fileSelector`).

## Rollback path
Restore from `checkpoint-1t-live-pre-deploy_20260807_034713/` if needed; note that pre-fix routing already contained the `wrong`/`drift` states, so rollback would re-introduce the routing defect. Rollback status: **NO**.

## Next
Proceed to Phase G/H (provider-free end-to-end video generation) with the queue worker now able to route generation success/failure correctly.