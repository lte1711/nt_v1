$ErrorActionPreference = "Stop"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

$scriptPath = "C:\nt_v1\BOOT\observe_multi5_realtime.ps1"
$statusPath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "nt_phase2_realtime_observe_status.txt" -EnsureParent

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like "*observe_multi5_realtime.ps1*" -and
    $_.CommandLine -notlike "* -Command *"
}

if ($existing) {
    Write-Output "OBSERVE_ALREADY_RUNNING=YES"
    Write-Output "OBSERVE_PID_LIST=$((($existing | Select-Object -ExpandProperty ProcessId) -join ','))"
    Write-Output "OBSERVE_STATUS_FILE=$statusPath"
    exit 0
}

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$scriptPath`"",
    "-IntervalSec", "60",
    "-DurationMinutes", "480"
)
$p = Start-Process -FilePath "powershell.exe" -ArgumentList $args -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1

Write-Output "OBSERVE_START=YES"
Write-Output "OBSERVE_PID=$($p.Id)"
Write-Output "OBSERVE_STATUS_FILE=$statusPath"

