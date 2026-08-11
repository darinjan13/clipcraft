# Checkpoint 1R: begin_job_stage ledger-contract harness (Constrained Option A).
#
# Usage:
#   RED phase   (against the pre-1R function; every RED check must detect a gap):
#               .\test_checkpoint_1r_begin_job_stage_contract.ps1 -RedPhase
#   GREEN phase (applies the reconcile migration; every check must pass):
#               .\test_checkpoint_1r_begin_job_stage_contract.ps1
#
# Uses only the local postgres:17 container; never contacts production.
# Assertions are PL/pgSQL do-blocks (same pattern as the 1B harness), which
# avoids any PowerShell JSON parsing.

param([switch]$RedPhase)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Supabase = Join-Path $Root 'supabase'
$Archive = Join-Path $Supabase 'migrations_archive'
$Migrations = Join-Path $Supabase 'migrations'
$Container = 'clipcraft-1r-' + [guid]::NewGuid().ToString('N').Substring(0, 12)
$Password = 'ephemeral-' + [guid]::NewGuid().ToString('N')
$DatabaseName = 'clipcraft_1r_' + [guid]::NewGuid().ToString('N').Substring(0, 12)
$Started = $false

$Job = '11111111-1111-4111-8111-111111111111'
$JobExpired = '22222222-2222-4222-8222-222222222222'
$JobTerminal = '33333333-3333-4333-8333-333333333333'
$Lease = 'ce000000-0000-4000-8000-000000000001'
$Lease2 = 'ce000000-0000-4000-8000-000000000002'
$Lease3 = 'ce000000-0000-4000-8000-000000000003'
$Worker = 'worker-a'

function Invoke-Psql {
    param([string]$Sql)
    $Prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $Out = $Sql | & docker exec -i $Container psql -h 127.0.0.1 -p 5432 -U postgres -d $DatabaseName -v ON_ERROR_STOP=1 2>&1
    $Code = $LASTEXITCODE
    $ErrorActionPreference = $Prev
    if ($Code -ne 0) { throw "psql failed: $($Out -join [environment]::NewLine)" }
    return $Out
}

function Invoke-PsqlFile {
    param([string]$Path)
    Write-Host "APPLY $Path"
    Invoke-Psql (Get-Content -LiteralPath $Path -Raw -Encoding UTF8) | Out-Host
}

function Invoke-Q {
    param([string]$Sql)
    $Prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $Out = & docker exec -i $Container psql -h 127.0.0.1 -p 5432 -U postgres -d $DatabaseName -Atqc $Sql 2>&1
    $Code = $LASTEXITCODE
    $ErrorActionPreference = $Prev
    if ($Code -ne 0) { throw "query failed: $($Out -join [environment]::NewLine)" }
    return ([string]::Join([environment]::NewLine, $Out)).Trim()
}

function Invoke-PsqlExpectFailure {
    param([string]$Sql, [string]$Expected)
    $Prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $Out = $Sql | & docker exec -i $Container psql -h 127.0.0.1 -p 5432 -U postgres -d $DatabaseName -v ON_ERROR_STOP=1 2>&1
    $Code = $LASTEXITCODE
    $ErrorActionPreference = $Prev
    if ($Code -eq 0) { throw "Expected failure '$Expected' did not occur." }
    $Text = $Out -join [environment]::NewLine
    if ($Text -notmatch [regex]::Escape($Expected)) { throw "Expected '$Expected', got: $Text" }
}

function Run-Check {
    param([string]$Name, [switch]$Red, [scriptblock]$Action)
    if ($Red) {
        if ($RedPhase) {
            $errored = $false
            try { & $Action } catch { $errored = $true }
            if (-not $errored) { throw "RED harness error: '$Name' satisfied pre-1R behavior (no gap detected)." }
            Write-Host "RED   $Name"
        }
        else {
            try { & $Action; Write-Host "PASS  $Name" }
            catch { Write-Host "FAIL  $Name"; throw }
        }
    }
    else {
        if ($RedPhase) { Write-Host "SKIP $Name"; return }
        try { & $Action; Write-Host "PASS  $Name" }
        catch { Write-Host "FAIL  $Name"; throw }
    }
}

