$ErrorActionPreference = "Stop"

$projectRoot = "C:\next-trade-ver1.0"
. (Join-Path $projectRoot "BOOT\report_path_resolver.ps1")
$startEngineScript = Join-Path $projectRoot "BOOT\start_engine.ps1"
$startRuntimeGuardScript = Join-Path $projectRoot "BOOT\start_runtime_guard.ps1"
$startAutoguardScript = Join-Path $projectRoot "BOOT\start_phase5_autoguard.ps1"
$startDashboardScript = Join-Path $projectRoot "BOOT\start_dashboard_8788.ps1"
$postRebootProbeScript = Join-Path $projectRoot "BOOT\post_reboot_status_probe.ps1"
$validateHealthScript = Join-Path $projectRoot "BOOT\validate_runtime_health_summary.ps1"
$pruneWorkerLocksScript = Join-Path $projectRoot "BOOT\prune_stale_worker_locks.ps1"
$postRebootProbePath = Join-Path $projectRoot "logs\service\post_reboot_status_probe.json"
$validateHealthPath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "runtime_health_validation_latest.json" -EnsureParent

function Get-RestartTargets {
    Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -eq "powershell.exe" -and $_.CommandLine -match "phase5_autoguard\.ps1|runtime_guard\.ps1") -or
        ($_.Name -eq "python.exe" -and $_.CommandLine -match "run_multi5_engine\.py|profitmax_v1_runner\.py|multi5_dashboard_server\.py")
    }
}

function Stop-RestartTargets {
    $targets = @(Get-RestartTargets)
    foreach ($target in $targets) {
        try {
            Stop-Process -Id $target.ProcessId -Force -ErrorAction Stop
        } catch {
        }
    }
}

function Wait-UntilStopped([int]$TimeoutSec = 20) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        $remaining = @(Get-RestartTargets)
        if ($remaining.Count -eq 0) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return (@(Get-RestartTargets).Count -eq 0)
}

function Get-EngineRoots {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -like "*run_multi5_engine.py*"
    })
}

function Wait-ForPortListening([int]$Port, [int]$TimeoutSec = 20) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Get-FileTimestampUtc([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    return (Get-Item -LiteralPath $Path).LastWriteTimeUtc
}

function Wait-ForFreshFile([string]$Path, $PreviousWriteUtc = $null, [int]$TimeoutSec = 20) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        if (Test-Path -LiteralPath $Path) {
            $current = (Get-Item -LiteralPath $Path).LastWriteTimeUtc
            if ($null -eq $PreviousWriteUtc -or $current -gt $PreviousWriteUtc) {
                return $true
            }
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

Stop-RestartTargets
$stopped = Wait-UntilStopped

if (-not $stopped) {
    Write-Output "ENGINE_RESTART_STOP_PHASE=TIMEOUT"
    Write-Output "REMAINING_PID_LIST=$(((@(Get-RestartTargets) | Select-Object -ExpandProperty ProcessId) -join ','))"
    exit 1
}

Start-Sleep -Seconds 2
if (Test-Path $pruneWorkerLocksScript) {
    & $pruneWorkerLocksScript | Out-Null
}
$previousHealthWriteUtc = Get-FileTimestampUtc $validateHealthPath
$previousProbeWriteUtc = Get-FileTimestampUtc $postRebootProbePath
Start-Sleep -Seconds 1
& $startEngineScript | Out-Null
Start-Sleep -Seconds 2
& $startRuntimeGuardScript | Out-Null
Start-Sleep -Seconds 1
& $startAutoguardScript | Out-Null
Start-Sleep -Seconds 1
& $startDashboardScript | Out-Null
if (-not (Wait-ForPortListening -Port 8100 -TimeoutSec 30)) {
    Write-Output "ENGINE_RESTART_API_8100=TIMEOUT"
    exit 1
}
if (-not (Wait-ForPortListening -Port 8788 -TimeoutSec 30)) {
    Write-Output "ENGINE_RESTART_DASHBOARD_8788=TIMEOUT"
    exit 1
}

if (Test-Path $validateHealthScript) {
    & $validateHealthScript | Out-Null
    if (-not (Wait-ForFreshFile -Path $validateHealthPath -PreviousWriteUtc $previousHealthWriteUtc -TimeoutSec 20)) {
        Write-Output "ENGINE_RESTART_HEALTH_VALIDATION=STALE"
        exit 1
    }
}
if (Test-Path $postRebootProbeScript) {
    & $postRebootProbeScript -InitialDelaySec 0 | Out-Null
    if (-not (Wait-ForFreshFile -Path $postRebootProbePath -PreviousWriteUtc $previousProbeWriteUtc -TimeoutSec 20)) {
        Write-Output "ENGINE_RESTART_POST_REBOOT_PROBE=STALE"
        exit 1
    }
}

$engineRoots = @(Get-EngineRoots)
if ($engineRoots.Count -eq 0) {
    Write-Output "ENGINE_RESTART=NO"
    exit 1
}

Write-Output "ENGINE_RESTART=YES"
Write-Output "ENGINE_PID_LIST=$((($engineRoots | Select-Object -ExpandProperty ProcessId) -join ','))"
