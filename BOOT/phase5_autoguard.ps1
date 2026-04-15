param(
    [int]$IntervalSec = 30,
    [int]$ObserveMinutes = 10080,
    [int]$WorkerStaleSec = 300,
    [int]$WarmWorkerTargetCount = 3,
    [int]$DashboardRestartCooldownSec = 90,
    [int]$HealthRestartCooldownSec = 600,
    [int]$WarnRestartThreshold = 3
)

$ErrorActionPreference = "Continue"
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $projectRoot "BOOT\report_path_resolver.ps1")
. (Join-Path $projectRoot "BOOT\common_process_helpers.ps1")

$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = Join-Path $projectRoot "venv\Scripts\python.exe"
}

$dashboardScript = Join-Path $projectRoot "tools\dashboard\multi5_dashboard_server.py"
$dashboardStartScript = Join-Path $projectRoot "BOOT\start_dashboard_8788.ps1"
$dashboardValidationScript = Join-Path $projectRoot "BOOT\monitor_dashboard_runtime_validation.ps1"
$runtimeHealthValidationScript = Join-Path $projectRoot "BOOT\validate_runtime_health_summary.ps1"
$runtimeHealthValidationPath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "runtime_health_validation_latest.json" -EnsureParent
$restartEngineScript = Join-Path $projectRoot "BOOT\restart_engine.ps1"
$healthRestartStatePath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "runtime_health_restart_state.json" -EnsureParent
$apiStartScript = Join-Path $projectRoot "BOOT\start_api_8100_safe.ps1"
$workerScript = Join-Path $projectRoot "tools\ops\profitmax_v1_runner.py"
$workerLogPath = Join-Path $projectRoot "logs\runtime\profitmax_v1_events.jsonl"
$workerSummaryPath = Join-Path $projectRoot "logs\runtime\profitmax_v1_summary.json"
$workerStrategyUnit = "momentum_intraday_v1"
$workerStrategySignalDir = Join-Path $projectRoot "logs\runtime\strategy_signals"
$workerTakeProfitPct = "0.012"
$workerStopLossPct = "0.006"
$workerMaxPositions = 1
$phase5Metrics = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "nt_phase5_multi_symbol_metrics.jsonl" -EnsureParent
$phase5Status = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "nt_phase5_multi_symbol_status.txt" -EnsureParent
$autoguardLog = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "phase5_autoguard_log.txt" -EnsureParent
$endAt = (Get-Date).AddMinutes($ObserveMinutes)

New-Item -ItemType Directory -Force -Path (Split-Path $autoguardLog -Parent) | Out-Null
$script:LastDashboardStartAt = $null
$script:LastHealthRestartAt = $null
$script:ConsecutiveHealthWarnCount = 0

$script:ImmediateRestartIssues = @(
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

$script:SoftFailIssues = @(
    "ACCOUNT_EQUITY_TOO_LOW",
    "OPS_HEALTH_NOT_OK",
    "ENGINE_ERROR_PRESENT",
    "PORTFOLIO_SNAPSHOT_STALE",
    "PORTFOLIO_SNAPSHOT_TS_INVALID",
    "HEALTH_SUMMARY_STALE"
)

$script:NoRestartIssues = @(
    "ALLOCATION_TARGET_EMPTY"
)

function Log([string]$line) {
    Add-Content -Path $autoguardLog -Value ("{0} {1}" -f (Get-Date).ToString("s"), $line)
}

function Get-LatestSelectedSymbols {
    $runtimePath = Join-Path $projectRoot "logs\runtime\multi5_runtime_events.jsonl"
    if (-not (Test-Path $runtimePath)) {
        return @()
    }
    $lastLine = Get-Content $runtimePath -Tail 1 -ErrorAction SilentlyContinue
    if (-not $lastLine) {
        return @()
    }
    try {
        $row = $lastLine | ConvertFrom-Json
        return @($row.selected_symbols_batch)
    } catch {
        return @()
    }
}

function Ensure-Api {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8100/api/v1/ops/health" -TimeoutSec 5
        if ($resp.StatusCode -eq 200) {
            return
        }
    } catch {
    }
    & $apiStartScript | Out-Null
    Log "START api_8100"
}

function Ensure-Dashboard {
    $listenerPids = @(Get-ListenerPidsByPort -Port 8788)
    if ($listenerPids.Count -ge 1) {
        return
    }
    $ageSec = -1
    if ($script:LastDashboardStartAt) {
        $ageSec = [int]((Get-Date) - $script:LastDashboardStartAt).TotalSeconds
        if ($ageSec -lt $DashboardRestartCooldownSec) {
            Log "DASHBOARD_RESTART_COOLDOWN age_sec=$ageSec"
            return
        }
    }
    & $dashboardStartScript | Out-Null
    $script:LastDashboardStartAt = Get-Date
    Log "START dashboard_8788"
}

