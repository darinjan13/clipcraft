import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "clipcraft" / "supabase" / "migrations_archive" / "004_core_backend_foundation.sql"
EVENTS_MIGRATION = ROOT / "clipcraft" / "supabase" / "migrations_archive" / "005_video_job_events.sql"
RUNNER = ROOT / "clipcraft" / "supabase" / "run-migrations.sh"
VERIFY = ROOT / "clipcraft" / "supabase" / "migrations" / "verify-migrations.sql"
RECONCILIATION = ROOT / "clipcraft" / "supabase" / "migrations" / "20260802140000_reconcile_job_leases_and_claim_contract.sql"
RECONCILIATION_DOWN = ROOT / "clipcraft" / "supabase" / "migrations_rollback" / "20260802140000_reconcile_job_leases_and_claim_contract.down.sql"
CHECKPOINT_1B = ROOT / "clipcraft" / "supabase" / "migrations" / "20260803120000_checkpoint_1b_lease_safety_rpcs.sql"
CHECKPOINT_1B_DOWN = ROOT / "clipcraft" / "supabase" / "migrations_rollback" / "20260803120000_checkpoint_1b_lease_safety_rpcs.down.sql"
LEGACY_CLAIM_ACL = ROOT / "clipcraft" / "supabase" / "migrations" / "20260803140000_restrict_legacy_claim_rpc_acl.sql"


def migration_text():
    return MIGRATION.read_text(encoding="utf-8").lower()


def events_migration_text():
    assert EVENTS_MIGRATION.is_file(), "missing migration 005_video_job_events.sql"
    return EVENTS_MIGRATION.read_text(encoding="utf-8").lower()


def reconciliation_text():
    assert RECONCILIATION.is_file(), "missing lease reconciliation migration"
    return RECONCILIATION.read_text(encoding="utf-8").lower()


def test_lease_reconciliation_is_additive_and_uses_a_distinct_claim_rpc():
    sql = reconciliation_text()
    assert "add column if not exists lease_token uuid" in sql
    assert "add column if not exists attempt_number integer" in sql
    assert "claim_next_video_job_fenced" in sql
    assert "for update skip locked" in sql
    assert "returns jsonb" in sql
    assert "job_stage_runs" in sql
    assert "create or replace function public.claim_next_video_job(" not in sql
    assert "update public.video_jobs" not in sql.split("create or replace function public.claim_next_video_job_fenced", 1)[0]
    assert "revoke all on function public.claim_next_video_job(text)" not in sql


def test_lease_reconciliation_has_a_companion_rollback():
    assert RECONCILIATION_DOWN.is_file(), "missing lease reconciliation rollback migration"
    sql = RECONCILIATION_DOWN.read_text(encoding="utf-8").lower()
    assert "drop function if exists public.claim_next_video_job_fenced" in sql
    assert "drop table if exists public.job_stage_runs" in sql
    assert "drop column if exists lease_token" in sql
    assert "drop column if exists pipeline_revision" in sql
    assert "revoke all on function public.claim_next_video_job(text)" not in sql


def test_legacy_claim_is_worker_only_while_service_role_compatibility_remains():
    assert LEGACY_CLAIM_ACL.is_file(), "missing legacy claim ACL reconciliation migration"
    sql = " ".join(LEGACY_CLAIM_ACL.read_text(encoding="utf-8").lower().split())
    assert "revoke all on function public.claim_next_video_job(text) from public, anon, authenticated" in sql
    assert "grant execute on function public.claim_next_video_job(text) to service_role" in sql


def test_checkpoint_1b_declares_bounded_lease_safety_contract():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    assert "add column if not exists max_job_attempts integer" in sql
    assert "reap_expired_video_job_leases" in sql
    assert "release_video_job" in sql
    assert "lease_expired_max_attempts" in sql
    assert "for update skip locked" in sql
    assert "revoke all on function public.reap_expired_video_job_leases" in sql
    assert "revoke all on function public.release_video_job" in sql
    assert "create or replace function public.claim_next_video_job(" not in sql


def test_checkpoint_1b_has_forward_only_invariants_and_guarded_rollback():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    down = CHECKPOINT_1B_DOWN.read_text(encoding="utf-8").lower()
    assert "default 3" in sql
    assert "not valid" in sql
    assert "active_fenced_leases_exist" in down
    assert "drop function if exists public.reap_expired_video_job_leases" in down
    assert "drop function if exists public.release_video_job" in down
    assert "drop column if exists max_job_attempts" in down


