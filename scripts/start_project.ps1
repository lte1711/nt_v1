$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$bootRoot = Join-Path $projectRoot "BOOT"

$steps = @(
    @{ Name = "API"; Script = Join-Path $bootRoot "start_api_8100_safe.ps1" },
    @{ Name = "Dashboard"; Script = Join-Path $bootRoot "start_dashboard_8788.ps1" },
    @{ Name = "Engine"; Script = Join-Path $bootRoot "start_engine.ps1" }
)

foreach ($step in $steps) {
    if (-not (Test-Path $step.Script)) {
        throw "Missing startup script: $($step.Script)"
    }
}

foreach ($step in $steps) {
    Write-Host "=== Starting $($step.Name) ===" -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File $step.Script
    if ($LASTEXITCODE -ne 0) {
        throw "$($step.Name) startup failed with exit code $LASTEXITCODE"
    }
}

Write-Host "NEXT-TRADE startup chain completed." -ForegroundColor Green
