param()

$ErrorActionPreference = 'Stop'
$before = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*multi5_dashboard_server.py*'
})
$beforeListeners = @(Get-NetTCPConnection -State Listen -LocalPort 8788 -ErrorAction SilentlyContinue)
$beforeApi = 'ERROR'
try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8788/api/runtime' -TimeoutSec 10
    $beforeApi = [string][int]$resp.StatusCode
} catch {
    $beforeApi = 'ERROR:' + $_.Exception.Message
}

$hygiene = powershell -NoProfile -ExecutionPolicy Bypass -File 'C:\nt_v1\BOOT\dashboard_duplicate_process_hygiene.ps1' -Execute | Out-String
Start-Sleep -Seconds 8

$after = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -like '*multi5_dashboard_server.py*'
})
$afterListeners = @(Get-NetTCPConnection -State Listen -LocalPort 8788 -ErrorAction SilentlyContinue)
$afterApi = 'ERROR'
try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8788/api/runtime' -TimeoutSec 15
    $afterApi = [string][int]$resp.StatusCode
} catch {
    $afterApi = 'ERROR:' + $_.Exception.Message
}

[pscustomobject]@{
    before_process_count = $before.Count
    before_listener_count = $beforeListeners.Count
    before_listener_pid = (@($beforeListeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ',')
    before_api = $beforeApi
    hygiene_output = $hygiene.Trim()
    after_process_count = $after.Count
    after_listener_count = $afterListeners.Count
    after_listener_pid = (@($afterListeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ',')
    after_api = $afterApi
} | ConvertTo-Json -Depth 5