try {
    Write-Host "START container=$Container"
    & docker run --name $Container -e "POSTGRES_PASSWORD=$Password" -e "POSTGRES_DB=$DatabaseName" -d postgres:17 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'docker run failed' }
    $Started = $true

    $ready = $false
    for ($i = 0; $i -lt 60; $i++) {
        & docker exec $Container pg_isready -h 127.0.0.1 -p 5432 -U postgres -d $DatabaseName *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'postgres:17 not ready' }
    $probe = $false
    for ($i = 0; $i -lt 30; $i++) {
        $Prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        $P = & docker exec $Container psql -h 127.0.0.1 -p 5432 -U postgres -d $DatabaseName -Atqc 'select 1' 2>&1
        $Pe = $LASTEXITCODE; $ErrorActionPreference = $Prev
        if ($Pe -eq 0 -and (($P -join '').Trim() -eq '1')) { $probe = $true; break }
        Start-Sleep -Seconds ([Math]::Min(5, [Math]::Max(1, $i + 1)))
    }
    if (-not $probe) { throw 'readiness probe failed' }

    Invoke-PsqlFile (Join-Path $Archive '001_create_all_tables.sql')
    Invoke-PsqlFile (Join-Path $Archive '002_add_job_claiming.sql')
    Invoke-PsqlFile (Join-Path $Archive '003_asset_path_functions.sql')
    Invoke-PsqlFile (Join-Path $Archive '20260727134852_simple_processing_lifecycle.sql')
    Invoke-PsqlFile (Join-Path $Archive '006_add_soft_delete.sql')

    Invoke-Psql @'
create role service_role;
create role anon;
create role authenticated;
grant usage on schema public to service_role, anon, authenticated;
'@ | Out-Host

    Invoke-PsqlFile (Join-Path $Migrations '20260802140000_reconcile_job_leases_and_claim_contract.sql')
    Invoke-PsqlFile (Join-Path $Migrations '20260803120000_checkpoint_1b_lease_safety_rpcs.sql')

    Invoke-Psql @'
insert into public.video_jobs
  (id, topic, status, current_step, priority, attempt_number, pipeline_revision,
   next_stage, claimed_by, claimed_at, lease_token, lease_expires_at, heartbeat_at)
values
  ('11111111-1111-4111-8111-111111111111', 'active',   'generating_images', 'generate_images', 10, 1, 1, 'generate_images', 'worker-a', now(), 'ce000000-0000-4000-8000-000000000001', now() + interval '10 minutes', now()),
  ('22222222-2222-4222-8222-222222222222', 'expired',  'generating_images', 'generate_images', 10, 1, 1, 'generate_images', 'worker-a', now(), 'ce000000-0000-4000-8000-000000000002', now() - interval '1 minute', now() - interval '2 minutes'),
  ('33333333-3333-4333-8333-333333333333', 'terminal', 'completed',         'completed',       10, 1, 1, 'next',            'worker-a', now(), 'ce000000-0000-4000-8000-000000000003', now() + interval '10 minutes', now());
'@ | Out-Host

    Invoke-Psql @'
insert into public.job_stage_runs
  (job_id, pipeline_revision, stage, item_key, input_hash, status, job_attempt_number,
   worker_id, lease_token, run_token, output_json, error_json)
values
  ('11111111-1111-4111-8111-111111111111', 1, 's2', 'k2', 'h2',   'succeeded', 1, 'worker-a', 'ce000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002', '{"x":2}'::jsonb, null),
  ('11111111-1111-4111-8111-111111111111', 1, 's3', 'k3', 'h3',   'running',   1, 'worker-a', 'ce000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000003', null, null),
  ('11111111-1111-4111-8111-111111111111', 1, 's4', 'k4', 'h4',   'failed',    1, 'worker-a', 'ce000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000004', null, '{"message":"boom"}'::jsonb),
  ('11111111-1111-4111-8111-111111111111', 1, 's5', 'k5', 'old5', 'succeeded', 1, 'worker-a', 'ce000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000005', '{"x":5}'::jsonb, null),
  ('11111111-1111-4111-8111-111111111111', 1, 's6', 'k6', 'old6', 'running',   1, 'worker-a', 'ce000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000006', null, null),
  ('11111111-1111-4111-8111-111111111111', 1, 's7', 'k7', 'h7',   'weird',     1, 'worker-a', 'ce000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000007', null, null);
'@ | Out-Host

    if (-not $RedPhase) {
        Invoke-PsqlFile (Join-Path $Migrations '20260805120000_reconcile_begin_job_stage_contract.sql')
    }

    # ---------------- REGRESSION / unchanged behavior (green-only) ----------------

    Run-Check 'REG: STARTED creates exactly one ledger row with one run_token' {
        Invoke-Psql @'
do $$
declare r jsonb; c integer; st text;
begin
  select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's1', 'k1', 'h1', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1) into r;
  if r->>'state' <> 'STARTED' then raise exception 'EXPECTED STARTED got %', r->>'state'; end if;
  if r->>'run_token' is null or r->>'run_token' = '' then raise exception 'missing run_token'; end if;
  select count(*), max(status)::text into c, st from public.job_stage_runs where job_id='11111111-1111-4111-8111-111111111111' and pipeline_revision=1 and stage='s1' and item_key='k1';
  if c <> 1 then raise exception 'row count %', c; end if;
  if st <> 'running' then raise exception 'row status %', st; end if;
