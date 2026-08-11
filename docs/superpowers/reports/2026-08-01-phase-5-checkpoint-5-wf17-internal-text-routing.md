# Phase 5 Checkpoint 5: WF17 Internal Text-Execution Integration

## Status

**Blocked by the required HMAC security gate. No WF17 workflow files were modified, imported, activated, or connected to the internal endpoint.**

The audit found that the current n8n runtime cannot be shown to compute the backend-required signature safely:

```text
HMAC-SHA256(secret, timestamp + "\n" + nonce + "\n" + exact raw request body)
```

WF17 is an internal `workflowTrigger` workflow. Its Code nodes receive parsed n8n item data, not the original HTTP byte sequence. Reconstructing the body with `JSON.stringify($json)` cannot guarantee byte-for-byte identity with the body later serialized by an HTTP Request node.

n8n crypto availability is also not established. Enabling `require('crypto')` would require a global module-access configuration change, which this checkpoint explicitly forbids without approval.

The hard-stop condition applies: do not weaken authentication or proceed with an unverifiable signature implementation.

## Files Changed

No production workflow files, backend files, frontend files, database files, migration files, callback files, or environment files were changed.

This report is the only file added for this blocked checkpoint.

## Read-Only Audit Results

### WF17 Nodes

WF17 is `clipcraft/workflows/17-ai-generate-text.json` with these relevant nodes:

```text
Build Request
  -> Validate Input
  -> Prepare Provider Attempt
  -> Call Provider API
  -> Evaluate Provider Result
  -> Retryable Failure?
  -> Increment Retry
  -> Prepare Provider Attempt
  -> Call Provider API
  -> Normalize Response
```

There is one direct provider HTTP node, `Call Provider API`. It currently calls Cloudflare directly using provider credentials from n8n environment data.

### Callers

The canonical callers are:

- `clipcraft/workflows/01-chat-message.json`
- `clipcraft/workflows/04-generate-script-and-scenes.json`

Both call WF17 by Execute Workflow reference. Caller contracts and downstream `response.result` consumption must remain unchanged.

### Existing Internal Endpoint

The backend endpoint already exists:

```text
POST /internal/ai/text/execute
```

It requires:

- `N8N_INTERNAL_SIGNING_SECRET`
- `X-ClipCraft-Timestamp`
- `X-ClipCraft-Nonce`
- `X-ClipCraft-Signature`

The endpoint uses exact raw-body HMAC verification, constant-time comparison, a five-minute timestamp window, bounded process-local nonce replay protection, and normalized Gemini/Cloudflare text execution.

### Future Internal Address

The current deployment runs the backend on the host and n8n in Docker. The audited private address is:

```text
http://host.docker.internal:8000/internal/ai/text/execute
```

No address was hardcoded into WF17 because the HMAC blocker prevented workflow changes. A configurable `CLIPCRAFT_INTERNAL_API_BASE_URL` should be introduced only with the approved integration design.

## Blocker Details

The following unsafe approaches were rejected:

1. Signing `JSON.stringify($json)` and allowing the HTTP node to serialize the body again.
2. Signing one object and sending a separately configured body expression.
3. Sending only a static API key.
4. Adding raw provider credentials to workflow input.
5. Enabling broad Code-node environment/module access without approval.
6. Logging or pinning the signed body, signature, nonce, or secret for debugging.

These approaches would violate the backend authentication contract or expose secrets in n8n execution data.

## Smallest Safe Alternatives

Approval is required before proceeding with one of these options:

### Option A: Narrowly Scoped n8n Signing Component

Provide a narrowly scoped n8n custom node or approved signing runtime that:

- Has guaranteed HMAC-SHA256 support.
- Receives the final serialized body string.
- Returns only timestamp, nonce, and signature.
- Does not expose the secret to ordinary Code nodes.
- Does not log or persist the body, signature, nonce, or secret.

The HTTP Request node must transmit the exact same serialized body string used by the signer.

### Option B: Approved n8n Crypto Configuration

Explicitly approve a narrowly scoped n8n configuration change that guarantees crypto availability and controlled environment access for WF17 only. This requires confirming:

- Exact n8n version and Code-node runtime behavior.
- Module allowlisting scope.
- Secret visibility scope.
- Execution-data redaction/retention behavior.
- Exact raw-body construction and transmission behavior.

No such approval was assumed.

### Option C: Dedicated Internal Signing Service

Introduce a separately authenticated internal signing component that accepts the final body and returns a signature without exposing the signing secret to n8n. This requires a new service boundary and security review, so it was not introduced under this checkpoint.

## Rollback And Mode

No `TEXT_EXECUTION_MODE` branch was added because the workflow was not modified.

The current effective behavior remains the existing legacy WF17 path. No internal endpoint call can occur from WF17 as a result of this checkpoint.

## Verification

No live provider request or live workflow import was performed.

The read-only audit confirmed:

- Existing WF17 direct-provider path remains untouched.
- Existing callers remain untouched.
- Existing retry and normalization paths remain untouched.
- Existing n8n workflow contracts remain untouched.
- The internal endpoint remains disconnected from n8n.

The implementation verification sequence was intentionally not started because the hard-stop security condition occurred before any implementation changes.

## Readiness

**Not ready for WF17 internal text-routing integration.**

The internal FastAPI boundary is ready, but WF17 cannot safely call it until an approved mechanism can produce an HMAC over the exact transmitted request body without exposing credentials or enabling unsafe global n8n runtime access.
