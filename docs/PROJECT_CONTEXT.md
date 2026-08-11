# ClipCraft AI Project Context

## Evidence Basis

This document is based on repository files and the project owner's local-development clarification. The repository is the canonical source code. Local Docker/n8n state is the canonical execution runtime. Local runtime secrets, local runtime state, Git history, and frontend source were not inspected.

## Product Mission

ClipCraft AI is intended to turn a structured brief or conversational brief into a short-form vertical AI video. The documented pipeline creates a script and scene plan, generates scene images and narration, builds captions and a render manifest, renders an MP4, and exposes status, result, regeneration, and download endpoints.

Primary evidence:

- `clipcraft/IMPLEMENTATION_REPORT.md`
- `clipcraft/shared-contract.md`
- `clipcraft/workflows/README.md`

## Problem Being Solved

The system automates the content-production pipeline for short social videos, including AI-assisted writing, visuals, narration, captions, file assembly, and delivery. The specific business problem, target market, tenancy model, billing model, and user personas are **UNKNOWN**.

## Intended Users

The repository implies content creators or operators producing vertical social videos. Exact user roles, organization model, permissions, and audience demographics are **UNKNOWN**.

## Confirmed Capabilities

- Conversational brief clarification through WF01.
- Video-job creation through WF02.
- Scheduled queue processing through WF03.
- AI script and scene generation through WF04 and WF17.
- Scene-image generation through WF05 and WF18.
- Local narration through WF06 and the TTS service.
- ASS caption generation through WF07.
- FFmpeg manifest and video rendering through WF08 and WF09.
- Job status and result retrieval through WF10 and WF11.
- Scene and whole-video regeneration through WF12 and WF13.
- Error handling and retry tracking through WF14 and Supabase functions.
- Authenticated asset download through WF15.
- Canonical asset-path resolution through WF16, PostgreSQL, and Python.

## Technology Stack

- Workflow orchestration: n8n, pinned to `2.29.7` in `clipcraft/docker/n8n.Dockerfile` and `clipcraft/docker/n8n-debug.Dockerfile`.
- Workflow definitions: JSON under `clipcraft/workflows/`.
- Datastore: Supabase/PostgreSQL through REST and RPC calls.
- Local TTS: Flask service using Kokoro first and Piper fallback.
- Media processing: Python, FFmpeg, and FFprobe.
- Containerization: Docker Compose for the primary `clipcraft/` stack.
- Functional verification: Python public-API client in root `functional_tests.py`.
- Frontend: no frontend source was found in this repository. A Next.js proxy route is documented but not implemented here.
- Package management: no root package manifest or complete Python project manifest was found. TTS dependencies are in `clipcraft/tts/requirements.txt`.

## External Services

- Cloudflare Workers AI for text and image generation.
- Supabase REST/RPC and PostgreSQL.
- No external cloud TTS is intended in the current `clipcraft/` TTS service.

## Data and Storage

- Supabase tables: `channels`, `chat_sessions`, `chat_messages`, `video_jobs`, `scenes`, and `assets`.
- Local job assets: `/data/jobs/{jobId}/`.
- n8n persistence volume: `clipcraft_n8n_data` mounted at `/root/.n8n`.
- SQLite runtime contents and deployed database state are **UNKNOWN** and were not accessed.

## Development Boundaries

- n8n owns workflow orchestration and service credentials.
- Supabase stores job metadata and state.
- The TTS container owns local speech synthesis.
- The video-tools container/runtime owns FFmpeg rendering and filesystem paths.
- The documented frontend boundary is external to this repository.
- ClipCraft AI is permanently local-development unless explicitly changed by the project owner. No production or deployment environment is assumed.

## Known Limitations

- No frontend implementation is present.
- Public webhook authentication is not consistently demonstrated; WF15 has an internal API-key check, while WF01/WF02 appear unauthenticated in source.
- RLS is enabled, but no policies were found in the primary migration.
- The canonical source, legacy trees, and backups are not clearly separated by an authoritative deployment manifest; the repository remains the engineering source of truth.
- Current source WF17/WF18 JSON conflicts with the handoff's description of live remediation.

## Unknowns

- Exact intended users and product ownership model.
- Canonical deployment directory between `clipcraft/`, `n8n-video-factory/`, and `n8n-video-factory-v1/`.
- Local n8n workflow IDs and activation state.
- Local-development Supabase schema and migration status.
- Local n8n Public API key configuration.
- Frontend repository and authentication UX.
- CI/CD, monitoring, alerting, backup restoration, and production rollback process.
- Whether any credentials have previously been exposed outside ignored `.env` files.
