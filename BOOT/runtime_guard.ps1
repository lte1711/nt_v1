param(
    [int]$IntervalSec = 30,
    [int]$ObserveMinutes = 480
)

$ErrorActionPreference = "Continue"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

$bootRoot = "C:\nt_v1\BOOT"
$projectRoot = "C:\nt_v1"
$guardLog = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "runtime_guard_log.txt" -EnsureParent
$endAt = (Get-Date).AddMinutes($ObserveMinutes)

New-Item -ItemType Directory -Force -Path (Split-Path $guardLog -Parent) | Out-Null

function Write-GuardLog([string]$line) {
    $ts = (Get-Date).ToString("s")
    Add-Content -Path $guardLog -Value "$ts $line"
}

function Get-RootEngine {
    $engines = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*run_multi5_engine.py*"
    })
    $roots = @()
    foreach ($e in $engines) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($e.ParentProcessId)" -ErrorAction SilentlyContinue
        if (-not $parent -or [string]$parent.CommandLine -notlike "*run_multi5_engine.py*") {
            $roots += $e
        }
    }
    return @($roots)
}

function Get-OrphanWorkers {
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*profitmax_v1_runner.py*"
    }
}

function Stop-DuplicateRootEngines([array]$roots) {
    $items = @($roots | Sort-Object CreationDate -Descending)
    if ($items.Count -le 1) {
        return @($items)
    }
    $keep = $items | Select-Object -First 1
    $drop = @($items | Select-Object -Skip 1)
    foreach ($root in $drop) {
        try {
            Stop-Process -Id $root.ProcessId -Force -ErrorAction Stop
            Write-GuardLog "ROOT_DUPLICATE_STOPPED pid=$($root.ProcessId)"
        } catch {
            Write-GuardLog "ROOT_DUPLICATE_STOP_FAILED pid=$($root.ProcessId)"
        }
    }
    Start-Sleep -Seconds 1
    return @(Get-RootEngine)
}

Write-GuardLog "GUARD_START interval_sec=$IntervalSec observe_minutes=$ObserveMinutes"

while ((Get-Date) -lt $endAt) {
    $roots = @(Get-RootEngine)
    if ($roots.Count -gt 1) {
        $rpids = ($roots | Select-Object -ExpandProperty ProcessId) -join ","
        Write-GuardLog "ROOT_DUPLICATES_DETECTED count=$($roots.Count) pids=$rpids"
        $roots = @(Stop-DuplicateRootEngines -roots $roots)
    }
    if ($roots.Count -eq 0) {
        $workers = @(Get-OrphanWorkers)
        if ($workers.Count -gt 0) {
            $wpids = ($workers | Select-Object -ExpandProperty ProcessId) -join ","
            Write-GuardLog "ROOT_MISSING orphan_workers_detected=$($workers.Count) pids=$wpids"
            foreach ($w in $workers) {
                try { Stop-Process -Id $w.ProcessId -Force } catch {}
            }
            Start-Sleep -Seconds 2
        } else {
            Write-GuardLog "ROOT_MISSING orphan_workers_detected=0"
        }

        try { & "$bootRoot\clear_lock.ps1" | Out-Null } catch {}
        Start-Sleep -Seconds 1

        try {
            $startOut = & "$bootRoot\start_engine.ps1" 2>&1
            $startSummary = ($startOut | Out-String).Trim().Replace("`r"," ").Replace("`n"," | ")
            Write-GuardLog "ENGINE_RESTART_TRIGGERED result=$startSummary"
        } catch {
            Write-GuardLog "ENGINE_RESTART_FAILED error=$($_.Exception.Message)"
        }
    } else {
        $rpids = ($roots | Select-Object -ExpandProperty ProcessId) -join ","
        Write-GuardLog "ROOT_OK count=$($roots.Count) pids=$rpids"
    }

    Start-Sleep -Seconds $IntervalSec
}

Write-GuardLog "GUARD_END"


