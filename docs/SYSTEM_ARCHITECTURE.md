# System Architecture

## Scope and Evidence

The diagrams describe repository-supported relationships. Dashed or labelled unknown boundaries indicate behavior documented but not implemented or not runtime-verified.

## System Context

```mermaid
flowchart LR
    User[Creator or operator\nexact persona UNKNOWN]
    Frontend[External frontend\nrepository not present]
    N8N[Local n8n workflow runtime\ncanonical development stack]
    Supabase[(Supabase/PostgreSQL)]
    CF[Cloudflare Workers AI]
    TTS[Local Kokoro/Piper TTS]
    FS[(Docker job volumes\n/data/jobs)]
    FFmpeg[FFmpeg/FFprobe]

    User --> Frontend
    Frontend --> N8N
    N8N --> Supabase
    N8N --> CF
    N8N --> TTS
    N8N --> FFmpeg
    N8N --> FS
    FFmpeg --> FS
```

The frontend relationship is documented but the frontend implementation is outside this repository.

## Component Architecture

```mermaid
flowchart TB
    subgraph Primary[clipcraft/ primary-looking source tree]
        W[WF01-WF15 public webhooks]
        Q[WF03 scheduled queue worker]
        I[WF16 asset paths\nWF17 text\nWF18 image]
        TTS[TTS Flask service]
        Tools[video-tools Python and FFmpeg]
        Migrations[Supabase migrations and RPCs]
    end
    DB[(Supabase/PostgreSQL)]
    Jobs[(clipcraft_jobs volume)]
    AI[Cloudflare Workers AI]

    W --> Q
    Q --> W
    W --> I
    I --> AI
    W --> DB
    Q --> DB
    W --> TTS
    W --> Tools
    Tools --> Jobs
    TTS --> Jobs
    Migrations --> DB
```

## WF17 Execution Flow From Repository JSON

```mermaid
flowchart LR
    Trigger[Workflow Trigger] --> Build[Build Request]
    Build --> Provider[Call Provider API]
    Provider --> Normalize[Normalize Response]
    Normalize --> Check[Check Retry]
    Check --> Retry[Retry]
    Retry --> Provider
```

The source JSON currently has no `Validate Input` or `Handle Validation Error` nodes. The handoff says live remediation added them, but live state was not contacted. This conflict is recorded in `CURRENT_STATE.md`.

## WF18 Execution Flow From Repository JSON

WF18 has the same source topology as WF17, with image-specific request construction and response normalization.

```mermaid
flowchart LR
    Trigger[Workflow Trigger] --> Build[Build Request]
    Build --> Provider[Call Provider API]
    Provider --> Normalize[Normalize Response]
    Normalize --> Check[Check Retry]
    Check --> Retry[Retry]
    Retry --> Provider
```

## Functional-Test Flow

```mermaid
flowchart TD
    Preflight[Validate explicit configuration] --> Identity[GET configured WF17/WF18\nverify name, active state, nodes, connections]
    Identity --> Parent[POST disposable parent]
    Parent --> ParentVerify[GET and verify parent]
    ParentVerify --> Activate[POST parent activate]
    Activate --> Invoke[POST disposable webhook]
    Invoke --> Page[GET public execution pages\nworkflowId + cursor + timestamp bound]
    Page --> Detail[GET execution with includeData=true]
    Detail --> Correlate[Match exact _testCorrelationId]
    Correlate --> Assert[Provider contract or invalid-path assertions]
    Assert --> Cleanup[Deactivate, delete, verify 404/410]
    Cleanup --> Results[Structured JSON result and exit code]
```

## Authentication Boundaries

- Functional verification uses `X-N8N-API-KEY` for documented n8n public API calls.
- Workflow service calls use environment-driven Cloudflare, Supabase, internal API, and TTS credentials.
- WF15 documents `X-Internal-Api-Key` authentication.
- Public WF01/WF02 source does not show caller authentication.
- Supabase service-role access is used from n8n and bypasses RLS; user-level authorization is not established.

## Observability

The repository provides n8n healthchecks and structured job status fields. A production metrics, logging, tracing, alerting, or retention design is **UNKNOWN**. n8n execution pruning is configured in `clipcraft/docker-compose.yml`.

## Deployment Architecture

The primary Docker Compose file defines `clipcraft-n8n` and `clipcraft-tts`, bridge networking, persistent volumes, healthchecks, and a host mapping of `5680:5678`. The alternate `n8n-video-factory/` stack uses different ports and image assumptions. The `clipcraft/` stack is the canonical local-development runtime; no separate production deployment is assumed.
