# Phase 5 Checkpoint 5A: Custom n8n Text Client

## Status

**Complete for package implementation and isolated verification. WF17 remains unchanged and no production workflow traffic was moved.**

The narrowly scoped `n8n-nodes-clipcraft` package provides one credential type and one text-execution node for the existing authenticated FastAPI boundary:

```text
POST /internal/ai/text/execute
```

The package solves the Checkpoint 5 signing blocker by serializing the normalized request once, computing HMAC-SHA256 over those exact UTF-8 bytes, and transmitting the same `Buffer` with an explicit content length.

## Included Types

### Credential

```text
Display name: ClipCraft Internal API
Type:         clipCraftInternalApi
```

The credential contains only:

- A private FastAPI base URL.
- A password-masked internal HMAC signing secret.

It does not contain Gemini, Cloudflare, Supabase, or other provider credentials. n8n persists the credential through its encrypted credential store when a stable `N8N_ENCRYPTION_KEY` is configured.

### Node

```text
Display name: ClipCraft Text Execute
Type:         clipCraftTextExecute
Export name:  CUSTOM.clipCraftTextExecute
```

The node supports Gemini and Cloudflare text-generation requests only. The internal route is fixed and cannot be supplied by workflow data.

## Signing And Transport

For each item, the node:

1. Builds the normalized internal request contract.
2. Calls `JSON.stringify` once.
3. Converts the result to one UTF-8 `Buffer`.
4. Generates a Unix timestamp and cryptographically random UUID nonce.
5. Computes:

```text
HMAC-SHA256(secret, timestamp + "\n" + nonce + "\n" + exact raw request body)
```

6. Sends the same `Buffer` to `/internal/ai/text/execute` with the required timestamp, nonce, signature, content type, and content length headers.

Node's built-in `crypto`, `http`, `https`, `dns`, and `net` modules are used directly. No global Code-node module allowlist, environment access expansion, signing service, or third-party runtime dependency was introduced.

## Security Controls

- Only `http` and `https` private base URLs are accepted.
- Credentials in URLs, paths, queries, and fragments are rejected.
- Public literal addresses and public DNS resolutions are rejected.
- Every DNS result must be private.
- The validated DNS address is pinned into the connection lookup callback, preventing validation/connection rebinding.
- The total deadline starts before DNS and covers resolution, connection, upload, and response handling.
- Timeout is bounded from 1 to 120 seconds.
- Redirects are not followed.
- Request bodies are limited to 1 MiB.
- Responses are limited to 4 MiB.
- Backend/provider error text is replaced by fixed local messages.
- Output excludes credentials, signatures, nonces, headers, and raw responses.
- The node and credential implementation contain no logging calls.
- `.dockerignore` prevents local environment files from entering Docker build contexts.

## Packaging

Package path:

```text
clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft
```

Runtime installation path:

```text
/opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft
```

n8n discovery path:

```text
/opt/clipcraft-n8n-nodes/n8n-nodes-clipcraft/dist
```

This path is outside `/root/.n8n`, so the existing persistent n8n volume does not hide the extension.

The package is dependency-free and targets Node.js 22.22 or newer. Its dry-run archive contains exactly four files:

- `README.md`
- `package.json`
- `dist/credentials/ClipCraftInternalApi.credentials.js`
- `dist/nodes/ClipCraftTextExecute/ClipCraftTextExecute.node.js`

The lightweight image is:

```text
clipcraft-n8n-debug:2.29.7-clipcraft-0.1.0
```

Its base is pinned to:

```text
clipcraft-n8n-debug@sha256:35b1892f05fcb3ec9e168e7cd73bf428f6cfcde9c3b9b3423c7cbc033b59c7f3
```

## Files Changed

- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/package.json`
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/package-lock.json`
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/README.md`
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/scripts/build.mjs`
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/scripts/clean.mjs`
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/src/credentials/ClipCraftInternalApi.credentials.js`
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/src/nodes/ClipCraftTextExecute/ClipCraftTextExecute.node.js`
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/test/clipcraft-text-execute.test.js`
- `clipcraft/n8n-custom-nodes/n8n-nodes-clipcraft/test/package-contract.test.js`
- `clipcraft/docker/n8n-custom-nodes.Dockerfile`
- `clipcraft/docker/n8n-debug.Dockerfile`
- `clipcraft/docker/n8n.Dockerfile`
- `clipcraft/docker-compose.yml`
- `clipcraft/.dockerignore`
- `clipcraft/.env.example`
- This report.

No FastAPI production route, frontend source, database, migration, callback, provider adapter, or canonical workflow file was changed for Checkpoint 5A.

## Verification

### Package Tests

```text
17 passed
```

Coverage includes:

- Credential masking.
- Single request normalization and serialization.
- Deterministic HMAC and an independently confirmed backend golden vector.
- Exact signed/transmitted byte identity.
- Unique nonce generation.
- Fixed internal path and unsafe URL rejection.
- Full node `execute()` integration against a mocked internal endpoint.
- Safe success/error normalization.
- Empty and malformed response handling.
- Total timeout handling.
- Request and response size limits.
- Redirect refusal.
- Package discovery metadata.
- Canonical WF17 immutability.

### Repository Verification

```text
Backend:                  242 passed
ClipCraft contracts:      65 passed
Frontend production build: passed
npm pack --dry-run:       passed, 4 files
Docker image build:       passed
```

### Isolated n8n Verification

The final image was started with a disposable persistent volume and did not replace the live n8n container.

```text
n8n:                     2.29.7
Node.js:                 22.23.1
Health endpoint:         passed
Exported node types:     897
Custom node discovered:  CUSTOM.clipCraftTextExecute
Credential imported:     passed
Credential persisted:    passed after restart/recreation
Plaintext export check:  no base URL or signing-secret fields present
```

The live `clipcraft-n8n` container remained healthy on its existing image throughout verification.

### Secret Review

- No provider credential name or environment access exists in package runtime code.
- No logging call exists in source or distribution runtime code.
- No real signing secret or provider credential is embedded in source, distribution, package archive, or final image inputs.
- Signature and credential identifiers appear only where required to implement signing and credential lookup.

## WF17 And Rollback

`clipcraft/workflows/17-ai-generate-text.json` is unchanged. Its callers, retry behavior, normalization behavior, and direct-provider legacy path remain authoritative.

Checkpoint 5A adds no `TEXT_EXECUTION_MODE` branch because it does not integrate the node into WF17. Rollback is therefore limited to restoring the prior n8n image/build configuration; no workflow, backend, database, or frontend rollback is required.

## Residual Limitations

- Existing legacy workflows still receive provider credentials in the n8n environment, and `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` remains enabled. This pre-existing risk cannot be removed while preserving the current WF17 rollback path.
- Existing Compose runs n8n as root even though the image returns to `USER node`; changing persistent-volume ownership is outside this checkpoint.
- The pinned base image uses a local repository name. A clean deployment host must have the matching digest or publish it to an approved registry.
- Operators must create the encrypted `ClipCraft Internal API` credential manually and retain a stable, strong `N8N_ENCRYPTION_KEY`.
- The backend must be reachable through a private service name or address from the n8n network.
- Mixed/public DNS rejection and DNS-deadline behavior are implemented but are not exercised with a controlled DNS server in the automated suite.

## Readiness

**Checkpoint 5A is ready as an isolated custom-node package and Docker artifact.**

It is not authorization to modify WF17, import or activate production workflows, send live provider traffic, or remove the legacy execution path. A later approved checkpoint must wire WF17 to this node through an encrypted credential while preserving unchanged caller output and rollback behavior.
