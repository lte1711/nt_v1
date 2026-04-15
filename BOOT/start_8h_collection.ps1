$ErrorActionPreference = "Stop"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

$collector = "C:\nt_v1\BOOT\collect_runtime_8h.ps1"
$statusFile = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "nt_phase2_8h_live_collection_status.txt" -EnsureParent

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like "*collect_runtime_8h.ps1*" -and
    $_.CommandLine -notlike "* -Command *"
}

if ($existing) {
    $pids = ($existing | Select-Object -ExpandProperty ProcessId) -join ","
    Write-Output "COLLECTION_ALREADY_RUNNING=YES"
    Write-Output "COLLECTION_PID_LIST=$pids"
    Write-Output "COLLECTION_STATUS_FILE=$statusFile"
    exit 0
}

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$collector`"",
    "-IntervalSec", "60",
    "-DurationMinutes", "480"
)

$proc = Start-Process -FilePath "powershell.exe" -ArgumentList $args -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1

Write-Output "COLLECTION_START=YES"
Write-Output "COLLECTION_PID=$($proc.Id)"
Write-Output "COLLECTION_STATUS_FILE=$statusFile"

