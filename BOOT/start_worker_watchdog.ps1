$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $projectRoot "BOOT\worker_watchdog.ps1"

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like "*worker_watchdog.ps1*" -and
    $_.CommandLine -notlike "* -Command *"
}

if ($existing) {
    Write-Output "WORKER_WATCHDOG_ALREADY_RUNNING=YES"
    Write-Output "WORKER_WATCHDOG_PID_LIST=$((($existing | Select-Object -ExpandProperty ProcessId) -join ','))"
    exit 0
}

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$scriptPath`"",
    "-IntervalSec", "30",
    "-ObserveMinutes", "480",
    "-StaleSec", "300"
)

$proc = Start-Process -FilePath "powershell.exe" -ArgumentList $args -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1

Write-Output "WORKER_WATCHDOG_START=YES"
Write-Output "WORKER_WATCHDOG_PID=$($proc.Id)"