def test_checkpoint_1b_rejects_null_batch_and_normalizes_legacy_reaper_values():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    reaper = sql_definition(sql, r"function public\.reap_expired_video_job_leases\s*\(")
    assert re.search(r"if\s+p_batch_size\s+is\s+null", reaper)
    assert "raise exception 'invalid_batch_size'" in reaper
    assert re.search(r"max_job_attempts\s*=\s*coalesce\(job\.max_job_attempts\s*,\s*3\)", reaper)
    assert re.search(r"pipeline_revision\s*=\s*coalesce\(job\.pipeline_revision\s*,\s*1\)", reaper)
    assert re.search(r"attempt_number\s*=\s*next_attempt", reaper)


def test_checkpoint_1b_release_is_null_safe_and_token_first():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    release = sql_definition(sql, r"function public\.release_video_job\s*\(")
    assert re.search(r"if\s+p_outcome\s+is\s+null\s+or\s+p_outcome\s+not\s+in", release)
    assert re.search(r"p_outcome\s*=\s*'completed_stage'\s+and\s+p_next_stage\s+is\s+null", release)
    token_check = re.search(r"if\s+p_lease_token\s+is\s+null.*?end if;", release, re.DOTALL)
    terminal_check = re.search(r"if\s+job\.status\s+in\s*\(", release)
    outcome_check = re.search(r"if\s+p_outcome\s+is\s+null\s+or\s+p_outcome\s+not\s+in", release)
    assert (
        token_check
        and terminal_check
        and outcome_check
        and token_check.start() < terminal_check.start() < outcome_check.start()
    )


def test_checkpoint_1b_forward_checks_reject_future_nulls():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    assert "check (attempt_number is not null and attempt_number >= 0) not valid" in sql
    assert "check (pipeline_revision is not null and pipeline_revision >= 1) not valid" in sql
    assert "check (max_job_attempts is not null and max_job_attempts >= 1) not valid" in sql


def test_checkpoint_1b_claim_enforces_threshold_and_normalizes_legacy_limits():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    claim = sql_definition(sql, r"function public\.claim_next_video_job_fenced\s*\(")
    assert re.search(r"next_attempt\s+>=\s+coalesce\(claimed_job\.max_job_attempts\s*,\s*3\)", claim)
    assert claim.count("max_job_attempts = coalesce(claimed_job.max_job_attempts, 3)") == 2
    assert "attempt_number = next_attempt + 1" in claim
    assert "pipeline_revision = coalesce(pipeline_revision, 1)" in claim


def test_checkpoint_1b_release_preserves_explicit_stage_contract():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    release = sql_definition(sql, r"function public\.release_video_job\s*\(")
    for stage in (
        "generate_script", "generate_images", "generate_voice", "build_captions",
        "build_manifest", "render", "completed",
    ):
        assert f"'{stage}'" in release
    assert "last_completed_stage = prior_stage" in release
    assert "next_stage = p_next_stage" in release
    assert "current_step = p_next_stage" in release
    assert "status = case when p_next_stage = 'completed' then 'completed' else 'queued' end" in release
    assert "current_step = coalesce(job.next_stage, job.current_step)" in release


def test_checkpoint_1b_preserves_legacy_claim_and_grants():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    down = CHECKPOINT_1B_DOWN.read_text(encoding="utf-8").lower()
    archived = (ROOT / "clipcraft" / "supabase" / "migrations_archive" / "004_core_backend_foundation.sql").read_text(encoding="utf-8").lower()
    assert "create or replace function public.claim_next_video_job(" not in sql
    assert "revoke all on function public.claim_next_video_job(text)" not in sql
    assert "drop function if exists public.claim_next_video_job(text)" not in down
    assert "revoke all on function public.claim_next_video_job(text)" not in down
    assert "grant execute on function public.claim_next_video_job(text, integer) to service_role" in archived


