# Phase 5.5: n8n Deployment Recovery and Operational Readiness

## Final Status

**LIVE_RECONCILIATION_COMPLETE**

The deployment is healthy and repository custom-node packaging is now present in the running image. Authenticated API v1 access supported the controlled WF05/WF18 reconciliation and import with preserved IDs, credential reference, and active states. Owner UI authentication and legacy `/rest/*` access remain unavailable. Internal image execution is not enabled by default.

## Deployment Topology

- Active Compose service: `clipcraft-n8n`
- n8n version: `2.29.7`
- Rebuilt image tag: `clipcraft-n8n-debug:2.29.7-clipcraft-0.1.0`
- Running image digest after rebuild: recorded from Docker inspect; no secret data involved.
- Startup: `n8n start`
- Port: `0.0.0.0:5680 -> 5678`
- Protocol: HTTP
- Persistent n8n volume: `clipcraft_n8n_data:/root/.n8n`
- Database: SQLite at `/root/.n8n/database.sqlite`
- Custom extension path: `/opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft/dist`
- Encryption key: configured and preserved; value never printed.
- Running n8n health: HTTP 200 / healthy.
- Backend health from n8n network: `{"status":"ok"}`.
- Renderer health: `{"status":"ok"}`.

The renderer is running an older `clipcraft-n8n-debug:latest` image rather than the Compose-pinned n8n image. It was not changed in this deployment-only phase.

## Docker Findings

The missing `ClipCraftImageExecute.node.js` was caused by a stale/incomplete image build context, not by a source, manifest, mount, or n8n path defect.

Evidence before rebuild:

- Source contained both nodes.
- Host `dist` contained both nodes.
- Package manifest listed both nodes.
- Dockerfile copy/build steps were correct.
- Running extension directory contained only Text Execute and the credential.
- No runtime mount hid `/opt/clipcraft-n8n-nodes`.

The clean rebuild transferred the current package context, ran all 28 package tests, rebuilt `dist`, and copied the complete package into the image.

## Custom-Node Verification

After the rebuild and container recreation, runtime filesystem checks confirmed:

- `package.json`: present
- `ClipCraftTextExecute.node.js`: present
- `ClipCraftImageExecute.node.js`: present
- `ClipCraftInternalApi.credentials.js`: present
- n8n version: `2.29.7`
- Node.js version: `22.23.1`

The package manifest declares two nodes and one credential. Package tests passed: **28 passed**. Direct registry metadata could not be queried because the available API does not expose a node-types endpoint and owner UI/REST access remains unauthorized; runtime files, package manifest, Docker build output, and startup health provide the verified loading evidence available without owner access.

## Authentication Mode

- Built-in n8n user management is active/expected.
- Basic Auth is explicitly disabled: `N8N_BASIC_AUTH_ACTIVE=false`.
- No reverse proxy authentication was found in the active Compose deployment.
- n8n is exposed over HTTP on all host interfaces.
- `N8N_API_KEY` is configured in the container and is accepted by `/api/v1/*` endpoints, but its value was never printed.
- UI/password login continues to return unauthorized/wrong credentials.
- Legacy `/rest/*` access remains unauthorized.

## Authentication Recovery

No recovery reset was executed.

The installed image contains the official `n8n user-management:reset` command, but that operation resets user state, removes user accounts except the owner, and reassigns ownership. It was not used because this phase forbids destructive credential resets and the existing owner credential is unavailable.

No passwords were guessed. No SQLite account rows were edited. No encryption key was changed. No new n8n instance was created.

## API Access

Non-destructive API v1 access is restored through the existing configured API key:

- `GET /api/v1/workflows`: HTTP 200, 15 workflows.
- `GET /api/v1/credentials`: HTTP 200, 1 credential.
- Credential metadata identifies `ClipCraft Internal API` / `clipCraftInternalApi`.
- Workflow metadata was readable for WF05 and WF18.
- Disposable API probe workflow creation succeeded without read-only `tags` fields.
- Disposable probe update succeeded for workflow name and custom image-node parameters.
- Existing `clipCraftInternalApi` credential reference was preserved through update and export.
- Disposable probe activation and deactivation both returned HTTP 200 when using a temporary webhook trigger.
- Disposable probe export returned the expected two-node definition, and deletion returned HTTP 200.
- Post-cleanup counts remained unchanged: 15 workflows and 1 credential; WF05 and WF18 remained present.

Owner UI access and `/rest/*` workflow access remain blocked. A new API key was not created because the existing configured API key supports the required `/api/v1/*` capability validation; its value was not printed or stored in repository files.

## SQLite Verification

