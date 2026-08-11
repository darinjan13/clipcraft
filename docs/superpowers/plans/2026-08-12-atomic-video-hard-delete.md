# Atomic Video Hard Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement an irreversible, service-role-only video hard delete that atomically removes all job-owned database records and safely removes only the matching local UUID directory afterward.

**Architecture:** A new PostgreSQL RPC performs the database deletion in one transaction. A transaction-local marker scoped to the requested UUID lets the existing append-only trigger delete only that job's events during the RPC. The backend validates the canonical job path before the RPC, calls the RPC, revalidates immediately before `rmtree`, and never uses fallback filesystem paths.

**Tech Stack:** PostgreSQL/Supabase Data API, PL/pgSQL, FastAPI, httpx, pathlib, pytest.

---

This workspace is not a Git repository, so commit steps are intentionally omitted.

### Task 1: Database Hard-Delete Contract

**Files:**
- Create: `clipcraft/supabase/migrations/20260812120000_atomic_video_hard_delete.sql`
- Create: `clipcraft/tests/test_atomic_video_hard_delete_contract.py`

- [ ] **Step 1: Write failing migration contract tests**

Create tests that load the migration and assert it defines `hard_delete_video_job(uuid)`, uses `SECURITY DEFINER` with an empty search path, locks the job, sets a transaction-local UUID marker, deletes events/assets/scenes/stage runs and the parent job, keeps the event mutation trigger, and grants only `service_role` execution. Assert the trigger compares the marker to `OLD.job_id` and still raises for all unauthorized UPDATE/DELETE operations.

- [ ] **Step 2: Run the contract tests and verify RED**

Run: `pytest -q tests/test_atomic_video_hard_delete_contract.py`

Working directory: `clipcraft`

Expected: FAIL because the migration does not exist.

- [ ] **Step 3: Add the minimal migration**

Implement:

```sql
create or replace function public.prevent_video_job_event_mutations()
returns trigger
language plpgsql
security definer set search_path = ''
as $$
begin
  if tg_op = 'DELETE'
     and current_setting('clipcraft.hard_delete_job_id', true) = old.job_id::text then
    return old;
  end if;
  raise exception 'video_job_events is append-only';
end;
$$;

create or replace function public.hard_delete_video_job(p_job_id uuid)
returns boolean
language plpgsql
security definer set search_path = ''
as $$
begin
  perform 1 from public.video_jobs where id = p_job_id for update;
  if not found then
    return false;
  end if;

  perform set_config('clipcraft.hard_delete_job_id', p_job_id::text, true);
  delete from public.video_job_events where job_id = p_job_id;
  delete from public.assets where job_id = p_job_id;
  delete from public.scenes where job_id = p_job_id;
  delete from public.job_stage_runs where job_id = p_job_id;
  delete from public.video_jobs where id = p_job_id;
  return found;
end;
$$;

revoke all on function public.hard_delete_video_job(uuid) from public, anon, authenticated;
grant execute on function public.hard_delete_video_job(uuid) to service_role;
```

Recreate the existing `video_job_events_append_only` trigger explicitly so the migration remains correct if an environment has drifted.

- [ ] **Step 4: Run the contract tests and verify GREEN**

Run: `pytest -q tests/test_atomic_video_hard_delete_contract.py`

Expected: all tests pass.

### Task 2: Backend RPC Client

**Files:**
- Modify: `backend/app/clients.py:158-162`
- Create: `backend/tests/test_database_hard_delete.py`

- [ ] **Step 1: Write a failing client request test**

Monkeypatch `httpx.request`, call `DatabaseClient(settings).hard_delete_job(video_id)`, and assert:

```python
assert captured["method"] == "POST"
assert captured["url"].endswith("/rest/v1/rpc/hard_delete_video_job")
assert captured["json"] == {"p_job_id": str(video_id)}
assert result is True
```

Also assert a false scalar RPC response returns `False`.

- [ ] **Step 2: Run the client tests and verify RED**

Run: `pytest -q tests/test_database_hard_delete.py`

Working directory: `backend`

Expected: FAIL because `hard_delete_job` does not exist.

- [ ] **Step 3: Replace the direct DELETE with the RPC call**

Implement in `DatabaseClient`:

```python
def hard_delete_job(self, job_id: UUID) -> bool:
    result = self._write_request(
        "POST",
        "/rest/v1/rpc/hard_delete_video_job",
        json_data={"p_job_id": str(job_id)},
    )
    return result is True
```

Remove `soft_delete_job`; do not retain a direct table-delete fallback.

- [ ] **Step 4: Run the client tests and verify GREEN**

Run: `pytest -q tests/test_database_hard_delete.py`

Expected: all tests pass.

### Task 3: Safe Endpoint Filesystem Cleanup

**Files:**
- Modify: `backend/app/main.py:60-65,897-910`
- Modify: `backend/tests/test_api.py:45-86,893-922`

