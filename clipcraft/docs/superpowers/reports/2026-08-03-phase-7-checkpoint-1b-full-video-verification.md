# Phase 7 Checkpoint 1B: Full Video Verification

## Final Status

**FULL_VIDEO_FAILED_RENDER**

The checkpoint stopped during pre-flight. No test video was created, no job was
claimed, and no provider or media pipeline execution was started.

## Pre-Flight Results

Passed:

- `TEXT_EXECUTION_MODE=internal`.
- `IMAGE_EXECUTION_MODE=internal`.
- No running n8n executions.
- Supabase lease state: `43` total jobs, `0` active jobs, `0` active leases.
- Known cancelled job remains cancelled.
- n8n container healthy.
- Backend health from the n8n network: HTTP `200`.
- Renderer health from the n8n network: HTTP `200`.
- TTS health from the n8n network: HTTP `200`.
- WF03, WF04, WF05, WF06, WF07, WF08, WF09, WF17, and WF18 are active.
- The `ClipCraft Internal API` credential exists.
- The custom node bundle is present in the n8n container.
- Live WF03 claim normalization is connected and accepts the nested fenced
  response, preserving `leaseToken`, `attemptNumber`, `pipelineRevision`, and
  `leaseExpiresAt`.

## Hard Stop

Live WF09 currently sends the renderer request to:

```text
http://127.0.0.1:8088/render
```

The renderer is a separate `clipcraft-renderer` container on the `clipcraft`
network. The live request must use the service address before any video job is
created. The running renderer image is also
`clipcraft-n8n-debug:latest`, while the Compose-declared image is
`clipcraft-n8n-debug:2.29.7-clipcraft-0.1.0`; this runtime drift must be
resolved or explicitly accepted before retrying the checkpoint.

Because the renderer contract failed pre-flight, the test stopped before Phase
B. No lease token, attempt number, pipeline revision, provider call, execution
ID, asset, MP4, thumbnail, or job ID exists for this checkpoint.

## Scope Boundary

No workflow, provider mode, migration, database data, Docker configuration,
credential, or legacy branch was modified. No second job, cancelled-job retry,
or end-to-end generation was attempted.