Read-only SQLite checks after the rebuilt container started:

- `PRAGMA integrity_check`: `ok`
- Workflows: 15
- Credentials: 1
- Users: 1
- Executions: 10,487

The database remains in `clipcraft_n8n_data`; no volume replacement or database write was performed. Existing foreign-key orphan records reported by the audit are application-level historical records, not SQLite page corruption.

## Backup Verification

The pre-recovery local backup remains at:

```text
backups/n8n-recovery/20260801-231151Z/
```

It contains:

- Full `/root/.n8n` data copy.
- SQLite database copy after a clean n8n stop.
- Docker Compose and Dockerfiles.
- Protected environment configuration.
- Custom-node package.
- Repository WF05/WF18 exports.
- Non-secret SHA-256 checksum manifest.

Verification recorded:

- 27 non-empty n8n-data files.
- 475,969,650 bytes of n8n data.
- SQLite database copy: 433,889,280 bytes.
- Non-secret checksum manifest present and non-empty.

The n8n container was restarted on the same named volume and same encryption configuration after backup. No `docker compose down -v`, volume removal, database replacement, or encryption-key replacement was used.

## Workflow Export and Counts

Read-only API exports were saved under:

```text
backups/n8n-recovery/20260801-231151Z/workflow-exports/live-current/
```

Live metadata:

- WF05: ID `gazJuTcoSGqYdGze`, live name `Generate Scene Images`, active, 27 nodes.
- WF18: ID `18`, live name `AI Generate Image`, active, 10 nodes.
- Total workflows: 15.
- Total credentials: 1.

The live WF05 definition has 27 nodes versus 24 in the repository definition, indicating unrelated live drift. WF18 has 10 nodes versus the repository’s integrated definition, as expected because the live workflow predates Checkpoint 6B. No import was attempted because owner-level mutation access and deliberate live-drift merge approval are not available.

## Runtime and Security Findings

