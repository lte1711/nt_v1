$ErrorActionPreference = "Stop"

$projectRoot = "C:\next-trade-ver1.0"
$runtimeDir = Join-Path $projectRoot "logs\runtime"
$serviceDir = Join-Path $projectRoot "logs\service"
$reportsDir = Join-Path $projectRoot "reports"

function Get-ResetTargets {
    Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -eq "powershell.exe" -and $_.CommandLine -match "phase5_autoguard\.ps1|runtime_guard\.ps1|start_dashboard_8788\.ps1") -or
        ($_.Name -eq "python.exe" -and $_.CommandLine -match "run_multi5_engine\.py|profitmax_v1_runner\.py|multi5_dashboard_server\.py")
    }
}

function Clear-DirectoryContents([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    Get-ChildItem -LiteralPath $Path -Force | ForEach-Object {
        Remove-Item -LiteralPath $_.FullName -Recurse -Force
    }
}

$targets = @(Get-ResetTargets)
foreach ($target in $targets) {
    try {
        Stop-Process -Id $target.ProcessId -Force -ErrorAction Stop
    } catch {
    }
}

Start-Sleep -Seconds 3
Clear-DirectoryContents $runtimeDir
Clear-DirectoryContents $serviceDir
Clear-DirectoryContents $reportsDir

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $runtimeDir "strategy_signals") | Out-Null
New-Item -ItemType Directory -Force -Path $serviceDir | Out-Null
New-Item -ItemType Directory -Force -Path $reportsDir | Out-Null

Write-Output "STATE_RESET=YES"
