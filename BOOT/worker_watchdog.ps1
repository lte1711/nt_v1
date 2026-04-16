param(
    [int]$IntervalSec = 30,
    [int]$ObserveMinutes = 10080,
    [int]$StaleSec = 300
)

$ErrorActionPreference = "Continue"
$projectRoot = Split-Path -Parent $PSScriptRoot
$bootRoot = Join-Path $projectRoot "BOOT"
. (Join-Path $bootRoot "report_path_resolver.ps1")
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = Join-Path $projectRoot "venv\Scripts\python.exe"
}
$workerScript = Join-Path $projectRoot "tools\ops\profitmax_v1_runner.py"
$workerLogPath = Join-Path $projectRoot "logs\runtime\profitmax_v1_events.jsonl"
$workerSummaryPath = Join-Path $projectRoot "logs\runtime\profitmax_v1_summary.json"
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

function Resolve-RecoverySymbols {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8100/api/v1/investor/positions" -Method Get -TimeoutSec 10
        $symbols = @(
            $resp.positions |
            Where-Object {
                $_.symbol -and ([math]::Abs([double]($_.positionAmt)) -gt 0)
            } |
            ForEach-Object { [string]$_.symbol }
        )
        if ($symbols.Count -gt 0) {
            return @($symbols | Select-Object -Unique)
        }
    } catch {}

    try {
        $snap = Invoke-RestMethod -Uri $dashboardRuntimeApi -Method Get -TimeoutSec 10
        if ($snap.position_status -eq "OPEN" -and $snap.current_position_symbol -and $snap.current_position_symbol -ne "-") {
            $positionSymbols = @(
                ([string]$snap.current_position_symbol).Split(",") |
                ForEach-Object { $_.Trim().ToUpperInvariant() } |
                Where-Object { $_ }
            )
            if ($positionSymbols.Count -gt 0) {
                return @($positionSymbols | Select-Object -Unique)
            }
        }
    } catch {}

    return @()
}

function Restart-Worker([string]$symbol) {
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
        $symbols = @(Resolve-RecoverySymbols)
        if ($symbols.Count -eq 0) {
            Write-GuardLog "WORKER_MISSING_NO_OPEN_POSITIONS log_age_sec=$logAge action=skip_restart"
        } else {
            Write-GuardLog "WORKER_MISSING log_age_sec=$logAge symbols=$($symbols -join ',')"
            foreach ($symbol in $symbols) {
                Restart-Worker -symbol $symbol
            }
        }
    } elseif ($logAge -gt $StaleSec) {
        $symbols = @(Resolve-RecoverySymbols)
        $pids = ($workers | Select-Object -ExpandProperty ProcessId) -join ","
        if ($symbols.Count -eq 0) {
            Write-GuardLog "WORKER_STALE_NO_OPEN_POSITIONS log_age_sec=$logAge kill_old_pids=$pids action=stop_without_restart"
        } else {
            Write-GuardLog "WORKER_STALE log_age_sec=$logAge symbols=$($symbols -join ',') kill_old_pids=$pids"
        }
        foreach ($w in $workers) {
            try { Stop-Process -Id $w.ProcessId -Force } catch {}
        }
        Start-Sleep -Seconds 2
        foreach ($symbol in $symbols) {
            Restart-Worker -symbol $symbol
        }
    } else {
        $pids = ($workers | Select-Object -ExpandProperty ProcessId) -join ","
        Write-GuardLog "WORKER_OK pids=$pids log_age_sec=$logAge"
    }

    Start-Sleep -Seconds $IntervalSec
}

Write-GuardLog "WORKER_GUARD_END"


