# WF17/WF18 Explicit Retry-State Repair

## Current Defect

The existing `Check Retry` code calls `$('Retry').all()`. `Retry` is a
conditional node later in the same path and has not executed on the first
provider attempt. n8n therefore raises `Node 'Retry' hasn't been executed`,
preventing successful provider responses from reaching `Normalize Response`.

## Explicit State Design

The current item carries `retryCount` through every provider attempt. A
`Prepare Provider Attempt` code node normalizes the initial value to `0` and
preserves it on loop re-entry. `Evaluate Provider Result` reads the current
attempt's state from the already-executed `Prepare Provider Attempt` node and
returns `retryCount`, `shouldRetry`, `retryExhausted`, and sanitized provider
error metadata. It never reads a future or conditionally unexecuted node.

`Increment Retry` copies the current provider request item and sets
`retryCount + 1`. The loop therefore has exactly three possible provider
attempts: initial attempt at `0`, retry one at `1`, and retry two at `2`.

Exhaustion is distinct from non-retryable failure:

```text
retryExhausted = !providerSuccess && retryableProvider && retryCount >= 2
```

A non-retryable failure never becomes `RETRY_EXHAUSTED`; it remains a
`PROVIDER_ERROR` with no retry increment.

## Topology

```text
Build Request -> Validate Input
  false -> Handle Validation Error -> Normalize Response
  true -> Prepare Provider Attempt -> Call Provider API
       -> Evaluate Provider Result -> Retryable Failure?
          true -> Increment Retry -> Prepare Provider Attempt
          false -> Normalize Response
```

Provider success and terminal provider failure both use the false branch of
`Retryable Failure?`, so `Normalize Response` executes exactly once. The retry
decision is item data, not execution history, node-run counts, static data, or
item indexes.

## WF18 Context

WF18 retains `context.jobId`, `context.sceneId`, and `context.sceneIndex` in
the trigger-derived normalized output. The retry item preserves the provider
request and retry counter without exposing credentials or raw headers in the
normalized response.