function Ensure-Engine {
    $engineRoots = @(Get-PythonProcessesByCommandPatterns -Patterns @("*run_multi5_engine.py*"))
    if ($engineRoots.Count -ge 1) {
        return
    }
    & (Join-Path $projectRoot "BOOT\start_engine.ps1") | Out-Null
    Log "START engine"
}

function Get-HealthActionClass {
    param([string[]]$Issues)

    if ((@($Issues | Where-Object { $_ -in $script:ImmediateRestartIssues }).Count) -ge 1) {
        return "restart_immediate"
    }
    if ((@($Issues | Where-Object { $_ -in $script:SoftFailIssues }).Count) -ge 1) {
        return "restart_soft"
    }
    if ((@($Issues | Where-Object { $_ -in $script:NoRestartIssues }).Count) -ge 1) {
        return "no_restart"
    }
    return "no_restart"
}

function Invoke-HealthDrivenRestart {
    param(
        [string]$ActionClass,
        [string[]]$Issues
    )

    $now = Get-Date
    if ($script:LastHealthRestartAt) {
        $ageSec = [int]($now - $script:LastHealthRestartAt).TotalSeconds
        if ($ageSec -lt $HealthRestartCooldownSec) {
            Log "HEALTH_RESTART_COOLDOWN_ACTIVE age_sec=$ageSec action_class=$ActionClass"
            return
        }
    }

    $script:LastHealthRestartAt = $now
    $joinedIssues = (@($Issues) -join ",")
    Log "HEALTH_RESTART_TRIGGER action_class=$ActionClass issues=$joinedIssues"
    & $restartEngineScript | Out-Null
}

function Apply-RuntimeHealthPolicy {
    param([string[]]$Issues)

    $actionClass = Get-HealthActionClass -Issues $Issues
    if ($actionClass -eq "restart_immediate") {
        Invoke-HealthDrivenRestart -ActionClass $actionClass -Issues $Issues
        return $actionClass
    }
    if ($actionClass -eq "restart_soft") {
        $script:ConsecutiveHealthWarnCount += 1
        if ($script:ConsecutiveHealthWarnCount -ge $WarnRestartThreshold) {
            Invoke-HealthDrivenRestart -ActionClass $actionClass -Issues $Issues
        }
        return $actionClass
    }
    $script:ConsecutiveHealthWarnCount = 0
    return $actionClass
}

while ((Get-Date) -lt $endAt) {
    Ensure-Api
    Ensure-Dashboard
    Ensure-Engine

    $issues = @()
    if (-not (Test-Path $runtimeHealthValidationScript)) {
        $issues += "RUNTIME_HEALTH_VALIDATION_MISSING_REPORT"
    } else {
        try {
            & $runtimeHealthValidationScript | Out-Null
        } catch {
            $issues += "RUNTIME_HEALTH_VALIDATION_EXECUTION_FAILED"
        }
    }

    if ((Get-ListenerPidsByPort -Port 8100).Count -eq 0) {
        $issues += "API_8100_NOT_LISTENING"
    }
    if ((Get-ListenerPidsByPort -Port 8788).Count -eq 0) {
        $issues += "DASHBOARD_8788_NOT_LISTENING"
    }
    if (-not (Test-Path $workerLogPath)) {
        $issues += "WORKER_EVENT_LOG_STALE"
    }

    $workerSymbols = Get-LatestSelectedSymbols
    foreach ($workerRole in $workerSymbols) {
        Log "WARM_WORKER_SELECTED role=$workerRole"
    }

    $actionClass = Apply-RuntimeHealthPolicy -Issues $issues
    $state = @{
        ts = (Get-Date).ToString("s")
        action_class = $actionClass
        issues = @($issues)
        warm_worker_target_count = $WarmWorkerTargetCount
        selected_symbols = @($workerSymbols)
        dashboard_script = $dashboardScript
        dashboard_validation_script = $dashboardValidationScript
        runtime_health_validation_path = $runtimeHealthValidationPath
        worker_script = $workerScript
        worker_summary_path = $workerSummaryPath
        worker_strategy_unit = $workerStrategyUnit
        worker_strategy_signal_dir = $workerStrategySignalDir
        worker_take_profit_pct = $workerTakeProfitPct
        worker_stop_loss_pct = $workerStopLossPct
        worker_max_positions = $workerMaxPositions
        phase5_metrics = $phase5Metrics
        phase5_status = $phase5Status
        restart_engine_script = $restartEngineScript
        health_restart_cooldown_sec = $HealthRestartCooldownSec
    } | ConvertTo-Json -Depth 4
    Set-Content -Path $healthRestartStatePath -Value $state -Encoding UTF8

    Start-Sleep -Seconds $IntervalSec
}
