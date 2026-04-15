param(
    [int]$IntervalSec = 30,
    [int]$ObserveMinutes = 480,
    [int]$StaleSec = 300
)

$ErrorActionPreference = "Continue"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

$projectRoot = "C:\nt_v1"
$pythonExe = Join-Path $projectRoot "venv\Scripts\python.exe"
$workerScript = Join-Path $projectRoot "tools\ops\profitmax_v1_runner.py"
$workerLogPath = "C:\nt_v1\logs\runtime\profitmax_v1_events.jsonl"
$workerSummaryPath = "C:\nt_v1\logs\runtime\profitmax_v1_summary.json"
$dashboardRuntimeApi = "http://127.0.0.1:8788/api/runtime"
$guardLog = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "worker_watchdog_log.txt" -EnsureParent
$endAt = (Get-Date).AddMinutes($ObserveMinutes)

New-Item -ItemType Directory -Force -Path (Split-Path $guardLog -Parent) | Out-Null

function Write-GuardLog([string]$line) {
    $ts = (Get-Date).ToString("s")
    Add-Content -Path $guardLog -Value "$ts $line"
}

function Get-RootEngineCount {
    $roots = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*run_multi5_engine.py*"
    })
    return $roots.Count
}

function Get-Workers {
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*profitmax_v1_runner.py*"
    })
}

function Get-WorkerLogAgeSec {
    if (-not (Test-Path $workerLogPath)) { return 999999 }
    $line = Get-Content $workerLogPath -Tail 1 -ErrorAction SilentlyContinue
    if (-not $line) { return 999999 }
    try {
        $obj = $line | ConvertFrom-Json
        $tsVal = [string]$obj.ts
        if (-not $tsVal) { return 999999 }
        $parsed = [datetimeoffset]::Parse($tsVal)
        return [int](((Get-Date).ToUniversalTime() - $parsed.UtcDateTime).TotalSeconds)
    } catch {
        return 999999
    }
}

function Resolve-Symbol {
    try {
        $snap = Invoke-RestMethod -Uri $dashboardRuntimeApi -Method Get -TimeoutSec 10
        if ($snap.position_status -eq "OPEN" -and $snap.current_position_symbol -and $snap.current_position_symbol -ne "-") {
            return [string]$snap.current_position_symbol
        }
        if ($snap.current_selected_symbol -and $snap.current_selected_symbol -ne "-") {
            return [string]$snap.current_selected_symbol
        }
        if ($snap.selected_symbol -and $snap.selected_symbol -ne "-") {
            return [string]$snap.selected_symbol
        }
    } catch {}
    return "BTCUSDT"
}

function Restart-Worker([string]$symbol) {
    $workers = Get-Workers
    if ($workers.Count -gt 0) {
        $pids = ($workers | Select-Object -ExpandProperty ProcessId) -join ","
        Write-GuardLog "STALE_OR_MISSING_WORKER kill_old_pids=$pids"
        foreach ($w in $workers) {
            try { Stop-Process -Id $w.ProcessId -Force } catch {}
        }
        Start-Sleep -Seconds 2
    }

    $args = @(
        "`"$workerScript`"",
        "--profile", "TESTNET_INTRADAY_SCALP",
        "--session-hours", "2.0",
        "--base-qty", "0.004",
        "--symbol", $symbol,
        "--evidence-path", "`"$workerLogPath`"",
        "--summary-path", "`"$workerSummaryPath`""
    )
    try {
        $proc = Start-Process -FilePath $pythonExe -ArgumentList $args -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
        Start-Sleep -Seconds 2
        Write-GuardLog "WORKER_RESTARTED pid=$($proc.Id) symbol=$symbol"
    } catch {
        Write-GuardLog "WORKER_RESTART_FAILED error=$($_.Exception.Message)"
    }
}

Write-GuardLog "WORKER_GUARD_START interval_sec=$IntervalSec observe_minutes=$ObserveMinutes stale_sec=$StaleSec"

while ((Get-Date) -lt $endAt) {
    $rootCount = Get-RootEngineCount
    if ($rootCount -eq 0) {
        Write-GuardLog "SKIP root_engine_missing"
        Start-Sleep -Seconds $IntervalSec
        continue
    }

    $workers = Get-Workers
    $logAge = Get-WorkerLogAgeSec

    if ($workers.Count -eq 0) {
        $symbol = Resolve-Symbol
        Write-GuardLog "WORKER_MISSING log_age_sec=$logAge symbol=$symbol"
        Restart-Worker -symbol $symbol
    } elseif ($logAge -gt $StaleSec) {
        $symbol = Resolve-Symbol
        Write-GuardLog "WORKER_STALE log_age_sec=$logAge symbol=$symbol"
        Restart-Worker -symbol $symbol
    } else {
        $pids = ($workers | Select-Object -ExpandProperty ProcessId) -join ","
        Write-GuardLog "WORKER_OK pids=$pids log_age_sec=$logAge"
    }

    Start-Sleep -Seconds $IntervalSec
}

Write-GuardLog "WORKER_GUARD_END"