def test_checkpoint_1b_rollback_restores_exact_checkpoint_1a_claim():
    one_a = reconciliation_text()
    down = CHECKPOINT_1B_DOWN.read_text(encoding="utf-8").lower()
    assert sql_definition(one_a, r"function public\.claim_next_video_job_fenced\s*\(") == sql_definition(
        down, r"function public\.claim_next_video_job_fenced\s*\("
    )
    assert "grant execute on function public.claim_next_video_job_fenced(text, integer) to service_role" in down
    assert "begin;" in down
    assert "lock table public.video_jobs in access exclusive mode" in down
    assert "commit;" in down
    assert "alter column attempt_number drop default" in down
    assert "alter column pipeline_revision drop default" in down
    assert "drop column if exists lease_token" not in down
    assert "drop table if exists public.job_stage_runs" not in down


def test_checkpoint_1b_reaper_and_release_contract_details():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    reaper = sql_definition(sql, r"function public\.reap_expired_video_job_leases\s*\(")
    release = sql_definition(sql, r"function public\.release_video_job\s*\(")
    assert "limit greatest(1, least(p_batch_size, 1000))" in reaper
    assert "grant execute on function public.reap_expired_video_job_leases(integer) to service_role" in sql
    for field in ("claimed_by", "claimed_at", "lease_token", "lease_expires_at", "heartbeat_at"):
        assert reaper.count(f"{field} = null") >= 2
    assert "status = 'failed'" in reaper
    assert "failure_class = 'lease_expired_max_attempts'" in reaper
    assert "status = 'queued'" in reaper
    assert "current_step = coalesce(job.next_stage, job.current_step, 'queued')" in reaper
    assert re.search(
        r"release_video_job\(\s*p_job_id uuid,\s*p_lease_token uuid,\s*p_outcome text,\s*p_next_stage text default null",
        sql,
        re.DOTALL,
    )
    assert "job.lease_token is distinct from p_lease_token" in release
    for stage in (
        "generate_script", "generate_images", "generate_voice", "build_captions",
        "build_manifest", "render", "completed",
    ):
        assert f"'{stage}'" in release
    assert "status = case when p_next_stage = 'completed' then 'completed' else 'queued' end" in release
    assert "last_completed_stage = prior_stage" in release
    assert "current_step = coalesce(job.next_stage, job.current_step)" in release
    assert "attempt_number = coalesce(job.attempt_number, 0)" in release
    assert "pipeline_revision = coalesce(job.pipeline_revision, 1)" in release
    assert "max_job_attempts = coalesce(job.max_job_attempts, 3)" in release
    assert "job.lease_expires_at <= now()" in release
    assert "raise exception 'lease_lost'" in release
    assert "attempt_number = coalesce(job.attempt_number, 0)" in release
    assert "pipeline_revision = coalesce(job.pipeline_revision, 1)" in release
    assert "max_job_attempts = coalesce(job.max_job_attempts, 3)" in release


def test_checkpoint_1b_claim_contract_details():
    sql = CHECKPOINT_1B.read_text(encoding="utf-8").lower()
    claim = sql_definition(sql, r"function public\.claim_next_video_job_fenced\s*\(")
    assert "next_attempt >= coalesce(claimed_job.max_job_attempts, 3)" in claim
    assert "status = 'failed'" in claim
    assert "failure_class = 'lease_expired_max_attempts'" in claim
    assert "'claimed', false" in claim
    assert "'failure_class', 'lease_expired_max_attempts'" in claim
    assert "attempt_number = next_attempt + 1" in claim
    assert "pipeline_revision = coalesce(pipeline_revision, 1)" in claim
    assert "max_job_attempts = coalesce(claimed_job.max_job_attempts, 3)" in claim
    assert "next_stage = claim_stage" in claim
    assert "to_jsonb(claimed_job)" not in claim
    for field in (
        "id", "topic", "status", "progress", "current_step", "brief_json",
        "script_json", "render_manifest", "output_url", "thumbnail_url",
        "retry_count", "max_retries", "claimed_by", "claimed_at", "lease_token",
        "lease_expires_at", "heartbeat_at", "attempt_number", "max_job_attempts",
        "pipeline_revision", "next_stage", "last_completed_stage", "failure_class",
    ):
        assert f"'{field}', claimed_job.{field}" in claim


