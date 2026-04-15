$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$bootRoot = Join-Path $projectRoot "BOOT"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$dashboardScript = Join-Path $projectRoot "tools\dashboard\multi5_dashboard_server.py"
$apiCmd = Join-Path $projectRoot "tools\ops\run_api_8100.cmd"
$startEngineScript = Join-Path $bootRoot "start_engine.ps1"

. (Join-Path $bootRoot "common_process_helpers.ps1")

if (-not (Test-Path $pythonExe)) {
    throw "Virtualenv python not found: $pythonExe"
}

function Wait-ForPortListening([int]$Port, [int]$TimeoutSec = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        $listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($listener) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Ensure-ApiStarted {
    if ((Get-ListenerPidsByPort -Port 8100).Count -ge 1) {
        Write-Host "API already listening on 8100" -ForegroundColor Yellow
        return
    }
    if (-not (Test-Path $apiCmd)) {
        throw "Missing API launch command: $apiCmd"
    }
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $apiCmd -WindowStyle Hidden | Out-Null
    if (-not (Wait-ForPortListening -Port 8100 -TimeoutSec 30)) {
        throw "API did not start listening on port 8100"
    }
    Write-Host "API listening on 8100" -ForegroundColor Green
}

function Ensure-DashboardStarted {
    if ((Get-ListenerPidsByPort -Port 8788).Count -ge 1) {
        Write-Host "Dashboard already listening on 8788" -ForegroundColor Yellow
        return
    }
    Start-Process -FilePath $pythonExe -ArgumentList $dashboardScript -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null
    if (-not (Wait-ForPortListening -Port 8788 -TimeoutSec 30)) {
        throw "Dashboard did not start listening on port 8788"
    }
    $deadline = (Get-Date).AddSeconds(45)
    $lastError = $null
    do {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8788/api/runtime" -TimeoutSec 12
            if ([int]$resp.StatusCode -eq 200) {
                Write-Host "Dashboard listening on 8788" -ForegroundColor Green
                return
            }
            $lastError = "Dashboard health probe returned status $($resp.StatusCode)"
        } catch {
            $lastError = $_.Exception.Message
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    if ($lastError) {
        throw "Dashboard health probe failed: $lastError"
    }
    throw "Dashboard health probe failed"
}

function Ensure-EngineStarted {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $startEngineScript | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Engine startup script failed with exit code $LASTEXITCODE"
    }
    Start-Sleep -Seconds 3
    $engineProcesses = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -match "run_multi5_engine\.py"
    })
    if ($engineProcesses.Count -lt 1) {
        throw "Engine process was not detected after startup"
    }
    Write-Host "Engine process detected" -ForegroundColor Green
}

Write-Host "=== Starting API ===" -ForegroundColor Cyan
Ensure-ApiStarted

Write-Host "=== Starting Dashboard ===" -ForegroundColor Cyan
Ensure-DashboardStarted

Write-Host "=== Starting Engine ===" -ForegroundColor Cyan
Ensure-EngineStarted

Write-Host "NEXT-TRADE startup chain completed." -ForegroundColor Green
