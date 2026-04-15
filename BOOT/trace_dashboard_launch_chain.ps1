param(
    [int]$SampleSeconds = 12
)

$ErrorActionPreference = 'Stop'
$startScript = 'C:\nt_v1\BOOT\start_dashboard_8788.ps1'

Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*multi5_dashboard_server.py*'
} | ForEach-Object {
    try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}
}
Start-Sleep -Seconds 2

$timeline = @()
$launch = powershell -NoProfile -ExecutionPolicy Bypass -File $startScript | Out-String
for ($i = 0; $i -lt $SampleSeconds; $i++) {
    $rows = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and $_.CommandLine -like '*multi5_dashboard_server.py*'
    } | Select-Object ProcessId, ParentProcessId, CommandLine)
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort 8788 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
    $timeline += [pscustomobject]@{
        sample_index = $i
        process_count = $rows.Count
        process_ids = (@($rows | ForEach-Object { $_.ProcessId }) -join ',')
        parent_ids = (@($rows | ForEach-Object { $_.ParentProcessId }) -join ',')
        listener_count = $listeners.Count
        listener_pids = (@($listeners) -join ',')
    }
    Start-Sleep -Seconds 1
}

$apiStatus = 'ERROR'
try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8788/api/runtime' -TimeoutSec 15
    $apiStatus = [string][int]$resp.StatusCode
} catch {
    $apiStatus = 'ERROR:' + $_.Exception.Message
}

$result = [pscustomobject]@{
    launch_output = $launch.Trim()
    api_status = $apiStatus
    timeline = $timeline
}
$result | ConvertTo-Json -Depth 6

