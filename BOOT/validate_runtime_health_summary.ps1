param(
    [int]$MaxSnapshotAgeSec = 180,
    [int]$MaxHealthSummaryAgeSec = 90,
    [int]$MaxEngineLogAgeSec = 90,
    [int]$MaxWorkerLogAgeSec = 90,
    [double]$MinAccountEquity = 1.0
)

$ErrorActionPreference = "Continue"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

$projectRoot = "C:\nt_v1"
$healthPath = Join-Path $projectRoot "logs\runtime\runtime_health_summary.json"
$engineLogPath = Join-Path $projectRoot "logs\runtime\multi5_runtime_events.jsonl"
$workerLogPath = Join-Path $projectRoot "logs\runtime\profitmax_v1_events.jsonl"
$outPath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "runtime_health_validation_latest.json" -EnsureParent

function Test-PortListening([int]$port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    return [bool]$listener
}

function To-IsoNow {
    return (Get-Date).ToUniversalTime().ToString("o")
}

function Get-TailJsonTimestampAgeSec([string]$Path) {
    if (-not (Test-Path $Path)) {
        return $null
    }
    try {
        $tailLine = Get-Content $Path -Tail 1 -Encoding UTF8
        if ([string]::IsNullOrWhiteSpace($tailLine)) {
            return $null
        }
        $obj = $tailLine | ConvertFrom-Json
        $tsText = [string]$obj.ts
        if ([string]::IsNullOrWhiteSpace($tsText)) {
            return $null
        }
        $ts = [datetimeoffset]::Parse($tsText)
        return [int](((Get-Date).ToUniversalTime() - $ts.UtcDateTime).TotalSeconds)
    } catch {
        return $null
    }
}