- [ ] **Step 1: Update the fake database and write failing endpoint tests**

Change the fake to expose `hard_delete_job()` and record that it was called. Add tests proving:

- The target database row disappears and only `root/<requested UUID>` is removed.
- Database failure leaves the local directory intact.
- A symlink at the target UUID is rejected before database mutation.
- A second validation immediately before removal prevents a path changed after RPC success from being removed.
- Missing videos return 404.
- A missing target directory is a successful no-op after database deletion.
- A sibling UUID directory and a shared root file remain untouched.

- [ ] **Step 2: Run endpoint tests and verify RED**

Run: `pytest -q tests/test_api.py -k "delete_video"`

Working directory: `backend`

Expected: FAIL because the endpoint still calls `soft_delete_job` and has no strict path validation.

- [ ] **Step 3: Implement one focused path validator**

Add a private helper that accepts only a canonical UUID child of the resolved jobs root:

```python
def _safe_job_directory(root: Path, video_id: UUID) -> Path:
    resolved_root = root.resolve()
    candidate = resolved_root / str(video_id)
    if candidate.is_symlink():
        raise ValueError("unsafe video job directory")
    resolved_candidate = candidate.resolve()
    if (
        resolved_candidate == resolved_root
        or resolved_candidate == resolved_root.parent
        or resolved_candidate.parent != resolved_root
        or resolved_candidate.name != str(video_id)
    ):
        raise ValueError("unsafe video job directory")
    return resolved_candidate
```

The UUID type prevents caller-controlled path segments. Resolving and checking the leaf rejects links that escape or alias another directory.

- [ ] **Step 4: Update the endpoint in the required order**

Use this sequence:

```python
row = database.get_job(video_id)
if not row:
    raise HTTPException(status_code=404, detail="video not found")
try:
    _safe_job_directory(root, video_id)
except ValueError as exc:
    raise HTTPException(status_code=500, detail="unsafe video job directory") from exc
if not database.hard_delete_job(video_id):
    raise HTTPException(status_code=404, detail="video not found")
job_dir = _safe_job_directory(root, video_id)
if job_dir.exists():
    shutil.rmtree(job_dir)
return {"ok": True, "id": str(video_id)}
```

Import `shutil` at module scope. Do not add fallback deletion, soft delete, archive behavior, or cleanup outside this UUID directory.

- [ ] **Step 5: Run endpoint and backend tests**

Run: `pytest -q tests/test_api.py -k "delete_video"`

Expected: all delete tests pass.

Run: `pytest -q`

Expected: the full backend suite passes.

### Task 4: Deploy and Verify the Database Contract

**Files:**
- Use: `clipcraft/supabase/migrations/20260812120000_atomic_video_hard_delete.sql`

- [ ] **Step 1: Apply the reviewed migration**

Apply the exact migration through Supabase migration tooling under the name `atomic_video_hard_delete`.

- [ ] **Step 2: Verify privileges and direct append-only protection**

Query `information_schema.routine_privileges` to confirm only `service_role` has RPC execution among API roles. In a transaction that is rolled back, attempt direct event UPDATE and DELETE and assert both raise `video_job_events is append-only`.

- [ ] **Step 3: Run Supabase advisors**

Run security and performance advisors. Record only findings caused by this migration; do not modify unrelated schema.

### Task 5: Disposable End-to-End Hard Delete

**Files:**
- No persistent files.

- [ ] **Step 1: Create isolated target and control fixtures**

Generate two UUIDs. Insert completed `video_jobs` rows for both. For each UUID insert one scene, one image asset, one event, and one succeeded stage run using valid current-schema values. Create `root/<uuid>/final.mp4` for both through the mounted jobs volume used by the backend.

- [ ] **Step 2: Capture pre-delete evidence**

Query counts for `video_jobs`, `scenes`, `assets`, `video_job_events`, and `job_stage_runs` for both UUIDs. Verify both local files exist.

- [ ] **Step 3: Delete only the target through the application API**

Call `DELETE /api/videos/<target UUID>` and require HTTP 200 with `{ "ok": true, "id": "<target UUID>" }`.

- [ ] **Step 4: Verify complete target removal and control isolation**

Query all five tables and require zero target rows. Require all control counts to equal their pre-delete counts. Verify the target directory is absent and the control directory/file remains.

- [ ] **Step 5: Reverify append-only protection**

Attempt direct deletion of the control event outside the RPC and require `video_job_events is append-only`.

- [ ] **Step 6: Remove the disposable control through the approved path**

Delete the control through the same API and verify its database rows and UUID directory are gone. Do not touch existing user videos.

- [ ] **Step 7: Final regression verification**

Run: `pytest -q`

Working directory: `backend`

Expected: all tests pass.

Run: `pytest -q tests/test_atomic_video_hard_delete_contract.py`

Working directory: `clipcraft`

Expected: all tests pass.
