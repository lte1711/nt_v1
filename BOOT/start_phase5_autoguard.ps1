$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $projectRoot "BOOT\phase5_autoguard.ps1"
$reportResolverPath = Join-Path $projectRoot "BOOT\report_path_resolver.ps1"
$maxHealthyLogAgeSec = 120

if (Test-Path $reportResolverPath) {
    . $reportResolverPath
}

function Get-Phase5AutoguardLogPath {
    if (Get-Command Resolve-NtRoleReportFile -ErrorAction SilentlyContinue) {
        return (Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "phase5_autoguard_log.txt" -EnsureParent)
    }
    return (Join-Path $projectRoot "reports\honey_execution_reports\phase5_autoguard_log.txt")
}

function Test-HealthyAutoguardProcess($processes, [string]$logPath, [int]$maxAgeSec) {
    if (-not $processes) {
        return $false
    }
    if (-not (Test-Path $logPath)) {
        return $false
    }
    try {
        $lastWrite = (Get-Item $logPath).LastWriteTime
        $ageSec = [int]((Get-Date) - $lastWrite).TotalSeconds
        return ($ageSec -le $maxAgeSec)
    } catch {
        return $false
    }
}

$autoguardLogPath = Get-Phase5AutoguardLogPath

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like "*\phase5_autoguard.ps1*" -and
    $_.CommandLine -notlike "*start_phase5_autoguard.ps1*" -and
    $_.CommandLine -notlike "* -Command *"
}

if ($existing) {
    if (Test-HealthyAutoguardProcess -processes $existing -logPath $autoguardLogPath -maxAgeSec $maxHealthyLogAgeSec) {
        $keep = $existing | Sort-Object CreationDate -Descending | Select-Object -First 1
        $dups = @($existing | Where-Object { $_.ProcessId -ne $keep.ProcessId })
        foreach ($dup in $dups) {
            try {
                Stop-Process -Id $dup.ProcessId -Force -ErrorAction Stop
                Write-Output "PHASE5_AUTOGUARD_DUPLICATE_STOPPED_PID=$($dup.ProcessId)"
            } catch {
                Write-Output "PHASE5_AUTOGUARD_DUPLICATE_STOP_FAILED_PID=$($dup.ProcessId)"
            }
        }
        Write-Output "PHASE5_AUTOGUARD_ALREADY_RUNNING=YES"
        Write-Output "PHASE5_AUTOGUARD_PID_LIST=$($keep.ProcessId)"
        Write-Output "PHASE5_AUTOGUARD_LOG_PATH=$autoguardLogPath"
        exit 0
    }

    foreach ($proc in $existing) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Output "PHASE5_AUTOGUARD_STALE_STOPPED_PID=$($proc.ProcessId)"
        } catch {
            Write-Output "PHASE5_AUTOGUARD_STALE_STOP_FAILED_PID=$($proc.ProcessId)"
        }
    }
    Start-Sleep -Seconds 2
}

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $scriptPath,
    "-IntervalSec", "30",
    "-ObserveMinutes", "10080",
    "-WorkerStaleSec", "300"
)

$proc = Start-Process -FilePath "powershell.exe" -ArgumentList $args -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1

Write-Output "PHASE5_AUTOGUARD_START=YES"
Write-Output "PHASE5_AUTOGUARD_PID=$($proc.Id)"
Write-Output "PHASE5_AUTOGUARD_LOG_PATH=$autoguardLogPath"