function Get-HealthActionClass([string[]]$Issues) {
    $immediateRestartIssues = @(
        "HEALTH_SUMMARY_MISSING",
        "HEALTH_SUMMARY_INVALID_JSON",
        "API_8100_NOT_LISTENING",
        "DASHBOARD_8788_NOT_LISTENING",
        "ENGINE_NOT_ALIVE",
        "RUNTIME_NOT_ALIVE",
        "KILL_SWITCH_ACTIVE",
        "ENGINE_RUNTIME_LOG_STALE",
        "WORKER_EVENT_LOG_STALE",
        "RUNTIME_HEALTH_VALIDATION_EXECUTION_FAILED",
        "RUNTIME_HEALTH_VALIDATION_MISSING_REPORT"
    )
    $softFailIssues = @(
        "ACCOUNT_EQUITY_TOO_LOW",
        "OPS_HEALTH_NOT_OK",
        "ENGINE_ERROR_PRESENT",
        "PORTFOLIO_SNAPSHOT_STALE",
        "PORTFOLIO_SNAPSHOT_TS_INVALID",
        "HEALTH_SUMMARY_STALE"
    )
    $noRestartIssues = @(
        "ALLOCATION_TARGET_EMPTY"
    )

    $issueSet = @($Issues | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($issueSet.Count -eq 0) {
        return "none"
    }
    foreach ($issue in $issueSet) {
        if ($immediateRestartIssues -contains $issue) {
            return "restart_immediate"
        }
    }
    $allNoRestart = $true
    foreach ($issue in $issueSet) {
        if (-not ($noRestartIssues -contains $issue)) {
            $allNoRestart = $false
            break
        }
    }
    if ($allNoRestart) {
        return "no_restart"
    }
    foreach ($issue in $issueSet) {
        if ($softFailIssues -contains $issue) {
            return "restart_soft"
        }
    }
    return "restart_immediate"
}

$issues = @()
$status = "PASS"
$health = $null
$healthAgeSec = $null
$engineLogAgeSec = Get-TailJsonTimestampAgeSec -Path $engineLogPath
$workerLogAgeSec = Get-TailJsonTimestampAgeSec -Path $workerLogPath

if (-not (Test-Path $healthPath)) {
    $issues += "HEALTH_SUMMARY_MISSING"
    $status = "FAIL"
} else {
    try {
        $health = Get-Content $healthPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        $issues += "HEALTH_SUMMARY_INVALID_JSON"
        $status = "FAIL"
    }
}

$api8100 = Test-PortListening 8100
$dash8788 = Test-PortListening 8788
if (-not $api8100) {
    $issues += "API_8100_NOT_LISTENING"
    $status = "FAIL"
}
if (-not $dash8788) {
    $issues += "DASHBOARD_8788_NOT_LISTENING"
    $status = "FAIL"
}

$snapshotAgeSec = $null
if ($health) {
    try {
        $healthTs = [datetimeoffset]::Parse([string]$health.ts)
        $healthAgeSec = [int](((Get-Date).ToUniversalTime() - $healthTs.UtcDateTime).TotalSeconds)
    } catch {
        $healthAgeSec = $null
    }

    try {
        $ts = [datetimeoffset]::Parse([string]$health.portfolio_snapshot_ts)
        $snapshotAgeSec = [int](((Get-Date).ToUniversalTime() - $ts.UtcDateTime).TotalSeconds)
    } catch {
        $issues += "PORTFOLIO_SNAPSHOT_TS_INVALID"
        if ($status -eq "PASS") { $status = "WARN" }
    }

    if (-not [bool]$health.engine_alive) {
        $issues += "ENGINE_NOT_ALIVE"
        $status = "FAIL"
    }
    if (-not [bool]$health.runtime_alive) {
        $issues += "RUNTIME_NOT_ALIVE"
        $status = "FAIL"
    }
    if ([string]$health.ops_health_status -ne "OK") {
        $issues += "OPS_HEALTH_NOT_OK"
        if ($status -eq "PASS") { $status = "WARN" }
    }
    if ([double]$health.account_equity -lt $MinAccountEquity) {
        $issues += "ACCOUNT_EQUITY_TOO_LOW"
        $status = "FAIL"
    }
    if ([bool]$health.kill_switch) {
        $issues += "KILL_SWITCH_ACTIVE"
        $status = "FAIL"
    }
    if ([int]$health.engine_error_count -gt 0) {
        $issues += "ENGINE_ERROR_PRESENT"
        if ($status -eq "PASS") { $status = "WARN" }
    }
    if ($snapshotAgeSec -ne $null -and $snapshotAgeSec -gt $MaxSnapshotAgeSec) {
        $issues += "PORTFOLIO_SNAPSHOT_STALE"
        if ($status -eq "PASS") { $status = "WARN" }
    }
    if ($healthAgeSec -ne $null -and $healthAgeSec -gt $MaxHealthSummaryAgeSec) {
        $issues += "HEALTH_SUMMARY_STALE"
        if ($status -eq "PASS") { $status = "WARN" }
    }
}

if ($engineLogAgeSec -ne $null -and $engineLogAgeSec -gt $MaxEngineLogAgeSec) {
    $issues += "ENGINE_RUNTIME_LOG_STALE"
    if ($status -eq "PASS") { $status = "WARN" }
}
if ($workerLogAgeSec -ne $null -and $workerLogAgeSec -gt $MaxWorkerLogAgeSec) {
    $issues += "WORKER_EVENT_LOG_STALE"
    if ($status -eq "PASS") { $status = "WARN" }
}

$actionClass = Get-HealthActionClass -Issues $issues

$payload = [ordered]@{
    ts = To-IsoNow
    status = $status
    action_class = $actionClass
    issues = @($issues)
    health_path = $healthPath
    api_8100_listening = [bool]$api8100
    dashboard_8788_listening = [bool]$dash8788
    health_summary_age_sec = $healthAgeSec
    portfolio_snapshot_age_sec = $snapshotAgeSec
    engine_runtime_log_age_sec = $engineLogAgeSec
    worker_event_log_age_sec = $workerLogAgeSec
    summary_mode = if ($health) { [string]$health.summary_mode } else { "-" }
    engine_alive = if ($health) { [bool]$health.engine_alive } else { $false }
    runtime_alive = if ($health) { [bool]$health.runtime_alive } else { $false }
    ops_health_status = if ($health) { [string]$health.ops_health_status } else { "-" }
    writer_symbol = if ($health) { [string]$health.writer_symbol } else { "-" }
    account_equity = if ($health) { [double]$health.account_equity } else { 0.0 }
    realized_pnl = if ($health) { [double]$health.realized_pnl } else { 0.0 }
    daily_trades = if ($health) { [int]$health.daily_trades } else { 0 }
    trade_outcomes_count = if ($health) { [int]$health.trade_outcomes_count } else { 0 }
    active_symbol_count = if ($health) { [int]$health.active_symbol_count } else { 0 }
    selected_symbol_count = if ($health) { [int]$health.selected_symbol_count } else { 0 }
    allocation_target_symbol_count = if ($health) { [int]$health.allocation_target_symbol_count } else { 0 }
    top_allocation_symbol = if ($health) { [string]$health.top_allocation_symbol } else { "-" }
    top_allocation_weight = if ($health) { [double]$health.top_allocation_weight } else { 0.0 }
}

$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $outPath -Encoding UTF8
$payload | ConvertTo-Json -Depth 6