end $$;
'@ | Out-Host | Out-Null
    }

    Run-Check 'REG: CACHED_SUCCESS returns output, no run_token, row unchanged' {
        Invoke-Psql @'
do $$
declare r jsonb; st text;
begin
  select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's2', 'k2', 'h2', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1) into r;
  if r->>'state' <> 'CACHED_SUCCESS' then raise exception 'EXPECTED CACHED_SUCCESS got %', r->>'state'; end if;
  if r->'output' is distinct from '{"x":2}'::jsonb then raise exception 'cached output %', r->'output'; end if;
  if r ? 'run_token' then raise exception 'CACHED_SUCCESS leaked run_token'; end if;
  select status into st from public.job_stage_runs where job_id='11111111-1111-4111-8111-111111111111' and pipeline_revision=1 and stage='s2' and item_key='k2';
  if st <> 'succeeded' then raise exception 'cached row mutated to %', st; end if;
end $$;
'@ | Out-Host | Out-Null
    }

    Run-Check 'REG: expired lease -> LEASE_LOST' {
        Invoke-PsqlExpectFailure @'
do $$ begin perform public.begin_job_stage('22222222-2222-4222-8222-222222222222', 1, 's13', 'k13', 'h13', 'worker-a', 'ce000000-0000-4000-8000-000000000002', 1); end $$;
'@ 'LEASE_LOST'
    }
    Run-Check 'REG: wrong worker -> LEASE_LOST' {
        Invoke-PsqlExpectFailure @'
do $$ begin perform public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's14', 'k14', 'h14', 'other-worker', 'ce000000-0000-4000-8000-000000000001', 1); end $$;
'@ 'LEASE_LOST'
    }
    Run-Check 'REG: terminal video job -> LEASE_LOST' {
        Invoke-PsqlExpectFailure @'
do $$ begin perform public.begin_job_stage('33333333-3333-4333-8333-333333333333', 1, 's15', 'k15', 'h15', 'worker-a', 'ce000000-0000-4000-8000-000000000003', 1); end $$;
'@ 'LEASE_LOST'
    }
    Run-Check 'REG: non-positive attempt -> LEASE_LOST' {
        Invoke-PsqlExpectFailure @'
do $$ begin perform public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's16', 'k16', 'h16', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 0); end $$;
'@ 'LEASE_LOST'
    }
    Run-Check 'REG: non-positive revision -> LEASE_LOST' {
        Invoke-PsqlExpectFailure @'
do $$ begin perform public.begin_job_stage('11111111-1111-4111-8111-111111111111', 0, 's17', 'k17', 'h17', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1); end $$;
'@ 'LEASE_LOST'
    }

    Run-Check 'REG: service_role granted; anon/authenticated denied' {
        Invoke-Psql @'
do $$
begin
  if not has_function_privilege('service_role', 'public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer)', 'execute') then raise exception 'service_role lacks execute'; end if;
  if has_function_privilege('anon', 'public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer)', 'execute') then raise exception 'anon can execute'; end if;
  if has_function_privilege('authenticated', 'public.begin_job_stage(uuid, integer, text, text, text, text, uuid, integer)', 'execute') then raise exception 'authenticated can execute'; end if;
end $$;
'@ | Out-Host | Out-Null
        Invoke-PsqlExpectFailure @'
set role anon;
select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's18', 'k18', 'h18', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1);
'@ 'permission denied'
    }

    # ---------------- NEW contract (RED checks) ----------------

    Run-Check -Red 'NEW: RUNNING preserves existing run_token (no overwrite/refresh)' {
        Invoke-Psql @'
do $$
declare r jsonb; rn text;
begin
  select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's3', 'k3', 'h3', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1) into r;
  if r->>'state' <> 'RUNNING' then raise exception 'EXPECTED RUNNING got %', r->>'state'; end if;
  if r ? 'run_token' then raise exception 'RUNNING leaked run_token'; end if;
  select run_token::text into rn from public.job_stage_runs where job_id='11111111-1111-4111-8111-111111111111' and pipeline_revision=1 and stage='s3' and item_key='k3';
  if rn is distinct from '00000000-0000-4000-8000-000000000003' then raise exception 'run_token replaced: %', rn; end if;
