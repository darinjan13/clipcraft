from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "supabase/migrations/20260812120000_atomic_video_hard_delete.sql"
)


def migration_text() -> str:
    return " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())


def test_hard_delete_rpc_is_atomic_uuid_scoped_and_service_role_only():
    sql = migration_text()

    assert "function public.hard_delete_video_job(p_job_id uuid)" in sql
    assert "security definer set search_path = ''" in sql
    assert "from public.video_jobs where id = p_job_id for update" in sql
    assert "set_config('clipcraft.hard_delete_job_id', p_job_id::text, true)" in sql
    for table in (
        "video_job_events",
        "assets",
        "scenes",
        "job_stage_runs",
    ):
        assert f"delete from public.{table} where job_id = p_job_id" in sql
    assert "delete from public.video_jobs where id = p_job_id" in sql
    assert "to_regclass('public.regeneration_operations')" in sql
    assert "delete from public.regeneration_operations where job_id = $1" in sql
    assert "revoke all on function public.hard_delete_video_job(uuid) from public, anon, authenticated" in sql
    assert "grant execute on function public.hard_delete_video_job(uuid) to service_role" in sql


def test_event_history_deletion_requires_matching_rpc_marker():
    sql = migration_text()

    assert "tg_op = 'delete'" in sql
    assert "current_setting('clipcraft.hard_delete_job_id', true) = old.job_id::text" in sql
    assert "raise exception 'video_job_events is append-only'" in sql
    assert "before update or delete on public.video_job_events" in sql
    assert "revoke all on function public.prevent_video_job_event_mutations() from public, anon, authenticated" in sql
