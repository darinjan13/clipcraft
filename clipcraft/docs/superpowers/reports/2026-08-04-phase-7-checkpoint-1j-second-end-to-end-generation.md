# Phase 7 Checkpoint 1J: Second End-to-End Production Generation

## Final Status

**SECOND_GENERATION_FAILED**

Exactly one new production test job was created. The pipeline progressed through
job creation, fenced claim, lease acquisition, WF04, and WF17, then stopped at
the first new blocker in WF04 failure finalization. No retry, second job, or
cancelled-job reuse was performed.

## Pre-Flight

Passed before job creation:

- Backend: healthy
- Renderer: healthy and reachable at `http://clipcraft-renderer:8088/render`
- n8n: healthy
- TTS: healthy
- Active jobs: `0`
- Active leases: `0`
- Workflow count: `15`, all active
- Credential count: `1`, internal credential present
- Custom text node: loaded
- Custom image node: loaded
- `TEXT_EXECUTION_MODE=internal`
- `IMAGE_EXECUTION_MODE=internal`
- Text provider: Cloudflare
- Image provider: Cloudflare

## Job

- Job ID: `1de38bd2-43e4-47c8-bcaf-0e4911425214`
- Create response: HTTP `202`
- Create execution: `35423`, success
- Topic: How bees help plants grow
- Duration: 30 seconds
- Scenes requested: 6
- Initial status: `queued`

## Lease And Claim

WF03 execution `35424` successfully used the fenced claim path.

- Lease token: present, UUID-shaped
- Lease duration: 120 seconds
- Attempt number: `1`
- Pipeline revision: `1`
- Claimed worker: `clipcraft-n8n`
- Next stage: `generate_script`
- Lease expiry: `2026-08-03T20:18:59.00545+00:00`
- Active lease at evidence capture: yes

The canonical WF03 normalization output preserved the complete lease context.

## Execution Timeline

1. WF02 `35423` created the job successfully.
2. WF03 `35424` claimed the job with the fenced lease contract.
3. WF04 `35425` started and completed prompt construction.
4. WF17 `35426` executed in internal mode.
5. WF17 returned a normalized non-retryable request-validation failure.
6. WF04 stopped at `Finalize Provider Failure` with `Bad request - please check your parameters`.
7. No WF05 or WF18 execution started.

## Exact Blocker

WF17 node: `Prepare Internal Request`

The node produced:

```text
jobId: valid production job UUID
requestId: unknown-request
providerId: cloudflare
modelId: @cf/meta/llama-3.1-8b-instruct
credentialSource: environment
routingVersion: 1
responseFormat: text
```

The `requestId` was lost because `Prepare Internal Request` reads the original
`Workflow Trigger` object rather than the authoritative `Prepare Provider
Attempt` output, where WF17 generated the valid request UUID
`f59c6c2f-95d0-4faf-9479-390587b885fa`.

The backend rejected the malformed internal request with:

- HTTP `422`
- Safe code: `AI_REQUEST_INVALID`
- Safe message: `request is invalid`
- Retryable: `false`

WF17 normalized this without retrying. WF04 then failed at `Finalize Provider
Failure` because its failure-finalization request was rejected.

## Pipeline Results

| Stage | Result |
| --- | --- |
| Job creation | Passed |
| Fenced claim | Passed |
| Lease | Passed |
| WF04 dispatch | Passed |
| WF17 internal branch | Passed |
| Internal text request construction | Failed: invalid request ID |
| Internal text execution | Rejected by backend validation |
| Structured output | Not reached |
| Word-count validation | Not reached |
| Scene persistence | Not reached |
| WF05 | Not reached |
| WF18 | Not reached |

## Provider And Media Results

- Internal provider branch selected: yes
- Legacy branch executed: no
- Cloudflare provider call: `0`; backend rejected the request before provider execution
- Successful text result: no
- Duplicate provider calls: none
- Image calls: none
- TTS: not reached
- Captions: not reached
- Manifest: not reached
- Renderer: not reached
- Thumbnail/preview/MP4: not reached

## Job Preservation

The failed production job was left intact according to the checkpoint failure
policy. No cancellation, retry, lease-clearing mutation, or second job was
performed after the blocker was identified.

At evidence capture:

- Status: `generating_script`
- Current step: `generate_script`
- Progress: `5`
- Script persisted: no
- Lease: still present with the captured expiry

## Tests And Reviews

The checkpoint stopped immediately at the first new production blocker. The
requested post-run workflow, backend, custom-node, frontend, compatibility, and
security checks were not run after this failed production attempt.

Previously verified before the attempt:

- ClipCraft workflow suite: `129 passed`
- Custom-node suite: `29 passed`
- Frontend production build: passed
- Docker Compose validation: passed
- Focused WF02/WF03/WF17 tests: passed

The known unrelated backend suite issue remains: one test references the
missing `clipcraft/supabase/migrations/009_video_job_configuration_snapshots.sql`.

## Compatibility And Security Review

No architecture, provider mode, claim contract, lease contract, WF04 business
logic, renderer, TTS, database schema, or frontend change was made during this
checkpoint. No provider credential or raw provider response was needed for the
failed request path. The malformed request ID was the only new blocker observed.

## Remaining Issues

- Reconcile WF17 `Prepare Internal Request` to consume the authoritative
  `Prepare Provider Attempt` request context.
- Verify WF04 failure finalization after that correction.
- Do not retry this job.
- Do not create another production job until the WF17 context fix is explicitly
  approved and verified.

## Production Readiness

The second end-to-end generation did not reach structured text output, scene
persistence, WF05, or WF18. The pipeline remains **not ready** for a complete
production generation.

## Checkpoint 1L Pre-Flight Follow-Up

On 2026-08-04, Checkpoint 1L was authorized to create exactly one new
production test job. The mandatory pre-flight stopped before job creation:

- The job remains `generating_script` at `generate_script`, progress `5`.
- The job still has retained claim/lease context in Supabase.
- No cancellation, retry, lease clearing, deletion, or other mutation was
  performed.
- No new production job was created.

This is a pre-flight state observation, not a new mutation of the Checkpoint 1J
job. Checkpoint 1L is blocked until the existing non-terminal job and lease
state are resolved under an explicitly authorized policy.
