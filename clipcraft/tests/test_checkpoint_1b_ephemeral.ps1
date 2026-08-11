$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Supabase = Join-Path $Root 'supabase'
$Archive = Join-Path $Supabase 'migrations_archive'
$Migrations = Join-Path $Supabase 'migrations'
$Rollback = Join-Path $Supabase 'migrations_rollback'
$Container = 'clipcraft-1b-' + [guid]::NewGuid().ToString('N').Substring(0, 12)
$Password = 'ephemeral-' + [guid]::NewGuid().ToString('N')
$DatabaseName = 'clipcraft_1b_' + [guid]::NewGuid().ToString('N').Substring(0, 12)
$ConnectionHost = '127.0.0.1'
$ConnectionPort = 5432
$ConnectionTarget = [pscustomobject]@{
    Host = $ConnectionHost
    Port = $ConnectionPort
    Database = $DatabaseName
    Container = $Container
}
$Started = $false
# This harness uses only the local postgres:17 container; it never contacts a
# production URL. The legacy contract is
# claim_next_video_job(text), and repeated sequential calls cover reaper safety.

function Invoke-PsqlText {
    param([string]$Sql)
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $Output = $Sql | & docker exec -i $ConnectionTarget.Container psql -h $ConnectionTarget.Host -p $ConnectionTarget.Port -U postgres -d $ConnectionTarget.Database -v ON_ERROR_STOP=1 2>&1
    $ExitCode = $LASTEXITCODE
    $ErrorActionPreference = $PreviousErrorActionPreference
    if ($ExitCode -ne 0) {
        $Text = $Output -join [Environment]::NewLine
        Write-Host $Text
        throw "psql failed: $Text"
    }
    return $Output
}

function Invoke-PsqlFile {
    param([string]$Path)
    Write-Host "APPLY $Path"
    Invoke-PsqlText (Get-Content -LiteralPath $Path -Raw -Encoding UTF8) | Out-Host
}

function Invoke-PsqlExpectedFailure {
    param(
        [string]$Sql,
        [string]$ExpectedMessage
    )
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $Output = $Sql | & docker exec -i $ConnectionTarget.Container psql -h $ConnectionTarget.Host -p $ConnectionTarget.Port -U postgres -d $ConnectionTarget.Database -v ON_ERROR_STOP=1 2>&1
    $ExitCode = $LASTEXITCODE
    $ErrorActionPreference = $PreviousErrorActionPreference
    if ($ExitCode -eq 0) {
        throw "Expected failure '$ExpectedMessage' did not occur."
    }
    $Text = $Output -join [Environment]::NewLine
    if ($Text -notmatch [regex]::Escape($ExpectedMessage)) {
        throw "Expected '$ExpectedMessage', got: $Text"
    }
    Write-Host "EXPECTED FAIL $ExpectedMessage"
}

function Run-Check {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    try {
        & $Action
        Write-Host "PASS $Name"
    }
    catch {
        Write-Host "FAIL $Name"
        throw
    }
}

function Assert-DisposableConnectionTarget {
    if ($ConnectionTarget.Host -notin @('127.0.0.1', 'localhost')) {
        throw 'INVALID DISPOSABLE CONNECTION TARGET HOST'
    }
    if ($ConnectionTarget.Database -ne $DatabaseName) {
        throw 'INVALID DISPOSABLE CONNECTION TARGET DATABASE'
    }
    if ($ConnectionTarget.Container -ne $Container) {
        throw 'INVALID DISPOSABLE CONNECTION TARGET CONTAINER'
    }
    if ($ConnectionTarget.Port -ne 5432) {
        throw 'INVALID DISPOSABLE CONNECTION TARGET PORT'
    }
}

$FullJobStateFields = @(
    'id', 'user_id', 'channel_id', 'session_id', 'topic', 'brief_json',
    'script_json', 'render_manifest', 'output_url', 'thumbnail_url',
    'retry_count', 'max_retries', 'started_at', 'completed_at', 'deleted_at',
    'priority', 'created_at', 'last_error', 'cancel_requested', 'available_at',
    'status', 'current_step', 'next_stage', 'last_completed_stage',
    'claimed_by', 'claimed_at', 'attempt_number', 'pipeline_revision',
    'max_job_attempts', 'lease_token', 'lease_expires_at', 'heartbeat_at',
    'progress', 'failure_class', 'error_message', 'finished_at', 'updated_at'
)