end $$;
'@ | Out-Host | Out-Null
    }

    Run-Check -Red 'NEW: FAILED is terminal; failed row not overwritten' {
        Invoke-Psql @'
do $$
declare r jsonb; st text; ev jsonb;
begin
  select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's4', 'k4', 'h4', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1) into r;
  if r->>'state' <> 'FAILED' then raise exception 'EXPECTED FAILED got %', r->>'state'; end if;
  if r ? 'run_token' then raise exception 'FAILED leaked run_token'; end if;
  if r#>>'{error,message}' <> 'boom' then raise exception 'FAILED error %', r->'error'; end if;
  select status, error_json into st, ev from public.job_stage_runs where job_id='11111111-1111-4111-8111-111111111111' and pipeline_revision=1 and stage='s4' and item_key='k4';
  if st <> 'failed' then raise exception 'failed row overwritten to %', st; end if;
  if ev is distinct from '{"message":"boom"}'::jsonb then raise exception 'failed error_json mutated %', ev; end if;
end $$;
'@ | Out-Host | Out-Null
    }

    Run-Check -Red 'NEW: INPUT_HASH_MISMATCH on succeeded row (no cached output)' {
        Invoke-Psql @'
do $$
declare r jsonb; st text;
begin
  select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's5', 'k5', 'h5', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1) into r;
  if r->>'state' <> 'INPUT_HASH_MISMATCH' then raise exception 'EXPECTED INPUT_HASH_MISMATCH got %', r->>'state'; end if;
  if r ? 'output' then raise exception 'mismatch leaked cached output'; end if;
  if r ? 'run_token' then raise exception 'mismatch leaked run_token'; end if;
  select status into st from public.job_stage_runs where job_id='11111111-1111-4111-8111-111111111111' and pipeline_revision=1 and stage='s5' and item_key='k5';
  if st <> 'succeeded' then raise exception 'succeeded row mutated to %', st; end if;
end $$;
'@ | Out-Host | Out-Null
    }

    Run-Check -Red 'NEW: INPUT_HASH_MISMATCH on running row' {
        Invoke-Psql @'
do $$
declare r jsonb;
begin
  select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's6', 'k6', 'h6', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1) into r;
  if r->>'state' <> 'INPUT_HASH_MISMATCH' then raise exception 'EXPECTED INPUT_HASH_MISMATCH got %', r->>'state'; end if;
  if r ? 'run_token' then raise exception 'mismatch leaked run_token'; end if;
end $$;
'@ | Out-Host | Out-Null
    }

    Run-Check -Red 'NEW: UNKNOWN_OUTCOME for non-canonical status' {
        Invoke-Psql @'
do $$
declare r jsonb;
begin
  select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's7', 'k7', 'h7', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1) into r;
  if r->>'state' <> 'UNKNOWN_OUTCOME' then raise exception 'EXPECTED UNKNOWN_OUTCOME got %', r->>'state'; end if;
  if r ? 'run_token' then raise exception 'UNKNOWN_OUTCOME leaked run_token'; end if;
end $$;
'@ | Out-Host | Out-Null
    }

    Run-Check -Red 'NEW: INVALID_ITEM_KEY blank item key (JSON return, no row created)' {
        Invoke-Psql @'
do $$
declare r jsonb; c integer;
begin
  select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's8', '', 'h8', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1) into r;
  if r->>'state' <> 'INVALID_ITEM_KEY' then raise exception 'EXPECTED INVALID_ITEM_KEY got %', r->>'state'; end if;
  select count(*) into c from public.job_stage_runs where job_id='11111111-1111-4111-8111-111111111111' and pipeline_revision=1 and stage='s8' and item_key='';
  if c <> 0 then raise exception 'blank item key created % rows', c; end if;
