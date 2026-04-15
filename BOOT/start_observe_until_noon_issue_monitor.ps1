$scriptPath = "C:\nt_v1\tools\ops\observe_until_noon_issue_monitor.ps1"

$existing = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like "*observe_until_noon_issue_monitor.ps1*" -and
    $_.CommandLine -notlike "*start_observe_until_noon_issue_monitor.ps1*"
})

if ($existing.Count -gt 0) {
    "already_running"
    $existing | Select-Object ProcessId, Name, CommandLine
    exit 0
}

Start-Process powershell -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $scriptPath
) -WindowStyle Hidden

Start-Sleep -Seconds 2

$started = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like "*observe_until_noon_issue_monitor.ps1*" -and
    $_.CommandLine -notlike "*start_observe_until_noon_issue_monitor.ps1*"
})

if ($started.Count -gt 0) {
    "started"
    $started | Select-Object ProcessId, Name, CommandLine
    exit 0
}

"failed_to_start"
exit 1

