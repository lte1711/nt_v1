$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$bootRoot = Join-Path $projectRoot "BOOT"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$dashboardScript = Join-Path $projectRoot "tools\dashboard\multi5_dashboard_server.py"
$apiScript = Join-Path $projectRoot "tools\ops\run_api_8100.py"
$startApiScript = Join-Path $bootRoot "start_api_8100_safe.ps1"
$startDashboardScript = Join-Path $bootRoot "start_dashboard_8788.ps1"
$startEngineScript = Join-Path $bootRoot "start_engine.ps1"

. (Join-Path $bootRoot "common_process_helpers.ps1")

if (-not (Test-Path $pythonExe)) {
    throw "Virtualenv python not found: $pythonExe"
}

function Resolve-ApiPythonExe {
    $venvCfg = Join-Path $projectRoot ".venv\pyvenv.cfg"
    if (Test-Path $venvCfg) {
        $homeLine = Get-Content $venvCfg | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
        if ($homeLine) {
            $homeValue = ($homeLine -split "=", 2)[1].Trim()
            $candidate = Join-Path $homeValue "python.exe"
            if (Test-Path $candidate) {
                return $candidate
            }
        }
    }
    return $pythonExe
}

function Invoke-BootScript([string]$ScriptPath, [int]$TimeoutSec = 60) {
    if (-not (Test-Path $ScriptPath)) {
        throw "Missing boot script: $ScriptPath"
    }

    $job = Start-Job -ScriptBlock {
        param($Path)
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Path 2>&1
    } -ArgumentList $ScriptPath

    try {
        if (-not (Wait-Job -Job $job -Timeout $TimeoutSec)) {
            Stop-Job -Job $job -ErrorAction SilentlyContinue | Out-Null
            throw "Boot script timed out: $ScriptPath"
        }
        $output = @(Receive-Job -Job $job -Keep)
        return [string]($output -join "`n")
    } finally {
        Remove-Job -Job $job -ErrorAction SilentlyContinue | Out-Null
    }
}

function Test-TcpPortOpen([int]$Port, [int]$TimeoutMs = 1000) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-ForPortListening([int]$Port, [int]$TimeoutSec = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        if (Test-TcpPortOpen -Port $Port -TimeoutMs 1000) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Test-HttpOk([string]$Url, [int]$TimeoutSec = 8) {
    try {
        $status = & curl.exe -s -o NUL -w "%{http_code}" --max-time $TimeoutSec $Url
        return ($LASTEXITCODE -eq 0 -and "$status".Trim() -eq "200")
    } catch {
        return $false
    }
}

function Test-ApiHealthy([int]$TimeoutSec = 4) {
    foreach ($url in @(
        "http://127.0.0.1:8100/api/status",
        "http://127.0.0.1:8100/openapi.json"
    )) {
        if (Test-HttpOk -Url $url -TimeoutSec $TimeoutSec) {
            return $true
        }
    }
    return $false
}

function Stop-ApiProcesses {
    $apiProcesses = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and (
            $_.CommandLine -match "run_api_8100\.py" -or
            $_.CommandLine -match "next_trade\.api\.app:app" -or
            $_.CommandLine -match "uvicorn.*8100"
        )
    })
    foreach ($proc in @($apiProcesses | Sort-Object ProcessId -Descending)) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        } catch {
        }
    }
}

function Get-DashboardProcesses {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -match "multi5_dashboard_server\.py"
    })
}

function Stop-DashboardProcesses {
    $dashboardProcesses = @(Get-DashboardProcesses)
    foreach ($proc in @($dashboardProcesses | Sort-Object ProcessId -Descending)) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        } catch {
        }
    }
}

function Ensure-ApiStarted {
    $bootOutput = Invoke-BootScript -ScriptPath $startApiScript -TimeoutSec 45
    $deadline = (Get-Date).AddSeconds(30)
    do {
        if (Test-ApiHealthy -TimeoutSec 4) {
            if ($bootOutput -match "API_8100_ALREADY_RUNNING=YES") {
                Write-Host "API already listening on 8100" -ForegroundColor Yellow
            } else {
                Write-Host "API listening on 8100" -ForegroundColor Green
            }
            return
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    throw "API health probe failed. Boot output: $bootOutput"
}

function Ensure-DashboardStarted {
    $dashboardProcesses = @(Get-DashboardProcesses)
    if ((Test-TcpPortOpen -Port 8788 -TimeoutMs 1000) -and (Test-HttpOk -Url "http://127.0.0.1:8788/api/health" -TimeoutSec 6) -and $dashboardProcesses.Count -eq 1) {
        Write-Host "Dashboard already listening on 8788" -ForegroundColor Yellow
        return
    }
    if ($dashboardProcesses.Count -gt 0 -or (Test-TcpPortOpen -Port 8788 -TimeoutMs 1000)) {
        Stop-DashboardProcesses
        Start-Sleep -Seconds 2
    }
    Start-Process -FilePath $pythonExe -ArgumentList $dashboardScript -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null
    $deadline = (Get-Date).AddSeconds(45)
    do {
        if (Test-HttpOk -Url "http://127.0.0.1:8788/api/health" -TimeoutSec 8) {
            Write-Host "Dashboard listening on 8788" -ForegroundColor Green
            return
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    throw "Dashboard health probe failed"
}

function Ensure-EngineStarted {
    $bootOutput = [string](& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $startEngineScript 2>&1 | Out-String)

    $deadline = (Get-Date).AddSeconds(45)
    do {
        $engineProcesses = @(Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq "python.exe" -and $_.CommandLine -match "run_multi5_engine\.py"
        })
        if ($engineProcesses.Count -ge 1) {
            if ($bootOutput -match "ENGINE_ALREADY_RUNNING=YES") {
                Write-Host "Engine process already detected" -ForegroundColor Yellow
            } else {
                Write-Host "Engine process detected" -ForegroundColor Green
            }
            return
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    if ($engineProcesses.Count -lt 1) {
        throw "Engine process was not detected after startup. Boot output: $bootOutput"
    }
}

Write-Host "=== Starting API ===" -ForegroundColor Cyan
Ensure-ApiStarted

Write-Host "=== Starting Dashboard ===" -ForegroundColor Cyan
Ensure-DashboardStarted

Write-Host "=== Starting Engine ===" -ForegroundColor Cyan
Ensure-EngineStarted

Write-Host "NEXT-TRADE startup chain completed." -ForegroundColor Green