end $$;
'@ | Out-Host | Out-Null
    }

    Run-Check -Red 'NEW: INVALID_INPUT_HASH blank hash' {
        Invoke-PsqlExpectFailure @'
do $$ begin perform public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's9', 'k9', '', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1); end $$;
'@ 'INVALID_INPUT_HASH'
    }
    Run-Check -Red 'NEW: INVALID_STAGE blank stage' {
        Invoke-PsqlExpectFailure @'
do $$ begin perform public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, '', 'k10', 'h10', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1); end $$;
'@ 'INVALID_STAGE'
    }
    Run-Check -Red 'NEW: INVALID_WORKER_ID blank worker' {
        Invoke-PsqlExpectFailure @'
do $$ begin perform public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's11', 'k11', 'h11', '', 'ce000000-0000-4000-8000-000000000001', 1); end $$;
'@ 'INVALID_WORKER_ID'
    }
    Run-Check -Red 'NEW: null lease token -> null-safe LEASE_LOST' {
        Invoke-PsqlExpectFailure @'
do $$ begin perform public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's12', 'k12', 'h12', 'worker-a', null, 1); end $$;
'@ 'LEASE_LOST'
    }

    Run-Check -Red 'NEW: idempotent re-begin -> RUNNING (one row, same stage_run_id)' {
        Invoke-Psql @'
do $$
declare r1 jsonb; r2 jsonb; rid uuid;
begin
  select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's_i', 'k_i', 'hi', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1) into r1;
  if r1->>'state' <> 'STARTED' then raise exception 'first begin %', r1->>'state'; end if;
  select id into rid from public.job_stage_runs where job_id='11111111-1111-4111-8111-111111111111' and pipeline_revision=1 and stage='s_i' and item_key='k_i';
  select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 's_i', 'k_i', 'hi', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1) into r2;
  if r2->>'state' <> 'RUNNING' then raise exception 'second begin %', r2->>'state'; end if;
  if r2->>'stage_run_id' <> rid::text then raise exception 'second begin changed stage_run_id'; end if;
  if r2 ? 'run_token' then raise exception 'second begin leaked run_token'; end if;
end $$;
'@ | Out-Host | Out-Null
    }

    Run-Check -Red 'NEW: concurrent begins serialize to one STARTED and one RUNNING' {
        $barrier = {
            param($C, $D)
            & docker exec -i $C psql -h 127.0.0.1 -p 5432 -U postgres -d $D -qAt -c "begin; lock table public.video_jobs in access exclusive mode; select pg_sleep(5); commit;" 2>&1
            if ($LASTEXITCODE -ne 0) { throw 'barrier psql failed' }
        }
        $begin = {
            param($C, $D)
            $O = & docker exec -i $C psql -h 127.0.0.1 -p 5432 -U postgres -d $D -Atqc "select public.begin_job_stage('11111111-1111-4111-8111-111111111111', 1, 'cc', 'kcc', 'hc', 'worker-a', 'ce000000-0000-4000-8000-000000000001', 1)::text;" 2>&1
            if ($LASTEXITCODE -ne 0) { throw "begin psql failed: $O" }
            return (([string]::Join([environment]::NewLine, $O)).Trim())
        }
        $barrierJob = Start-Job -ScriptBlock $barrier -ArgumentList $Container, $DatabaseName
        $granted = $false
        for ($i = 0; $i -lt 30; $i++) {
            $lc = Invoke-Q "select count(*) from pg_locks l join pg_class c on c.oid=l.relation where c.relname='video_jobs' and l.mode='AccessExclusiveLock' and l.granted;"
            if ($lc -match '1') { $granted = $true; break }
            Start-Sleep -Milliseconds 100
        }
        if (-not $granted) { throw 'concurrent barrier lock not granted' }
        $jobA = Start-Job -ScriptBlock $begin -ArgumentList $Container, $DatabaseName
        $jobB = Start-Job -ScriptBlock $begin -ArgumentList $Container, $DatabaseName
        Wait-Job -Job @($barrierJob, $jobA, $jobB) | Out-Null
        $sa = (Receive-Job -Job $jobA) -join ''
        $sb = (Receive-Job -Job $jobB) -join ''
        Remove-Job -Job @($barrierJob, $jobA, $jobB) -Force -ErrorAction SilentlyContinue
        $as = $sa.Contains('"state": "STARTED"'); $ar = $sa.Contains('"state": "RUNNING"')
        $bs = $sb.Contains('"state": "STARTED"'); $br = $sb.Contains('"state": "RUNNING"')
        $totalStarted = [int]$as + [int]$bs
        $totalRunning = [int]$ar + [int]$br
        if ($totalStarted -ne 1 -or $totalRunning -ne 1) { throw "expected 1 STARTED / 1 RUNNING, got $sa / $sb" }
        $cnt = Invoke-Q "select count(*) from public.job_stage_runs where job_id='11111111-1111-4111-8111-111111111111' and stage='cc' and item_key='kcc';"
        if ($cnt -ne '1') { throw "concurrent row count $cnt" }
    }

    Write-Host 'PASS all Checkpoint 1R begin_job_stage contract checks'
    if ($RedPhase) { Write-Host 'RED phase complete: every NEW contract check detected a pre-1R gap.' }
}
catch {
    Write-Host "FAIL $($_.Exception.Message)"
    exit 1
}
finally {
    if ($Started) {
        $o = & docker rm -f $Container 2>&1; $rc = $LASTEXITCODE; $o | Out-Host
        if ($rc -ne 0) { Write-Host "FAIL container removal exit=$rc"; exit 1 }
    }
}

exit 0