param(
    [int]$DurationSec = 60,
    [int]$IntervalSec = 5
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Virtualenv python not found: $pythonExe"
}

function Invoke-PythonCheck([string]$Code) {
    try {
        $output = & $pythonExe -c $Code 2>$null
        return (($output | Out-String).Trim() -eq "OK")
    } catch {
        return $false
    }
}

function Test-TcpPortOpen([int]$Port) {
    $code = "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',$Port)); s.close(); print('OK')"
    return (Invoke-PythonCheck -Code $code)
}

function Test-HttpOk([string]$Url) {
    $code = "import urllib.request; r=urllib.request.urlopen('$Url', timeout=4); print('OK' if r.status==200 else 'FAIL')"
    return (Invoke-PythonCheck -Code $code)
}

function Test-EngineProcess {
    $engineProcesses = @(Get-Process -Name python -ErrorAction SilentlyContinue)
    return ($engineProcesses.Count -ge 1)
}

$deadline = (Get-Date).AddSeconds($DurationSec)
$results = @()

do {
    $apiTcp = Test-TcpPortOpen -Port 8100
    $dashboardTcp = Test-TcpPortOpen -Port 8788
    $apiHttp = if ($apiTcp) { Test-HttpOk -Url "http://127.0.0.1:8100/api/v1/ops/health" } else { $false }
    $dashboardHttp = if ($dashboardTcp) { Test-HttpOk -Url "http://127.0.0.1:8788/api/health" } else { $false }
    $engineOk = Test-EngineProcess

    $row = [pscustomobject]@{
        ts = (Get-Date).ToString("s")
        api_tcp = $apiTcp
        api_http = $apiHttp
        dashboard_tcp = $dashboardTcp
        dashboard_http = $dashboardHttp
        engine_process = $engineOk
    }
    $results += $row
    Write-Host ("{0} api_tcp={1} api_http={2} dashboard_tcp={3} dashboard_http={4} engine_process={5}" -f `
        $row.ts, $row.api_tcp, $row.api_http, $row.dashboard_tcp, $row.dashboard_http, $row.engine_process)

    Start-Sleep -Seconds $IntervalSec
} while ((Get-Date) -lt $deadline)

$failed = @($results | Where-Object {
    -not $_.api_tcp -or -not $_.api_http -or -not $_.dashboard_tcp -or -not $_.dashboard_http -or -not $_.engine_process
})

if ($failed.Count -gt 0) {
    throw "Smoke test failed. Unhealthy samples: $($failed.Count)"
}

Write-Host "Smoke test passed for $DurationSec seconds." -ForegroundColor Green