def test_checkpoint_1b_ephemeral_harness_is_reproducible_and_isolated():
    harness = ROOT / "clipcraft" / "tests" / "test_checkpoint_1b_ephemeral.ps1"
    assert harness.is_file(), "missing Checkpoint 1B ephemeral validation harness"
    script = harness.read_text(encoding="utf-8").lower()
    executable = "\n".join(
        line for line in script.splitlines()
        if not line.strip().startswith("#")
    )
    for required in (
        "postgres:17", "docker run", "docker rm", "finally", "pg_isready",
        "001_create_all_tables.sql", "002_add_job_claiming.sql", "003_asset_path_functions.sql",
        "20260727134852_simple_processing_lifecycle.sql", "006_add_soft_delete.sql",
        "20260802140000_reconcile_job_leases_and_claim_contract.sql",
        "20260803120000_checkpoint_1b_lease_safety_rpcs.sql",
        "active_fenced_leases_exist", "lease_expired_max_attempts", "service_role",
        "claim_next_video_job(text)", "release_video_job", "reap_expired_video_job_leases",
        "exit 1", "$connectionhost = '127.0.0.1'", "docker container inspect",
        "$removeexit", "lease_expires_at", "heartbeat_at", "last_completed_stage",
        "select 1", "start-sleep", "$connectiontarget", "$connectionport",
        "$databasename", "$connectiontarget.container", "invalid disposable connection target",
        "video_jobs_fenced_queue_idx", "video_jobs_fenced_lease_idx", "job_stage_runs",
        "heartbeat_video_job", "pg_constraint", "pg_indexes", "has_function_privilege",
        "attempt_number", "pipeline_revision", "max_job_attempts", "progress",
        "failure_class", "error_message", "finished_at", "updated_at",
        "priority", "created_at", "last_error", "cancel_requested", "completed_at",
        "deleted_at", "information_schema.columns", "legacy nullable release",
        "function get-jobstatesnapshot", "assert-jobstateequal", "assert-leasecleared",
        "invalid_lease_seconds", "invalid_batch_size", "job_terminal", "invalid_next_stage",
        "start-job", "wait-job", "receive-job", "remove-job", "concurrent reaper",
        "reaped_count", "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
        "barrierjob", "pg_locks", "accessexclusivelock", "lock table public.video_jobs",
        "future forward checks reject null and invalid values",
        "expired release rejects token and preserves state",
    ):
        assert required in script
    assert "supabase.co" not in executable
    assert "-h $connectiontarget.host" in executable
    assert "if ($connectiontarget.host -notin @('127.0.0.1', 'localhost'))" in executable
    assert "if ($connectiontarget.database -ne $databasename)" in executable
    assert "if ($connectiontarget.container -ne $container)" in executable


def sql_definition(sql, object_pattern):
    match = re.search(object_pattern + r".*?\bas\s+\$(?:\w+)?\$(.*?)\$(?:\w+)?\$\s*;", sql, re.DOTALL)
    assert match, f"missing SQL definition matching {object_pattern}"
    return match.group(1)


def table_definition(sql, table_name):
    match = re.search(
        rf"create table(?: if not exists)? public\.{table_name}\s*\((.*?)\)\s*;",
        sql,
        re.DOTALL,
    )
    assert match, f"migration must create public.{table_name}"
    return match.group(1)


def table_columns(table_sql):
    parts = []
    start = 0
    depth = 0
    for index, character in enumerate(table_sql):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            parts.append(table_sql[start:index])
            start = index + 1
    parts.append(table_sql[start:])
    constraints = ("constraint", "primary", "foreign", "unique", "check", "exclude")
    return {
        part.strip().split()[0].strip('"')
        for part in parts
        if part.strip() and not part.strip().lower().startswith(constraints)
    }


def test_foundation_migration_declares_lease_and_stage_schema():
    sql = migration_text()
    assert "alter table public.video_jobs" in sql
    for field in ("lease_token", "lease_expires_at", "heartbeat_at", "attempt_number", "pipeline_revision", "next_stage"):
        assert field in sql
    assert "create table if not exists public.job_stage_runs" in sql
    assert "item_key text not null" in sql
    assert "unique (job_id, pipeline_revision, stage, item_key)" in sql
    assert "create table if not exists public.regeneration_operations" in sql


def test_migration_runner_applies_foundation_and_verifier_fails_hard():
    runner = RUNNER.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8").lower()
    assert "004_core_backend_foundation.sql" in runner
    assert "raise exception '=== verification failed ==='" in verify