- The rebuilt image contains the image node and credential package.
- n8n, backend, and renderer health checks pass.
- No custom-node load errors appeared in recent n8n logs.
- The Python task-runner virtual environment warning remains unrelated to JavaScript custom-node loading.
- Basic Auth is disabled while n8n is published on all interfaces over HTTP.
- Provider, Supabase, database, internal API, n8n API, and encryption secrets exist in local environment configuration and container environment. Values were not printed.
- A security review found plaintext secret material in repository artifacts and recovery backups; these should be rotated through an approved security process. Rotation was not attempted in this phase because it could invalidate encrypted credentials and is outside deployment recovery approval.
- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` and root execution remain deployment risks; they were not changed because this phase does not authorize product/security configuration changes.

## Tests and Checks

- Custom-node package tests: **28 passed**.
- Backend image tests: **20 passed**.
- Full backend suite: **262 passed**.
- Workflow contract suite: **76 passed**.
- Frontend build: passed.
- Docker Compose validation: passed.
- n8n image rebuild: passed; package tests executed inside the Docker build.
- SQLite integrity: `ok`.
- Backend health: passed from n8n network.
- n8n health: passed.
- Renderer health: passed.
- Targeted secret/log scans: no secrets were printed; no new logging calls were added.

## Remaining Blockers

1. Owner UI authentication is unavailable.
2. `/rest/*` owner/session access is unauthorized.
3. Production default cutover to internal mode requires a separate explicit approval; this checkpoint leaves legacy mode active.
4. The running image is now correct, but live n8n registry/UI confirmation is still pending authenticated access.
5. The n8n host is exposed over HTTP with Basic Auth disabled; this must be handled through an approved security/operations process before broader access.
6. Existing plaintext secrets and backup artifacts require approved rotation and access-control remediation.

## Readiness

**LIVE_RECONCILIATION_COMPLETE**

The deployment is runtime-ready and WF05/WF18 live reconciliation is complete. Legacy mode is restored and active; internal mode remains optional. Do not change the default mode, reset users, rotate the n8n encryption key, or begin Pexels integration automatically.

## Phase 6C Live Reconciliation

### Three-Way Sources

- Original live backup: `clipcraft/backups/n8n-recovery/20260801-231151Z/workflow-exports/live-current/WF05-live.json` and `WF18-live.json`.
- Current live definitions: authenticated API v1 exports captured before import.
- Repository definitions: `clipcraft/workflows/05-generate-scene-images.json` and `18-ai-generate-image.json`.
- Fresh rollback exports: `clipcraft/backups/n8n-recovery/20260801-231151Z/workflow-exports/pre-import-live/`.
- Reconciled artifacts: `clipcraft/backups/n8n-recovery/20260801-231151Z/workflow-exports/reconciled/`.

The original live backup and pre-import current live definitions matched in nodes and connections before import. The current live definitions were not treated as authoritative over repository architecture.

### Merged Decisions

| Workflow | Difference | Classification | Decision |
|---|---|---|---|
| WF05 | Stage begin/reserve/heartbeat/finalize graph was present but disconnected in live | Repository improvement | Restored repository stage orchestration and failure finalization connections. |
| WF05 | `request_id` generation was absent in live | Repository improvement | Preserved repository per-scene UUID generation using n8n sandbox-safe `crypto.randomUUID()`. |
| WF05 | Targeted-scene query and no-pending guard | Intentional live modification | Preserved live `sceneId` filtering and `Pending Scenes?`/`Return Existing Images` path. |
| WF05 | Live JPEG validation, BinaryData, `.jpg` write, and JPEG asset MIME | Intentional live modification; conflict with repository PNG path | Preserved live behavior because actual Cloudflare bytes are JPEG and the live persistence path is contract-compatible. |
| WF05 | Live disconnected image-processing nodes and repository PNG `Save Image File` | Conflict requiring merge | Kept live `Decode Image`/`Write Image File` BinaryData pipeline and connected it to repository stage finalization. |
| WF18 | Live 10-node Cloudflare-only graph vs repository 18-node mode-gated graph | Repository improvement; live implementation obsolete | Imported repository mode gates, retry graph, request-ID flow, custom node, adapter, and normalized response. |
| WF18 | Live prompt sanitization-only request builder | Obsolete implementation | Replaced with the repository caller-compatible request normalization. |
| WF18 | Workflow ID, active state, execution order, credential identity, operational metadata | Intentional live modification | Preserved live ID `18`, active state `true`, execution order, and existing credential reference. |
| WF18 | Internal adapter rejected JPEG while live provider returns JPEG | Conflict requiring merge | Adapter now accepts PNG and JPEG; BinaryData remains validated and the merged WF05 path preserves the detected MIME/extension. |

### Imported Workflows

- WF05: ID `gazJuTcoSGqYdGze`, active `true`, 27 nodes, final version `4cdaf283-897f-4620-909d-ff750b9eb0b3`.
- WF18: ID `18`, active `true`, 18 nodes, final version `96814afb-3228-41b9-8279-4a61768ec13d`.
- WF18 custom node: `CUSTOM.clipCraftImageExecute`.
- Credential: `ClipCraft Internal API`, ID `byn0eWsH3GMCxFWH`.
- Total workflow count remained 15; total credential count remained 1.
- No unrelated workflow was imported or modified.

### Controlled Verification

- Legacy final execution: n8n execution `25499`, success, one `Call Provider API`, zero custom-node runs, imageBase64 present, scene context preserved, request ID preserved, JPEG magic `ffd8ff`, 540,277 decoded bytes.
- Internal final execution: n8n execution `25490`, success, one `ClipCraft Image Execute`, zero legacy provider-call nodes, BinaryData present, imageBase64 present, JPEG magic `ffd8ff`, 413,475 decoded bytes, HMAC/backend path completed, scene context and request ID preserved.
- Immediate rollback: container recreated with `IMAGE_EXECUTION_MODE=legacy`; health returned HTTP 200 and the final legacy execution succeeded.
- The direct WF18 boundary verified the renderer-facing image contract fields and payload MIME/extension compatibility. WF05’s merged static graph preserves scene ordering by `scene_index`, padded filenames, and the live JPEG MIME/write path.
- Earlier controlled diagnostics exposed and corrected n8n sandbox `require('crypto')`, unselected-node expression references, backend startup loading, and JPEG adapter compatibility. Those failures were not reported as successful verification.

### Final Verification

- Reconciled JSON parse and connection validation: passed for both artifacts.
- Repository workflow validation: 21 workflow JSON files valid; node IDs and connection targets valid.
- Workflow contract tests: **78 passed**.
- Backend suite: **262 passed**.
- Custom-node suite: **28 passed**.
- Frontend build: passed (`tsc -b && vite build`).
- Source secret-pattern scan: clean for backend app, frontend source, workflow source, and custom-node source. Existing protected `.env`/backup findings remain documented from Phase 5.5.
- Final runtime state: n8n healthy, `IMAGE_EXECUTION_MODE=legacy`, WF05/WF18 active, IDs and credential preserved.

### Readiness

**LIVE_RECONCILIATION_COMPLETE**

WF05 and WF18 are reconciled and imported with legacy mode restored as the default. Internal execution remains optional. Stop here; do not enable internal mode by default and do not begin Pexels integration.
