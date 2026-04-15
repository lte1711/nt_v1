param(
    [int]$LookbackLines = 400,
    [int]$RecentMinutes = 60,
    [int]$ChurnThreshold = 3
)

$ErrorActionPreference = 'Stop'
. 'C:\nt_v1\BOOT\report_path_resolver.ps1'

$logPath = Resolve-NtRoleReportFile -RoleFolder 'honey_execution_reports' -FileName 'phase5_autoguard_log.txt'
$reportPath = Resolve-NtRoleReportFile -RoleFolder 'honey_execution_reports' -FileName 'dashboard_churn_monitor_latest.json' -EnsureParent

$rows = @()
if (Test-Path $logPath) {
    $rows = @(Get-Content $logPath -Tail $LookbackLines)
}

$cutoff = (Get-Date).AddMinutes(-$RecentMinutes)
$dashboardStarts = @()
$cooldownEvents = @()
foreach ($line in $rows) {
    if ($line -match '^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s+(.*)$') {
        $ts = [datetime]::ParseExact($matches[1], 'yyyy-MM-ddTHH:mm:ss', $null)
        $msg = $matches[2]
        if ($ts -ge $cutoff) {
            if ($msg -like '*START dashboard_8788*') { $dashboardStarts += $line }
            if ($msg -like '*DASHBOARD_RESTART_COOLDOWN_ACTIVE*') { $cooldownEvents += $line }
        }
    }
}

$apiStatus = 'ERROR'
$dashboardProcessCount = -1
$dashboardListenerCount = -1
$singleListenerHealth = $false
try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8788/api/runtime' -TimeoutSec 10
    $apiStatus = [string][int]$resp.StatusCode
    $json = $resp.Content | ConvertFrom-Json
    $dashboardProcessCount = [int]$json.dashboard_process_count
    $dashboardListenerCount = [int]$json.dashboard_listener_count
    $singleListenerHealth = [bool]$json.dashboard_single_listener_health
} catch {
    $apiStatus = 'ERROR:' + $_.Exception.Message
}

$result = [pscustomobject]@{
    ts = (Get-Date).ToString('o')
    log_path = $logPath
    lookback_lines = $LookbackLines
    recent_minutes = $RecentMinutes
    dashboard_start_events = $dashboardStarts.Count
    cooldown_events = $cooldownEvents.Count
    churn_confirmed = ($dashboardStarts.Count -ge $ChurnThreshold)
    dashboard_api_status = $apiStatus
    dashboard_process_count = $dashboardProcessCount
    dashboard_listener_count = $dashboardListenerCount
    dashboard_single_listener_health = $singleListenerHealth
}

$result | ConvertTo-Json -Depth 4 | Set-Content -Path $reportPath -Encoding UTF8
$result | ConvertTo-Json -Depth 4