def test_video_job_events_migration_declares_append_only_event_schema():
    sql = events_migration_text()
    table = table_definition(sql, "video_job_events")
    required_columns = {
        "id", "job_id", "stage", "event_type", "level", "message", "progress", "metadata", "created_at",
    }
    allowed_columns = required_columns | {"idempotency_key"}
    declared_columns = table_columns(table)
    assert required_columns <= declared_columns
    assert declared_columns <= allowed_columns, "event records must not carry mutable or canonical job-state columns"
    assert re.search(r"\bmetadata\s+jsonb\b", table)
    assert re.search(r"\bjob_id\b.*references public\.video_jobs\s*\(\s*id\s*\)", table, re.DOTALL)

    assert "alter table public.video_job_events enable row level security" in sql
    permission_statements = re.findall(r"(?:revoke|grant)\b[^;]*;", sql, re.DOTALL)
    assert any(re.search(
        r"revoke\s+(?:all|insert)[^;]*on\s+(?:table\s+)?public\.video_job_events[^;]*\b(anon|authenticated)\b",
        statement,
        re.DOTALL,
    ) for statement in permission_statements)
    assert not any(re.search(
        r"grant\s+(?:insert|update|delete|all)[^;]*on\s+(?:table\s+)?public\.video_job_events[^;]*\b(anon|authenticated)\b",
        statement,
        re.DOTALL,
    ) for statement in permission_statements)
    assert re.search(
        r"create\s+trigger\b[^;]*before\s+(?:update\s+or\s+delete|delete\s+or\s+update)"
        r"[^;]*on\s+public\.video_job_events\b[^;]*;",
        sql,
        re.DOTALL,
    ), (
        "append-only must be enforced independently of browser grants"
    )


def test_video_job_events_migration_orders_events_and_safely_deduplicates_metadata():
    sql = events_migration_text()
    index_statements = re.findall(r"create\s+(?:unique\s+)?index\b[^;]*;", sql, re.DOTALL)
    assert any(re.search(
        r"on\s+public\.video_job_events\s*(?:using\s+btree\s*)?"
        r"\(\s*job_id\s*,\s*created_at\s+desc\s*,\s*id\s+desc\s*\)",
        statement.replace('"', ""),
    ) for statement in index_statements)
    persist_body = sql_definition(sql, r"function public\.persist_video_job_failure\s*\(")
    event_table = table_definition(sql, "video_job_events")
    has_idempotency_column = "idempotency_key" in table_columns(event_table)
    unique_index = any(re.search(
        r"create\s+unique\s+index\b[^;]*on\s+public\.video_job_events\s*"
        r"\(\s*job_id\s*,\s*idempotency_key\s*\)",
        statement.replace('"', ""),
    ) for statement in index_statements)
    unique_constraint = re.search(r"unique\s*\(\s*job_id\s*,\s*idempotency_key\s*\)", event_table)
    expression_uniqueness = any(
        "unique" in statement and "idempotency" in statement
        for statement in index_statements
    )
    if has_idempotency_column:
        assert unique_index or unique_constraint
    else:
        assert expression_uniqueness or re.search(
            r"if\s+exists\s*\([^;]*public\.video_job_events[^;]*(?:idempotency|job_failed)",
            persist_body,
            re.DOTALL,
        )

    sanitizer_match = re.search(
        r"function public\.([a-z_]*metadata[a-z_]*)\s*\("
        r".*?\bas\s+\$(?:\w+)?\$(.*?)\$(?:\w+)?\$\s*;",
        sql,
        re.DOTALL,
    )
    metadata_scope = sanitizer_match.group(2) if sanitizer_match else persist_body
    assert not re.search(r"return\s+(?:coalesce\s*\(\s*)?p_metadata\b", metadata_scope), (
        "metadata must not be returned unsanitized"
    )
    safe_keys = (
        "execution_id", "stage_run_id", "attempt_number", "pipeline_revision",
        "failure_class", "retryable", "error_code", "workflow_id", "execution",
        "stage", "attempt", "code",
    )
    assert any(key in metadata_scope for key in safe_keys), "metadata needs a positive safe-key allowlist"
    for unsafe_key in ("authorization", "api_key", "service_role_key", "access_token", "prompt"):
        assert not re.search(rf"['\"]{unsafe_key}['\"]", metadata_scope)
    assert any(selector in metadata_scope for selector in (
        "jsonb_each", "jsonb_object_agg", "jsonb_build_object", "jsonb_path_query", "->",
    )), "metadata allowlisting must select approved JSON keys"
    if sanitizer_match:
        assert sanitizer_match.group(1) in persist_body
    else:
        event_insert = re.search(r"insert\s+into\s+public\.video_job_events\b[^;]*;", persist_body, re.DOTALL)
        assert event_insert
        insert_sql = event_insert.group(0)
        metadata_variables = set(re.findall(r"\b(?!p_metadata\b)[a-z_][a-z0-9_]*metadata\b", insert_sql)) - {"metadata"}
        inline_selector = any(selector in insert_sql for selector in (
            "jsonb_object_agg", "jsonb_build_object", "jsonb_path_query", "->",
        ))
        if inline_selector:
            unselected_metadata = re.sub(
                r"p_metadata\s*(?:->|->>|#>|#>>)\s*['\"][a-z_][a-z0-9_]*['\"]",
                "",
                insert_sql,
            )
            assert "p_metadata" not in unselected_metadata, "raw metadata must not accompany selected keys"
        operation = r"(?:jsonb_each|jsonb_object_agg|jsonb_build_object|jsonb_path_query|->)"
        transformed_variable = any(
            (
                re.search(rf"{variable}\s*:=.*?{operation}", metadata_scope, re.DOTALL)
                or re.search(rf"{operation}.*?into\s+{variable}\b", metadata_scope, re.DOTALL)
            )
            for variable in metadata_variables
        )
        assert inline_selector or transformed_variable

