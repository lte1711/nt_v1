param(
    [switch]$Execute
)

$ErrorActionPreference = 'Stop'
$projectRoot = 'C:\next-trade-ver1.0'
$engineRoot = Join-Path $projectRoot 'NEXT-TRADE'
$dashboardStartScript = Join-Path $projectRoot 'BOOT\start_dashboard_8788.ps1'

$procs = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*multi5_dashboard_server.py*'
})

$preferred = $procs | Where-Object { $_.CommandLine -like '*\\.venv\\Scripts\\python.exe*' } | Select-Object -First 1
if (-not $preferred -and $procs.Count -gt 0) {
    $preferred = $procs | Select-Object -First 1
}

$stopped = @()
$started = $false

if ($Execute) {
    foreach ($p in $procs) {
        try {
            Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
            $stopped += $p.ProcessId
        } catch {
        }
    }
    Start-Sleep -Seconds 2
    & $dashboardStartScript | Out-Null
    $started = $true
    Start-Sleep -Seconds 5
}

$after = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*multi5_dashboard_server.py*'
})
$listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8788 -ErrorAction SilentlyContinue)
$apiStatus = 'ERROR'
try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8788/api/runtime' -TimeoutSec 10
    $apiStatus = [string][int]$resp.StatusCode
} catch {
    $apiStatus = 'ERROR:' + $_.Exception.Message
}

[pscustomobject]@{
    execute = [bool]$Execute
    before_process_count = $procs.Count
    preferred_before_pid = if ($preferred) { $preferred.ProcessId } else { $null }
    stopped_pids = @($stopped) -join ','
    restarted = $started
    after_process_count = $after.Count
    listener_count_8788 = $listeners.Count
    listener_pids_8788 = (@($listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ',')
    api_status = $apiStatus
} | ConvertTo-Json -Depth 4
