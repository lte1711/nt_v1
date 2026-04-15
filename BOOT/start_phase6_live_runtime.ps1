$ErrorActionPreference = "Stop"

$scriptPath = "C:\nt_v1\BOOT\phase6_live_runtime_collector.ps1"

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like "*phase6_live_runtime_collector.ps1*" -and
    $_.CommandLine -notlike "* -Command *"
}

if ($existing) {
    Write-Output "PHASE6_COLLECTOR_ALREADY_RUNNING=YES"
    Write-Output "PHASE6_COLLECTOR_PID_LIST=$((($existing | Select-Object -ExpandProperty ProcessId) -join ','))"
    exit 0
}

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$scriptPath`"",
    "-IntervalSec", "60",
    "-DurationMinutes", "360"
)

$proc = Start-Process -FilePath "powershell.exe" -ArgumentList $args -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1
Write-Output "PHASE6_COLLECTOR_START=YES"
Write-Output "PHASE6_COLLECTOR_PID=$($proc.Id)"