def test_persist_video_job_failure_is_locked_idempotent_and_completion_safe():
    sql = events_migration_text()
    body = sql_definition(sql, r"function public\.persist_video_job_failure\s*\(")
    update_position = body.find("update public.video_jobs")
    assert update_position >= 0
    assert re.search(r"select\b.*from public\.video_jobs\b.*for update", body, re.DOTALL)
    assert re.search(
        r"if\b.*status\s*(?:=\s*'completed'|in\s*\([^)]*'completed').*then\s*return",
        body[:update_position],
        re.DOTALL,
    )
    duplicate_guard = re.search(
        r"if\s+exists\s*\(.*public\.video_job_events.*(?:idempotency|job_failed).*\)\s*then\s*return",
        body[:update_position],
        re.DOTALL,
    )
    conflict = re.search(
        r"on\s+conflict\b[^;]*(?:do\s+nothing|idempotency_key)",
        body,
        re.DOTALL,
    )
    conflict_suppression = False
    if conflict:
        conflict_position = conflict.start()
        failed_terminal_guard = re.search(
            r"if\b.*status\s*(?:=\s*'failed'|in\s*\([^)]*'failed').*then\s*return",
            body[:update_position],
            re.DOTALL,
        )
        insert_gate = conflict_position < update_position and re.search(
            r"if\s+(?:not\s+found|[^;]*row_count[^;]*=\s*0).*then\s*return",
            body[conflict_position:update_position],
            re.DOTALL,
        )
        cte_gate = re.search(r"where\s+exists\s*\(\s*select\b[^)]*\b(?:inserted|event)\b", body, re.DOTALL)
        conflict_suppression = bool(failed_terminal_guard or insert_gate or cte_gate)
    assert duplicate_guard or conflict_suppression, "duplicate failures need idempotent suppression before canonical mutation"


def test_persist_video_job_failure_updates_canonical_failure_and_appends_one_event():
    sql = events_migration_text()
    body = sql_definition(sql, r"function public\.persist_video_job_failure\s*\(")
    for assignment in (
        r"status\s*=\s*'failed'",
        r"current_step\s*=\s*(?:'failed'|coalesce)",
        r"error_message\s*=",
        r"last_error\s*=",
        r"updated_at\s*=",
        r"finished_at\s*=",
    ):
        assert re.search(assignment, body)
    assert "sanitize_video_job_error" in sql
    assert "sanitize_video_job_error" in body
    progress = re.search(r"progress\s*=\s*([^,;]+)", body)
    assert progress
    progress_expression = progress.group(1).strip()
    if re.fullmatch(r"\d+", progress_expression):
        assert 0 <= int(progress_expression) < 100
    else:
        bounded_inline = any(term in progress_expression for term in ("least", "greatest", "between"))
        bounded_variable = re.fullmatch(r"[a-z_][a-z0-9_]*", progress_expression)
        assert bounded_inline or (
            bounded_variable
            and re.search(
                rf"{progress_expression}\s*:=.*?(?:least|greatest|between)",
                body,
                re.DOTALL,
            )
        )
    safe_failure_code = re.search(
        r"(?:last_error|error_message)\s*=[^;]*?(?:sanitize_video_job_error_code|'code')",
        body,
        re.DOTALL,
    )
    assert re.search(r"failure_class\s*=", body) or safe_failure_code
    for lease_column in ("claimed_by", "claimed_at", "lease_token", "lease_expires_at", "heartbeat_at"):
        assert re.search(rf"{lease_column}\s*=\s*null", body)

    event_inserts = re.findall(r"insert\s+into\s+public\.video_job_events\b[^;]*;", body, re.DOTALL)
    assert len(event_inserts) == 1
    event_insert = event_inserts[0]
    assert "event_type" in event_insert and "'job_failed'" in event_insert
    assert "level" in event_insert and "'error'" in event_insert


