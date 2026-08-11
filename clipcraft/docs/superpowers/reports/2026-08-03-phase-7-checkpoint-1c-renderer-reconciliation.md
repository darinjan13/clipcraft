# Phase 7 Checkpoint 1C: Renderer Deployment Reconciliation

## Final Status

**RENDERER_RECONCILED**

No video job was created, claimed, retried, or generated.

## Root Cause

The renderer drift had two independent parts:

- **Workflow drift:** repository WF09 and the deployed live WF09 both used
  `http://127.0.0.1:8088/render`. In the n8n container, that address is not the
  separate renderer service.
- **Deployment drift:** the running renderer used the mutable
  `clipcraft-n8n-debug:latest` image, while Compose declared the pinned
  `clipcraft-n8n-debug:2.29.7-clipcraft-0.1.0` image.

There was no evidence requiring a renderer API, payload, FFmpeg, manifest, or
provider change. The observed state is consistent with a stale workflow
deployment plus a stale manually running renderer container; the exact import
or manual-change event is not recoverable from the available metadata.

## Authoritative Configuration

The single canonical renderer endpoint is:

```text
http://clipcraft-renderer:8088/render
```

Compose and the renderer network both use the service name `clipcraft-renderer`
on the `clipcraft` network. The renderer exposes port `8088` internally and
does not require a host port binding.

## Changes

- Updated only the `Execute FFmpeg` URL in repository WF09.
- Updated only the `Execute FFmpeg` URL in deployed live WF09.
- Recreated only `clipcraft-renderer` with
  `docker compose up -d --no-deps --force-recreate clipcraft-renderer`.
- Preserved renderer volumes.
- Did not recreate n8n or backend.
- Did not modify request payload, FFmpeg behavior, manifest contract, renderer
  API, provider execution, or lease behavior.

## Verification

Before:

```text
http://127.0.0.1:8088/render
```

After, in repository and live WF09:

```text
http://clipcraft-renderer:8088/render
```

Renderer deployment:

- Image: `clipcraft-n8n-debug:2.29.7-clipcraft-0.1.0`
- Image digest: `sha256:e8a489a4081c0f80a62e08e2e60c195353a46d82f7b45374177b1744308d925c`
- Renderer container is running on the `clipcraft` network with the
  `clipcraft-renderer` alias.
- Renderer health from the n8n container: HTTP `200`.
- n8n and backend container IDs/start times were unchanged.

Synthetic renderer probe:

- Existing `render-test.sh` passed.
- Three synthetic scenes rendered.
- Manifest validation passed.
- MP4: H.264 video, AAC audio, 1080x1920, 12 seconds, non-zero size.
- Thumbnail was generated and non-empty.
- Synthetic probe artifacts were removed afterward.

Tests:

- Renderer probe: passed.
- Workflow/backend Python suite: `108 passed`.
- Custom node suite: `28 passed`.
- `docker compose config --quiet`: passed.
- No frontend package exists in this repository; frontend build was not
  applicable.

## Readiness

Renderer deployment is ready for a single controlled end-to-end video after
explicit approval. This checkpoint did not create or claim a Supabase job and
did not invoke n8n provider workflows.