function Get-JobStateSnapshot {
    param([string]$JobId)
    if ($JobId -notmatch '^[0-9a-f-]{36}$') { throw "invalid job id: $JobId" }
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $OptionalOutput = & docker exec -i $ConnectionTarget.Container psql -h $ConnectionTarget.Host -p $ConnectionTarget.Port -U postgres -d $ConnectionTarget.Database -Atqc "select column_name from information_schema.columns where table_schema = 'public' and table_name = 'video_jobs' and column_name in ('available_at', 'cancel_requested');" 2>&1
    $OptionalExitCode = $LASTEXITCODE
    if ($OptionalExitCode -ne 0) {
        $ErrorActionPreference = $PreviousErrorActionPreference
        throw "snapshot column discovery failed: $($OptionalOutput -join [Environment]::NewLine)"
    }
    $OptionalColumns = @($OptionalOutput | ForEach-Object { $_.ToString().Trim() })
    $AvailableExpression = if ($OptionalColumns -contains 'available_at') { 'available_at' } else { 'null::timestamptz' }
    $CancelExpression = if ($OptionalColumns -contains 'cancel_requested') { 'cancel_requested' } else { 'null::boolean' }
    $Sql = "select jsonb_build_object('id', id, 'user_id', user_id, 'channel_id', channel_id, 'session_id', session_id, 'topic', topic, 'brief_json', brief_json, 'script_json', script_json, 'render_manifest', render_manifest, 'output_url', output_url, 'thumbnail_url', thumbnail_url, 'retry_count', retry_count, 'max_retries', max_retries, 'started_at', started_at, 'completed_at', completed_at, 'deleted_at', deleted_at, 'priority', priority, 'created_at', created_at, 'last_error', last_error, 'cancel_requested', $CancelExpression, 'available_at', $AvailableExpression, 'status', status, 'current_step', current_step, 'next_stage', next_stage, 'last_completed_stage', last_completed_stage, 'claimed_by', claimed_by, 'claimed_at', claimed_at, 'attempt_number', attempt_number, 'pipeline_revision', pipeline_revision, 'max_job_attempts', max_job_attempts, 'lease_token', lease_token, 'lease_expires_at', lease_expires_at, 'heartbeat_at', heartbeat_at, 'progress', progress, 'failure_class', failure_class, 'error_message', error_message, 'finished_at', finished_at, 'updated_at', updated_at) from public.video_jobs where id = '$JobId';"
    $Output = & docker exec -i $ConnectionTarget.Container psql -h $ConnectionTarget.Host -p $ConnectionTarget.Port -U postgres -d $ConnectionTarget.Database -Atqc $Sql 2>&1
    $ExitCode = $LASTEXITCODE
    $ErrorActionPreference = $PreviousErrorActionPreference
    if ($ExitCode -ne 0) { throw "snapshot query failed: $($Output -join [Environment]::NewLine)" }
    $Text = ($Output -join '').Trim()
    if ([string]::IsNullOrWhiteSpace($Text)) { throw "job not found: $JobId" }
    return ($Text | ConvertFrom-Json)
}

function Assert-JobStateEqual {
    param(
        [psobject]$Before,
        [psobject]$After,
        [string]$Context
    )
    foreach ($Field in $FullJobStateFields) {
        $BeforeValue = $Before.PSObject.Properties[$Field].Value
        $AfterValue = $After.PSObject.Properties[$Field].Value
        if ([string]$BeforeValue -ne [string]$AfterValue) {
            throw "$Context changed ${Field}: '$BeforeValue' -> '$AfterValue'"
        }
    }
}

function Assert-LeaseCleared {
    param([psobject]$State, [string]$Context)
    foreach ($Field in @('claimed_by', 'claimed_at', 'lease_token', 'lease_expires_at', 'heartbeat_at')) {
        if ($null -ne $State.PSObject.Properties[$Field].Value) {
            throw "$Context left $Field populated"
        }
    }
}

try {
    Assert-DisposableConnectionTarget
    Write-Host "START container=$Container"
    & docker run --name $Container -e "POSTGRES_PASSWORD=$Password" -e "POSTGRES_DB=$DatabaseName" -d postgres:17 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'docker run failed' }
    $Started = $true

    for ($i = 0; $i -lt 60; $i++) {
        & docker exec $ConnectionTarget.Container pg_isready -h $ConnectionTarget.Host -p $ConnectionTarget.Port -U postgres -d $ConnectionTarget.Database *> $null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 1
    }
    if ($LASTEXITCODE -ne 0) { throw 'postgres:17 did not become ready' }

    $Ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        $PreviousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $ProbeOutput = & docker exec $ConnectionTarget.Container psql -h $ConnectionTarget.Host -p $ConnectionTarget.Port -U postgres -d $ConnectionTarget.Database -Atqc 'select 1' 2>&1
        $ProbeExit = $LASTEXITCODE
        $ErrorActionPreference = $PreviousErrorActionPreference
        if ($ProbeExit -eq 0 -and (($ProbeOutput -join '').Trim() -eq '1')) {
            $Ready = $true
            break
        }
        Start-Sleep -Seconds ([Math]::Min(5, [Math]::Max(1, $i + 1)))
    }
    if (-not $Ready) { throw 'psql select 1 readiness probe failed after bounded retries' }
    Write-Host 'PASS psql select 1 readiness probe'

    Invoke-PsqlFile (Join-Path $Archive '001_create_all_tables.sql')
    Invoke-PsqlFile (Join-Path $Archive '002_add_job_claiming.sql')
    Invoke-PsqlFile (Join-Path $Archive '003_asset_path_functions.sql')
    Invoke-PsqlFile (Join-Path $Archive '20260727134852_simple_processing_lifecycle.sql')
    Invoke-PsqlFile (Join-Path $Archive '006_add_soft_delete.sql')

    Invoke-PsqlText @'
create role service_role;
create role anon;
create role authenticated;
grant usage on schema public to service_role, anon, authenticated;
grant select, insert, update on public.video_jobs to service_role;
'@ | Out-Host

    Invoke-PsqlFile (Join-Path $Migrations '20260802140000_reconcile_job_leases_and_claim_contract.sql')

    Invoke-PsqlText @'
insert into public.video_jobs
  (id, topic, status, current_step, priority, attempt_number, pipeline_revision,
   next_stage, claimed_by, claimed_at, lease_token,
   lease_expires_at, heartbeat_at)