def test_migration_runner_and_verifier_cover_video_job_events_contracts():
    runner = RUNNER.read_text(encoding="utf-8")
    verify = VERIFY.read_text(encoding="utf-8").lower()
    assert "005_video_job_events.sql" in runner
    for required in ("video_job_events", "persist_video_job_failure"):
        assert required in verify
    assert "relrowsecurity" in verify or "rowsecurity" in verify


def test_foundation_migration_declares_fenced_rpc_contracts():
    sql = migration_text()
    for function in (
        "claim_next_video_job", "heartbeat_video_job", "begin_job_stage",
        "reserve_stage_external_attempt", "finalize_stage_success",
        "fail_job_stage", "release_video_job", "request_cancel_video_job",
        "acknowledge_cancel_video_job", "reap_expired_video_job_leases",
        "enqueue_regeneration",
    ):
        assert f"function public.{function}" in sql
    assert "lease_token = p_lease_token" in sql
    assert "lease_expires_at > now()" in sql
    assert "for update skip locked" in sql
    assert "provider_attempt_count" in sql
    assert "renderer_attempt_count" in sql
    assert "database_retry_count" in sql
    assert "status='running'" in sql
    assert "row.worker_id <> p_worker_id" in sql
    assert "grant execute on function public.claim_next_video_job" in sql
    assert "stage_row.status = 'running' then return" in sql
    assert "_retryable" in sql
    assert "retry_count + 1" in sql
    assert "max_retries + 1" in sql


def test_foundation_migration_has_approved_regeneration_modes_and_statuses():
    sql = migration_text()
    for value in ("scene_visual", "all_images", "script_creative", "video_render_only", "video_full_creative"):
        assert value in sql
    for value in ("queued", "leased", "running", "awaiting_reconciliation", "succeeded", "failed", "cancelled"):
        assert value in sql
    assert "target_scene_id" in sql and "scene.job_id=p_job_id" in sql
    assert "revision_sequence=next_revision" in sql
    assert "job.status not in ('completed','failed','cancelled')" in sql


def test_asset_path_api_exposes_posix_identity():
    import sys

    sys.path.insert(0, str(ROOT / "clipcraft" / "video-tools"))
    from asset_paths import get_asset_key, get_asset_path, get_container_path, get_filesystem_path

    job_id = "550E8400-E29B-41D4-A716-446655440000"
    assert get_asset_key(job_id, "scene", 3) == "550e8400-e29b-41d4-a716-446655440000/scene-03.png"
    assert get_container_path(job_id, "video") == "/data/jobs/550e8400-e29b-41d4-a716-446655440000/final.mp4"
    assert get_asset_path(job_id, "video")["asset_key"].endswith("/final.mp4")
    assert get_filesystem_path(job_id, "video", root="C:/jobs").name == "final.mp4"


@pytest.mark.parametrize("value", [True, False, 1.5, "3", None])
def test_scene_index_is_strict(value):
    import sys

    sys.path.insert(0, str(ROOT / "clipcraft" / "video-tools"))
    from asset_paths import get_asset_key

    with pytest.raises((TypeError, ValueError)):
        get_asset_key("550e8400-e29b-41d4-a716-446655440000", "scene", value)


def test_migration_does_not_change_provider_workflow_contract_files():
    for path in (ROOT / "clipcraft" / "workflows").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("name")


def test_path_traversal_test_is_not_a_false_positive():
    path_test = (ROOT / "clipcraft" / "tests" / "test_asset_paths.py").read_text(encoding="utf-8")
    assert "with pytest.raises(ValueError)" in path_test
