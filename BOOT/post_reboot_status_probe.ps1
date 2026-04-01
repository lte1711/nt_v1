param(
    [int]$InitialDelaySec = 120
)

$ErrorActionPreference = "Continue"
. "C:\next-trade-ver1.0\BOOT\report_path_resolver.ps1"

$projectRoot = "C:\next-trade-ver1.0"
$logDir = Join-Path $projectRoot "logs\service"
$outputPath = Join-Path $logDir "post_reboot_status_probe.json"
$autoBootStatusPath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "auto_boot_completion_status.json" -EnsureParent
$runtimeHealthValidationScript = Join-Path $projectRoot "BOOT\validate_runtime_health_summary.ps1"
$runtimeHealthValidationPath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "runtime_health_validation_latest.json" -EnsureParent

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Start-Sleep -Seconds $InitialDelaySec

function Test-PortListening([int]$port) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
    return [bool]$listener
}

function Get-ProcCount([string]$pattern, [string]$name = "python.exe") {
    return @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq $name -and
            $_.CommandLine -ne $null -and
            $_.CommandLine -like "*$pattern*"
        }
    ).Count
}

function Get-RootProcCount([string]$pattern, [string]$name = "python.exe") {
    $matches = @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq $name -and
            $_.CommandLine -ne $null -and
            $_.CommandLine -like "*$pattern*"
        }
    )
    $roots = @()
    foreach ($proc in $matches) {
        $parent = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $proc.ParentProcessId) -ErrorAction SilentlyContinue
        if (-not $parent -or [string]$parent.CommandLine -notlike "*$pattern*") {
            $roots += $proc
        }
    }
    return @($roots).Count
}

$payload = [ordered]@{
    ts = (Get-Date).ToString("o")
    port_3001 = Test-PortListening 3001
    port_8100 = Test-PortListening 8100
    port_8788 = Test-PortListening 8788
    engine_root_count = Get-RootProcCount "run_multi5_engine.py"
    worker_count = Get-RootProcCount "profitmax_v1_runner.py"
    runtime_guard_count = Get-ProcCount "runtime_guard.ps1" "powershell.exe"
    phase5_autoguard_count = Get-ProcCount "phase5_autoguard.ps1" "powershell.exe"
    dashboard_count = Get-RootProcCount "multi5_dashboard_server.py"
    auto_boot_status_path = $autoBootStatusPath
    auto_boot_status_exists = Test-Path $autoBootStatusPath
    auto_boot_status_raw = if (Test-Path $autoBootStatusPath) { [string](Get-Content $autoBootStatusPath -Raw -ErrorAction SilentlyContinue) } else { $null }
    runtime_health_validation_path = $runtimeHealthValidationPath
    runtime_health_validation_exists = $false
    runtime_health_validation_status = "-"
    runtime_health_validation_issues = @()
    runtime_health_validation_ts = $null
}

if (Test-Path $runtimeHealthValidationScript) {
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $runtimeHealthValidationScript | Out-Null
    } catch {}
}

if (Test-Path $runtimeHealthValidationPath) {
    $payload.runtime_health_validation_exists = $true
    try {
        $validationRaw = [string](Get-Content $runtimeHealthValidationPath -Raw -ErrorAction SilentlyContinue)
        $validationObj = $validationRaw | ConvertFrom-Json
        $payload.runtime_health_validation_status = [string]$validationObj.status
        $payload.runtime_health_validation_issues = @($validationObj.issues)
        $payload.runtime_health_validation_ts = [string]$validationObj.ts
    } catch {
        $payload.runtime_health_validation_status = "INVALID"
        $payload.runtime_health_validation_issues = @("RUNTIME_HEALTH_VALIDATION_PARSE_FAILED")
    }
}

$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $outputPath -Encoding UTF8