values
  ('11111111-1111-4111-8111-111111111111', 'normal reap', 'generating_images', 'generating_images', 10, null, null, 'generate_images', 'reaper', now() - interval '2 minutes', '11111111-1111-4111-8111-111111111112', now() - interval '1 minute', now() - interval '2 minutes'),
  ('22222222-2222-4222-8222-222222222222', 'max reap', 'generating_script', 'generating_script', 10, 1, null, 'generate_script', 'reaper', now() - interval '2 minutes', '22222222-2222-4222-8222-222222222223', now() - interval '1 minute', now() - interval '2 minutes'),
  ('33333333-3333-4333-8333-333333333333', 'repeat reap', 'generating_voice', 'generating_voice', 10, 0, null, 'generate_voice', 'reaper', now() - interval '2 minutes', '33333333-3333-4333-8333-333333333334', now() - interval '1 minute', now() - interval '2 minutes'),
  ('dddddddd-dddd-4ddd-8ddd-dddddddddddd', 'concurrent reap', 'generating_voice', 'generating_voice', 10, 0, 1, 'generate_voice', 'reaper', now() - interval '2 minutes', 'dddddddd-dddd-4ddd-8ddd-ddddddddddde', now() + interval '5 minutes', now()),
  ('44444444-4444-4444-8444-444444444444', 'claim max', 'queued', 'queued', 50, 1, null, null, null, null, null, null, null),
  ('55555555-5555-4555-8555-555555555555', 'release requeue', 'generating_images', 'generating_images', 10, 0, 1, 'generate_images', 'worker', now(), '55555555-5555-4555-8555-555555555556', now() + interval '5 minutes', now()),
  ('66666666-6666-4666-8666-666666666666', 'release complete stage', 'generating_images', 'generating_images', 100, 0, 1, 'generate_images', 'worker', now(), '66666666-6666-4666-8666-666666666667', now() + interval '5 minutes', now()),
  ('77777777-7777-4777-8777-777777777777', 'stale token', 'generating_voice', 'generating_voice', 10, 0, 1, 'generate_voice', 'worker', now(), '77777777-7777-4777-8777-777777777778', now() + interval '5 minutes', now()),
  ('88888888-8888-4888-8888-888888888888', 'invalid release', 'generating_voice', 'generating_voice', 10, 0, 1, 'generate_voice', 'worker', now(), '88888888-8888-4888-8888-888888888889', now() + interval '5 minutes', now()),
  ('cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'legacy release', 'generating_images', 'generating_images', 10, null, null, 'generate_images', 'worker', now(), 'cccccccc-cccc-4ccc-8ccc-cccccccccccd', now() + interval '5 minutes', now()),
  ('99999999-9999-4999-8999-999999999999', 'legacy claim', 'queued', 'queued', 1, 0, 1, null, null, null, null, null, null),
  ('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', 'fenced claim', 'queued', 'queued', 20, null, null, null, null, null, null, null, null);
'@ | Out-Host

    Invoke-PsqlText @'
update public.video_jobs
set lease_expires_at = case id
  when '11111111-1111-4111-8111-111111111111' then now() - interval '10 minutes'
  when '22222222-2222-4222-8222-222222222222' then now() - interval '9 minutes'
  when '33333333-3333-4333-8333-333333333333' then now() - interval '8 minutes'
  else now() - interval '8 minutes'
end
where id in (
  '11111111-1111-4111-8111-111111111111',
  '22222222-2222-4222-8222-222222222222',
  '33333333-3333-4333-8333-333333333333'
);
'@ | Out-Host

    Invoke-PsqlFile (Join-Path $Migrations '20260803120000_checkpoint_1b_lease_safety_rpcs.sql')
    Invoke-PsqlText @'
update public.video_jobs
set max_job_attempts = case id
  when '22222222-2222-4222-8222-222222222222' then 2
  when '33333333-3333-4333-8333-333333333333' then 5
  when 'dddddddd-dddd-4ddd-8ddd-dddddddddddd' then 5
  when '44444444-4444-4444-8444-444444444444' then 1
  else 3
end,
pipeline_revision = coalesce(pipeline_revision, 1)
where id in (
  '22222222-2222-4222-8222-222222222222',
  '33333333-3333-4333-8333-333333333333',
  'dddddddd-dddd-4ddd-8ddd-dddddddddddd',
  '44444444-4444-4444-8444-444444444444',
  '55555555-5555-4555-8555-555555555555',
  '66666666-6666-4666-8666-666666666666',
  '77777777-7777-4777-8777-777777777777',
  '88888888-8888-4888-8888-888888888888',
  '99999999-9999-4999-8999-999999999999'
);
'@ | Out-Host

    Run-Check 'future forward checks reject null and invalid values' {
        Invoke-PsqlExpectedFailure @'
insert into public.video_jobs (id, topic, attempt_number)
values ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1', 'null attempt', null);
'@ 'video_jobs_attempt_number_forward_check'
        Invoke-PsqlExpectedFailure @'
insert into public.video_jobs (id, topic, pipeline_revision)
values ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee2', 'null revision', null);
'@ 'video_jobs_pipeline_revision_forward_check'
        Invoke-PsqlExpectedFailure @'
insert into public.video_jobs (id, topic, max_job_attempts)
values ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee3', 'null limit', null);
'@ 'video_jobs_max_job_attempts_forward_check'
        Invoke-PsqlExpectedFailure @'
insert into public.video_jobs (id, topic, attempt_number)
values ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee4', 'negative attempt', -1);
'@ 'video_jobs_attempt_number_forward_check'
        Invoke-PsqlExpectedFailure @'
insert into public.video_jobs (id, topic, pipeline_revision)
values ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee5', 'zero revision', 0);
'@ 'video_jobs_pipeline_revision_forward_check'
        Invoke-PsqlExpectedFailure @'
insert into public.video_jobs (id, topic, max_job_attempts)
values ('eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee6', 'zero limit', 0);
'@ 'video_jobs_max_job_attempts_forward_check'
    }

    Run-Check 'normal expired lease reaping' {
        Invoke-PsqlText @'
set role service_role;
do $$
declare r jsonb; j public.video_jobs;
begin
  select public.reap_expired_video_job_leases(1) into r;
  if r->>'reaped_count' <> '1' or r->>'failed_count' <> '0' then raise exception 'bad normal reap result %', r; end if;
  select * into j from public.video_jobs where id = '11111111-1111-4111-8111-111111111111';
  if j.status <> 'queued' or j.attempt_number <> 1 or j.max_job_attempts <> 3 or j.pipeline_revision <> 1 or j.next_stage <> 'generate_images' or j.claimed_by is not null or j.claimed_at is not null or j.lease_token is not null or j.lease_expires_at is not null or j.heartbeat_at is not null then raise exception 'normal reap state mismatch'; end if;
end $$;
'@ | Out-Host
    }

    Run-Check 'max-attempt expired lease failure' {
        Invoke-PsqlText @'
set role service_role;
do $$
declare j public.video_jobs;
begin
  perform public.reap_expired_video_job_leases(1);
  select * into j from public.video_jobs where id = '22222222-2222-4222-8222-222222222222';
  if j.status <> 'failed' or j.failure_class <> 'LEASE_EXPIRED_MAX_ATTEMPTS' or j.attempt_number <> 2 or j.claimed_by is not null or j.claimed_at is not null or j.lease_token is not null or j.lease_expires_at is not null or j.heartbeat_at is not null then raise exception 'max reap state mismatch'; end if;
end $$;
'@ | Out-Host
    }

    Run-Check 'repeated reaping processes one lease once' {
        Invoke-PsqlText @'
set role service_role;
do $$
declare first_result jsonb; second_result jsonb; j public.video_jobs;
begin
  select public.reap_expired_video_job_leases(1) into first_result;
  select public.reap_expired_video_job_leases(1) into second_result;
  if first_result->>'reaped_count' <> '1' or second_result->>'reaped_count' <> '0' then raise exception 'repeat reap count mismatch'; end if;
  select * into j from public.video_jobs where id = '33333333-3333-4333-8333-333333333333';
  if j.attempt_number <> 1 or j.status <> 'queued' or j.lease_token is not null then raise exception 'repeat reap state mismatch'; end if;
end $$;
'@ | Out-Host
    }

    Run-Check 'concurrent reaper processes one lease once' {
        Invoke-PsqlText @'
update public.video_jobs
set lease_expires_at = now() - interval '1 minute'
where id = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
'@ | Out-Host
        $ConcurrentReaper = {
            param([string]$ContainerName, [string]$DatabaseName)
            $Sql = "set role service_role; select public.reap_expired_video_job_leases(1);"
            $Output = $Sql | & docker exec -i $ContainerName psql -h 127.0.0.1 -p 5432 -U postgres -d $DatabaseName -qAt 2>&1
            if ($LASTEXITCODE -ne 0) { throw "concurrent reaper psql failed: $($Output -join [Environment]::NewLine)" }
            return (($Output -join '').Trim())
        }
        $BarrierJob = $null
        $JobA = $null
        $JobB = $null
        try {
            $BarrierScript = {
                param([string]$ContainerName, [string]$DatabaseName)
                $Sql = "begin; lock table public.video_jobs in access exclusive mode; select pg_sleep(5); commit;"
                $Output = $Sql | & docker exec -i $ContainerName psql -h 127.0.0.1 -p 5432 -U postgres -d $DatabaseName -qAt 2>&1
                if ($LASTEXITCODE -ne 0) { throw "barrier psql failed: $($Output -join [Environment]::NewLine)" }
            }
            $BarrierJob = Start-Job -ScriptBlock $BarrierScript -ArgumentList $ConnectionTarget.Container, $ConnectionTarget.Database
            $BarrierGranted = $false
            for ($i = 0; $i -lt 30; $i++) {
                $LockOutput = Invoke-PsqlText "select count(*) from pg_locks l join pg_class c on c.oid = l.relation where c.relname = 'video_jobs' and l.mode = 'AccessExclusiveLock' and l.granted;"
                if (($LockOutput -join '').Trim() -match '1') { $BarrierGranted = $true; break }
                Start-Sleep -Milliseconds 100
            }
            if (-not $BarrierGranted) { throw 'concurrent reaper barrier lock was not granted' }
            Write-Host 'PASS concurrent reaper barrier lock granted'
            $JobA = Start-Job -ScriptBlock $ConcurrentReaper -ArgumentList $ConnectionTarget.Container, $ConnectionTarget.Database
            $JobB = Start-Job -ScriptBlock $ConcurrentReaper -ArgumentList $ConnectionTarget.Container, $ConnectionTarget.Database
            Wait-Job -Job @($BarrierJob, $JobA, $JobB) | Out-Null
            $ResultA = ((Receive-Job -Job $JobA) -join '').Trim() | ConvertFrom-Json
            $ResultB = ((Receive-Job -Job $JobB) -join '').Trim() | ConvertFrom-Json
            if (([int]$ResultA.reaped_count + [int]$ResultB.reaped_count) -ne 1 -or ([int]$ResultA.failed_count + [int]$ResultB.failed_count) -ne 0) {
                throw "concurrent reaper count mismatch: $ResultA / $ResultB"
            }
            if (([int]$ResultA.reaped_count -eq 1) -eq ([int]$ResultB.reaped_count -eq 1)) {
                throw "concurrent reaper did not produce exactly one winner: $ResultA / $ResultB"
            }
            $ConcurrentState = Get-JobStateSnapshot 'dddddddd-dddd-4ddd-8ddd-dddddddddddd'
            if ($ConcurrentState.status -ne 'queued' -or $ConcurrentState.attempt_number -ne 1) { throw 'concurrent reaper state mismatch' }
            Assert-LeaseCleared $ConcurrentState 'concurrent reaper'
        }
        finally {
            if ($null -ne $BarrierJob) { Remove-Job -Job $BarrierJob -Force -ErrorAction SilentlyContinue }
            if ($null -ne $JobA) { Remove-Job -Job $JobA -Force -ErrorAction SilentlyContinue }
            if ($null -ne $JobB) { Remove-Job -Job $JobB -Force -ErrorAction SilentlyContinue }
        }
    }

    Run-Check 'claim limit failure and normalization' {
        Invoke-PsqlText @'
set role service_role;
do $$
declare r jsonb; j public.video_jobs;
begin
  select public.claim_next_video_job_fenced('limit-worker', 30) into r;
  select * into j from public.video_jobs where id = '44444444-4444-4444-8444-444444444444';
  if r->>'claimed' <> 'false' or r->>'failure_class' <> 'LEASE_EXPIRED_MAX_ATTEMPTS' then raise exception 'claim limit result mismatch'; end if;
  if j.status <> 'failed' or j.failure_class <> 'LEASE_EXPIRED_MAX_ATTEMPTS' or j.attempt_number <> 1 or j.max_job_attempts <> 1 or j.pipeline_revision <> 1 then raise exception 'claim limit state mismatch'; end if;
end $$;
'@ | Out-Host
    }

    Run-Check 'fenced claim normalizes and initializes legacy fields' {
        Invoke-PsqlText @'
set role service_role;
do $$
declare r jsonb; j public.video_jobs;
begin
  select public.claim_next_video_job_fenced('claim-worker', 30) into r;
  select * into j from public.video_jobs where id = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
  if r->>'claimed' <> 'true' or r#>>'{job,attempt_number}' <> '1' or r#>>'{job,pipeline_revision}' <> '1' or r#>>'{job,max_job_attempts}' <> '3' or r#>>'{job,next_stage}' <> 'generate_script' or r#>>'{job,lease_token}' is null then raise exception 'fenced claim normalization mismatch: %', r; end if;
end $$;
'@ | Out-Host
    }

    Run-Check 'release requeue preserves stage and clears lease' {
        Invoke-PsqlText @'
set role service_role;
do $$
declare j public.video_jobs;
begin
  perform public.release_video_job('55555555-5555-4555-8555-555555555555', '55555555-5555-4555-8555-555555555556', 'requeue');
  select * into j from public.video_jobs where id = '55555555-5555-4555-8555-555555555555';
  if j.status <> 'queued' or j.next_stage <> 'generate_images' or j.current_step <> 'generate_images' or j.claimed_by is not null or j.claimed_at is not null or j.lease_token is not null or j.lease_expires_at is not null or j.heartbeat_at is not null then raise exception 'requeue state mismatch'; end if;
end $$;
'@ | Out-Host
        $RequeueState = Get-JobStateSnapshot '55555555-5555-4555-8555-555555555555'
        Assert-LeaseCleared $RequeueState 'requeue release'
    }

    Run-Check 'legacy nullable release normalizes fields and clears lease' {
        $LegacyBefore = Get-JobStateSnapshot 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
        if ($null -ne $LegacyBefore.attempt_number -or $null -ne $LegacyBefore.pipeline_revision -or $null -ne $LegacyBefore.max_job_attempts) {
            throw 'legacy release fixture was not nullable before release'
        }
        Invoke-PsqlText @'
set role service_role;
select public.release_video_job('cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'cccccccc-cccc-4ccc-8ccc-cccccccccccd', 'requeue');
'@ | Out-Host
        $LegacyAfter = Get-JobStateSnapshot 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
        if ($LegacyAfter.attempt_number -ne 0 -or $LegacyAfter.pipeline_revision -ne 1 -or $LegacyAfter.max_job_attempts -ne 3 -or $LegacyAfter.status -ne 'queued') {
            throw 'legacy release did not normalize fields'
        }
        Assert-LeaseCleared $LegacyAfter 'legacy nullable release'
    }

    Run-Check 'completed-stage release and immediate next-stage claim' {
        $PriorLeaseToken = (Get-JobStateSnapshot '66666666-6666-4666-8666-666666666666').lease_token
        Invoke-PsqlText @'
set role service_role;
do $$
declare r jsonb; j public.video_jobs;
begin
  perform public.release_video_job('66666666-6666-4666-8666-666666666666', '66666666-6666-4666-8666-666666666667', 'completed_stage', 'generate_voice');
  select * into j from public.video_jobs where id = '66666666-6666-4666-8666-666666666666';
  if j.status <> 'queued' or j.last_completed_stage <> 'generate_images' or j.next_stage <> 'generate_voice' or j.claimed_by is not null or j.claimed_at is not null or j.lease_token is not null or j.lease_expires_at is not null or j.heartbeat_at is not null then raise exception 'completed-stage release mismatch'; end if;
  select public.claim_next_video_job_fenced('next-stage-worker', 30) into r;
  if r->>'claimed' <> 'true' or r#>>'{job,id}' <> '66666666-6666-4666-8666-666666666666' or r#>>'{job,status}' <> 'generating_voice' or r#>>'{job,current_step}' <> 'generate_voice' or r#>>'{lease_token}' is null then raise exception 'next-stage claim mismatch'; end if;
end $$;
'@ | Out-Host
        $ClaimedState = Get-JobStateSnapshot '66666666-6666-4666-8666-666666666666'
        if ($ClaimedState.status -ne 'generating_voice' -or $ClaimedState.current_step -ne 'generate_voice' -or $null -eq $ClaimedState.lease_token -or $ClaimedState.lease_token -eq $PriorLeaseToken) {
            throw 'completed-stage claim did not receive a distinct new lease token and expected stage'
        }
    }

    Run-Check 'stale token and invalid input rejection' {
        Invoke-PsqlText @'
set role service_role;
do $$
declare before_job public.video_jobs; after_job public.video_jobs; caught boolean; message text;
begin
  select * into before_job from public.video_jobs where id = '77777777-7777-4777-8777-777777777777';
  caught := false;
  begin
    perform public.release_video_job('77777777-7777-4777-8777-777777777777', '77777777-7777-4777-8777-777777777779', 'requeue');
  exception when others then
    caught := true;
    if sqlerrm not like '%LEASE_LOST%' then raise; end if;
  end;
  if not caught then raise exception 'stale token was accepted'; end if;
  select * into after_job from public.video_jobs where id = '77777777-7777-4777-8777-777777777777';
  if before_job.status is distinct from after_job.status or before_job.current_step is distinct from after_job.current_step or before_job.next_stage is distinct from after_job.next_stage or before_job.last_completed_stage is distinct from after_job.last_completed_stage or before_job.attempt_number is distinct from after_job.attempt_number or before_job.pipeline_revision is distinct from after_job.pipeline_revision or before_job.max_job_attempts is distinct from after_job.max_job_attempts or before_job.progress is distinct from after_job.progress or before_job.failure_class is distinct from after_job.failure_class or before_job.error_message is distinct from after_job.error_message or before_job.finished_at is distinct from after_job.finished_at or before_job.updated_at is distinct from after_job.updated_at or before_job.claimed_by is distinct from after_job.claimed_by or before_job.claimed_at is distinct from after_job.claimed_at or before_job.lease_token is distinct from after_job.lease_token or before_job.lease_expires_at is distinct from after_job.lease_expires_at or before_job.heartbeat_at is distinct from after_job.heartbeat_at then raise exception 'stale token mutated state'; end if;
end $$;
'@ | Out-Host

        Invoke-PsqlText @'
set role service_role;
do $$
declare before_job public.video_jobs; after_job public.video_jobs; caught boolean;
begin
  select * into before_job from public.video_jobs where id = '88888888-8888-4888-8888-888888888888';
  caught := false;
  begin
    perform public.release_video_job('88888888-8888-4888-8888-888888888888', '88888888-8888-4888-8888-888888888889', null);
  exception when others then
    caught := true;
    if sqlerrm not like '%INVALID_RELEASE_OUTCOME%' then raise; end if;
  end;
  if not caught then raise exception 'NULL outcome was accepted'; end if;
  select * into after_job from public.video_jobs where id = '88888888-8888-4888-8888-888888888888';
  if before_job.status is distinct from after_job.status or before_job.current_step is distinct from after_job.current_step or before_job.next_stage is distinct from after_job.next_stage or before_job.last_completed_stage is distinct from after_job.last_completed_stage or before_job.attempt_number is distinct from after_job.attempt_number or before_job.pipeline_revision is distinct from after_job.pipeline_revision or before_job.max_job_attempts is distinct from after_job.max_job_attempts or before_job.progress is distinct from after_job.progress or before_job.failure_class is distinct from after_job.failure_class or before_job.error_message is distinct from after_job.error_message or before_job.finished_at is distinct from after_job.finished_at or before_job.updated_at is distinct from after_job.updated_at or before_job.claimed_by is distinct from after_job.claimed_by or before_job.claimed_at is distinct from after_job.claimed_at or before_job.lease_token is distinct from after_job.lease_token or before_job.lease_expires_at is distinct from after_job.lease_expires_at or before_job.heartbeat_at is distinct from after_job.heartbeat_at then raise exception 'NULL outcome mutated state'; end if;
  caught := false;
  begin
    perform public.release_video_job('88888888-8888-4888-8888-888888888888', '88888888-8888-4888-8888-888888888889', 'completed_stage', 'not_a_stage');
  exception when others then
    caught := true;
    if sqlerrm not like '%INVALID_NEXT_STAGE%' then raise; end if;
  end;
  if not caught then raise exception 'invalid next stage was accepted'; end if;
  select * into after_job from public.video_jobs where id = '88888888-8888-4888-8888-888888888888';
  if before_job.status is distinct from after_job.status or before_job.current_step is distinct from after_job.current_step or before_job.next_stage is distinct from after_job.next_stage or before_job.last_completed_stage is distinct from after_job.last_completed_stage or before_job.attempt_number is distinct from after_job.attempt_number or before_job.pipeline_revision is distinct from after_job.pipeline_revision or before_job.max_job_attempts is distinct from after_job.max_job_attempts or before_job.progress is distinct from after_job.progress or before_job.failure_class is distinct from after_job.failure_class or before_job.error_message is distinct from after_job.error_message or before_job.finished_at is distinct from after_job.finished_at or before_job.updated_at is distinct from after_job.updated_at or before_job.claimed_by is distinct from after_job.claimed_by or before_job.claimed_at is distinct from after_job.claimed_at or before_job.lease_token is distinct from after_job.lease_token or before_job.lease_expires_at is distinct from after_job.lease_expires_at or before_job.heartbeat_at is distinct from after_job.heartbeat_at then raise exception 'invalid next stage mutated state'; end if;
end $$;
'@ | Out-Host
        $StaleBefore = Get-JobStateSnapshot '77777777-7777-4777-8777-777777777777'
        Invoke-PsqlExpectedFailure @'
set role service_role;
select public.release_video_job('77777777-7777-4777-8777-777777777777', '77777777-7777-4777-8777-777777777779', 'requeue');
'@ 'LEASE_LOST'
        Assert-JobStateEqual $StaleBefore (Get-JobStateSnapshot '77777777-7777-4777-8777-777777777777') 'stale token release'

        $InvalidBefore = Get-JobStateSnapshot '88888888-8888-4888-8888-888888888888'
        Invoke-PsqlExpectedFailure @'
set role service_role;
select public.release_video_job('88888888-8888-4888-8888-888888888888', '88888888-8888-4888-8888-888888888889', null);
'@ 'INVALID_RELEASE_OUTCOME'
        Assert-JobStateEqual $InvalidBefore (Get-JobStateSnapshot '88888888-8888-4888-8888-888888888888') 'NULL outcome release'
        Invoke-PsqlExpectedFailure @'
set role service_role;
select public.release_video_job('88888888-8888-4888-8888-888888888888', '88888888-8888-4888-8888-888888888889', 'completed_stage', 'not_a_stage');
'@ 'INVALID_NEXT_STAGE'
        Assert-JobStateEqual $InvalidBefore (Get-JobStateSnapshot '88888888-8888-4888-8888-888888888888') 'invalid next stage release'
    }

    Run-Check 'additional failure paths preserve full job state' {
        $DurationBefore = Get-JobStateSnapshot '99999999-9999-4999-8999-999999999999'
        Invoke-PsqlExpectedFailure @'
set role service_role;
select public.claim_next_video_job_fenced('duration-worker', 4);
'@ 'INVALID_LEASE_SECONDS'
        Assert-JobStateEqual $DurationBefore (Get-JobStateSnapshot '99999999-9999-4999-8999-999999999999') 'invalid lease duration'

        $BatchBefore = Get-JobStateSnapshot '77777777-7777-4777-8777-777777777777'
        Invoke-PsqlExpectedFailure @'
set role service_role;
select public.reap_expired_video_job_leases(null::integer);
'@ 'INVALID_BATCH_SIZE'
        Assert-JobStateEqual $BatchBefore (Get-JobStateSnapshot '77777777-7777-4777-8777-777777777777') 'NULL batch size'

        Invoke-PsqlExpectedFailure @'
set role service_role;
select public.release_video_job('77777777-7777-4777-8777-777777777777', '77777777-7777-4777-8777-777777777778', 'requeue', 'generate_voice');
'@ 'INVALID_NEXT_STAGE'
        Assert-JobStateEqual $BatchBefore (Get-JobStateSnapshot '77777777-7777-4777-8777-777777777777') 'requeue next stage'

        Invoke-PsqlText @'
update public.video_jobs
set status = 'completed', current_step = 'completed', finished_at = now()
where id = '88888888-8888-4888-8888-888888888888';
'@ | Out-Host
        $TerminalBefore = Get-JobStateSnapshot '88888888-8888-4888-8888-888888888888'
        Invoke-PsqlExpectedFailure @'
set role service_role;
select public.release_video_job('88888888-8888-4888-8888-888888888888', '88888888-8888-4888-8888-888888888889', 'requeue');
'@ 'JOB_TERMINAL'
        Assert-JobStateEqual $TerminalBefore (Get-JobStateSnapshot '88888888-8888-4888-8888-888888888888') 'terminal release'
    }

    Run-Check 'expired release rejects token and preserves state' {
        Invoke-PsqlText @'
update public.video_jobs
set lease_expires_at = now() - interval '1 minute'
where id = '77777777-7777-4777-8777-777777777777';
'@ | Out-Host
        $ExpiredBefore = Get-JobStateSnapshot '77777777-7777-4777-8777-777777777777'
        Invoke-PsqlExpectedFailure @'
set role service_role;
select public.release_video_job('77777777-7777-4777-8777-777777777777', '77777777-7777-4777-8777-777777777778', 'requeue');
'@ 'LEASE_LOST'
        Assert-JobStateEqual $ExpiredBefore (Get-JobStateSnapshot '77777777-7777-4777-8777-777777777777') 'expired release'
        Invoke-PsqlText @'
update public.video_jobs
set lease_expires_at = now() + interval '5 minutes'
where id = '77777777-7777-4777-8777-777777777777';
'@ | Out-Host
    }

    Run-Check 'legacy claim and fenced grants' {
        Invoke-PsqlText @'
set role service_role;
do $$
declare legacy public.video_jobs;
begin
  if not has_function_privilege('service_role', 'public.claim_next_video_job_fenced(text, integer)', 'execute') then raise exception 'service role lacks fenced claim'; end if;
  if has_function_privilege('anon', 'public.claim_next_video_job_fenced(text, integer)', 'execute') then raise exception 'anon can execute fenced claim'; end if;
  if has_function_privilege('authenticated', 'public.claim_next_video_job_fenced(text, integer)', 'execute') then raise exception 'authenticated can execute fenced claim'; end if;
  select * into legacy from public.claim_next_video_job('legacy-worker');
  if legacy.id <> '99999999-9999-4999-8999-999999999999' then raise exception 'legacy claim did not claim fixture'; end if;
end $$;
'@ | Out-Host
    }

    Run-Check 'rollback guard refuses active fenced lease' {
        Invoke-PsqlText @'
insert into public.video_jobs (id, topic, status, current_step, claimed_by, claimed_at, lease_token, lease_expires_at, heartbeat_at)
values ('bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', 'rollback guard', 'generating_script', 'generating_script', 'rollback-worker', now(), 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbc', now() + interval '5 minutes', now());
'@ | Out-Host
        Invoke-PsqlExpectedFailure (Get-Content -LiteralPath (Join-Path $Rollback '20260803120000_checkpoint_1b_lease_safety_rpcs.down.sql') -Raw -Encoding UTF8) 'ACTIVE_FENCED_LEASES_EXIST'
    }

    Run-Check 'safe rollback preserves Checkpoint 1A objects' {
        Invoke-PsqlText @'
update public.video_jobs
set status = 'failed', lease_token = null, lease_expires_at = null, heartbeat_at = null, claimed_by = null, claimed_at = null
where lease_token is not null;
'@ | Out-Host
        Invoke-PsqlFile (Join-Path $Rollback '20260803120000_checkpoint_1b_lease_safety_rpcs.down.sql')
        Invoke-PsqlText @'
do $$
declare required_column text; required_stage_column text;
begin
  if to_regprocedure('public.claim_next_video_job(text)') is null then raise exception 'legacy claim signature missing'; end if;
  if not has_function_privilege('service_role', 'public.claim_next_video_job(text)', 'execute') then raise exception 'legacy claim grant missing'; end if;
  if to_regprocedure('public.claim_next_video_job_fenced(text, integer)') is null then raise exception '1A fenced claim missing'; end if;
  if to_regprocedure('public.heartbeat_video_job(uuid, text, uuid, integer, integer, integer)') is null then raise exception '1A heartbeat missing'; end if;
  if not has_function_privilege('service_role', 'public.claim_next_video_job_fenced(text, integer)', 'execute') then raise exception '1A fenced claim grant missing'; end if;
  if not has_function_privilege('service_role', 'public.heartbeat_video_job(uuid, text, uuid, integer, integer, integer)', 'execute') then raise exception '1A heartbeat grant missing'; end if;
  if to_regprocedure('public.reap_expired_video_job_leases(integer)') is not null then raise exception '1B reaper remains'; end if;
  if to_regprocedure('public.release_video_job(uuid, uuid, text, text)') is not null then raise exception '1B release remains'; end if;
  if exists (select 1 from information_schema.columns c where c.table_schema = 'public' and c.table_name = 'video_jobs' and c.column_name = 'max_job_attempts') then raise exception '1B column remains'; end if;
  if exists (select 1 from pg_constraint where conrelid = 'public.video_jobs'::regclass and conname in ('video_jobs_attempt_number_forward_check', 'video_jobs_pipeline_revision_forward_check', 'video_jobs_max_job_attempts_forward_check')) then raise exception '1B constraints remain'; end if;
  if exists (select 1 from pg_indexes where schemaname = 'public' and indexname like '%checkpoint_1b%') then raise exception '1B indexes remain'; end if;
  foreach required_column in array array['lease_token', 'lease_expires_at', 'heartbeat_at', 'attempt_number', 'pipeline_revision', 'next_stage', 'last_completed_stage', 'failure_class'] loop
    if not exists (select 1 from information_schema.columns c where c.table_schema = 'public' and c.table_name = 'video_jobs' and c.column_name = required_column) then raise exception '1A column missing: %', required_column; end if;
  end loop;
  if exists (select 1 from information_schema.columns c where c.table_schema = 'public' and c.table_name = 'video_jobs' and c.column_name in ('attempt_number', 'pipeline_revision') and c.column_default is not null) then raise exception '1B defaults remain'; end if;
  if to_regclass('public.video_jobs_fenced_queue_idx') is null or to_regclass('public.video_jobs_fenced_lease_idx') is null then raise exception '1A fenced indexes missing'; end if;
  if to_regclass('public.job_stage_runs') is null then raise exception '1A stage ledger missing'; end if;
  foreach required_stage_column in array array['job_id', 'pipeline_revision', 'stage', 'item_key', 'lease_token', 'job_attempt_number'] loop
    if not exists (select 1 from information_schema.columns c where c.table_schema = 'public' and c.table_name = 'job_stage_runs' and c.column_name = required_stage_column) then raise exception '1A stage column missing: %', required_stage_column; end if;
  end loop;
end $$;
'@ | Out-Host
    }

    Write-Host 'PASS all Checkpoint 1B ephemeral validation'
}
catch {
    Write-Host "FAIL $($_.Exception.Message)"
    exit 1
}
finally {
    if ($Started) {
        Write-Host "REMOVE container=$Container"
        $RemoveOutput = & docker rm -f $Container 2>&1
        $RemoveExit = $LASTEXITCODE
        $RemoveOutput | Out-Host
        if ($RemoveExit -ne 0) {
            Write-Host "FAIL container removal exit=$RemoveExit"
            exit 1
        }
        $PreviousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $InspectOutput = & docker container inspect $Container 2>&1
        $InspectExit = $LASTEXITCODE
        $ErrorActionPreference = $PreviousErrorActionPreference
        if ($InspectExit -eq 0) {
            Write-Host 'FAIL container still exists after removal'
            exit 1
        }
        Write-Host 'PASS container removed and verified absent'
    }
}

exit 0
