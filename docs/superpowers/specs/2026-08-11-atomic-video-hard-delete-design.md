# Atomic Video Hard Delete Design

## Goal

Replace the broken completed-video deletion path with a true, irreversible hard delete. The operation removes all database records belonging exclusively to one requested video, then removes only that video's local job directory after the database transaction succeeds.

This change is intentionally limited to deletion. It does not add archive or soft-delete behavior and does not change pipeline execution.

## Root Cause

`SupabaseDatabaseClient.soft_delete_job()` currently sends `DELETE /rest/v1/video_jobs`, despite the method name and the existing `deleted_at` column. The delete cascades into `video_job_events`, whose append-only trigger rejects every delete with `video_job_events is append-only`. PostgREST returns HTTP 400 and the backend surfaces `database service returned an error`.

## Database Design

Add `public.hard_delete_video_job(p_job_id uuid)` as a `SECURITY DEFINER` function with an empty search path. Revoke execution from `PUBLIC`, `anon`, and `authenticated`; grant execution only to `service_role`.

The function performs one transaction-scoped operation:

1. Lock and confirm the requested `video_jobs` row exists.
2. Set a transaction-local authorization marker containing the canonical requested UUID.
3. Delete `video_job_events` for that UUID.
4. Delete `assets`, `scenes`, and `job_stage_runs` for that UUID in foreign-key-safe order.
5. Delete the `video_jobs` row.
6. Return whether a row was deleted.

Existing `ON DELETE CASCADE` constraints remain a final safeguard for current and future job-specific dependent records. A restrictive future dependency will fail the transaction rather than leave a partial deletion.

Update `prevent_video_job_event_mutations()` so UPDATE remains unconditionally forbidden. DELETE is permitted only when the transaction-local authorization marker exactly equals `OLD.job_id::text`. Direct event deletion, deletion for another UUID, and deletion outside the hard-delete RPC continue to raise `video_job_events is append-only`.

The marker is transaction-local and UUID-scoped, so it cannot authorize a later transaction or records belonging to another video. If any statement fails, PostgreSQL rolls back all database deletions atomically.

## Backend Design

Rename the database-client operation to reflect its behavior and call `POST /rest/v1/rpc/hard_delete_video_job` with the requested UUID. The API keeps `DELETE /api/videos/{video_id}` and its existing `{ "ok": true, "id": "..." }` success contract.

The endpoint verifies the video exists and validates the local path before invoking the RPC. An unsafe local path aborts the request before any database or filesystem mutation. After validation, the endpoint invokes the RPC and performs no filesystem mutation if the database call fails. A missing video remains HTTP 404. A database dependency failure retains the existing sanitized dependency-error response.

## Filesystem Safety

Path validation occurs before the RPC; filesystem deletion occurs only after the RPC succeeds.

Before calling `shutil.rmtree`, the backend:

1. Canonicalizes the requested UUID with `str(video_id)`.
2. Resolves the configured jobs root.
3. Resolves the candidate path formed only as `jobs_root / canonical_uuid` without following an unvalidated path into deletion.
4. Requires the resolved candidate's parent to equal the resolved jobs root.
5. Requires the resolved candidate's final name to equal the canonical UUID.
6. Requires the candidate to differ from the jobs root and its parent.
7. Rejects symlinks or resolution results that escape the jobs root or point at another job.

If validation fails, the backend rejects the operation without deleting database records or filesystem content. It must never delete the jobs root, its parent, a shared directory, or another video's files. A missing validated job directory is treated as already clean.

Because database deletion is intentionally irreversible and precedes local cleanup, an operating-system removal failure cannot roll back the database transaction. The backend reports that local cleanup failed without attempting a broader or fallback deletion.

## Testing

### Database contract

- The RPC is executable by `service_role` and unavailable to `PUBLIC`, `anon`, and `authenticated`.
- Direct UPDATE and DELETE against `video_job_events` remain blocked.
- The RPC removes the target job's events, assets, scenes, stage runs, and job row.
- Records for an unrelated video remain unchanged.
- A forced child-deletion failure rolls back the entire database operation.
- A missing UUID reports that no row was deleted without touching unrelated records.

### Backend regression tests

- A completed video with dependent records and a local directory is hard-deleted successfully.
- The backend calls the hard-delete RPC rather than issuing a direct table DELETE.
- Local deletion happens only after database success.
- Database failure leaves the local directory untouched.
- Unsafe path validation aborts before database deletion.
- A valid UUID directory under the configured jobs root is removed.
- Escaping paths, symlinks, the jobs root, its parent, shared directories, and paths for another UUID are never removed.
- A missing video returns HTTP 404.

### Disposable live verification

Create one disposable completed video containing scenes, assets, event history, stage runs, and local files. Also retain at least one unrelated control video. Delete the disposable video through the application API, then verify:

- No `video_jobs` row remains for the disposable UUID.
- No `scenes`, `assets`, `video_job_events`, or `job_stage_runs` rows remain for that UUID.
- Its local UUID job directory no longer exists.
- The unrelated control video's database records and local files remain unchanged.
- Direct event-history deletion is still rejected after the migration.

## Out of Scope

- Soft delete, archive, restore, or retention behavior.
- Bulk deletion.
- Shared-file garbage collection.
- Changes to generation, rendering, workflow, or provider functionality.
