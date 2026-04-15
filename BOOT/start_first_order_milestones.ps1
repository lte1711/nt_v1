$ErrorActionPreference = "Stop"

$scriptPath = "C:\nt_v1\BOOT\first_order_milestone_reporter.ps1"

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like "*first_order_milestone_reporter.ps1*" -and
    $_.CommandLine -notlike "* -Command *"
}

if ($existing) {
    Write-Output "MILESTONE_REPORTER_ALREADY_RUNNING=YES"
    Write-Output "MILESTONE_REPORTER_PID_LIST=$((($existing | Select-Object -ExpandProperty ProcessId) -join ','))"
    exit 0
}

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$scriptPath`"",
    "-IntervalSec", "60",
    "-DurationMinutes", "360"
)
$p = Start-Process -FilePath "powershell.exe" -ArgumentList $args -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1

Write-Output "MILESTONE_REPORTER_START=YES"
Write-Output "MILESTONE_REPORTER_PID=$($p.Id)"

