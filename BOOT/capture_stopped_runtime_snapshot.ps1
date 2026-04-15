param(
    [string]$RootPath = "C:\nt_v1\reports",
    [string]$DateString = "",
    [string]$TimeString = "",
    [switch]$AssumeStopped
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DateString)) {
    $DateString = Get-Date -Format "yyyy-MM-dd"
}
if ([string]::IsNullOrWhiteSpace($TimeString)) {
    $TimeString = Get-Date -Format "HHmmss"
}

$sourceFolder = Join-Path $RootPath "honey_execution_reports"
$dailyHoneyFolder = Join-Path (Join-Path $RootPath $DateString) "honey_execution_reports"
$snapshotFolder = Join-Path $dailyHoneyFolder ("stopped_runtime_snapshot_" + $TimeString)

$snapshotFiles = @(
    "runtime_guard_log.txt",
    "phase5_autoguard_log.txt",
    "nt_phase5_multi_symbol_metrics.jsonl",
    "nt_phase5_multi_symbol_status.txt",
    "worker_watchdog_log.txt",
    "nt_phase5_portfolio_observe_15m.txt",
    "nt_phase5_portfolio_observe_30m.txt",
    "nt_phase5_portfolio_observe_60m.txt",
    "nt_phase5_portfolio_observe_3h.txt",
    "nt_phase5_portfolio_observe_6h.txt",
    "nt_phase5_portfolio_observe_24h.txt",
    "nt_phase5_portfolio_observe_24h_final.txt"
)

$pythonProcesses = @(Get-Process python -ErrorAction SilentlyContinue)
$runtimeStopped = $AssumeStopped.IsPresent -or ($pythonProcesses.Count -eq 0)

if (-not $runtimeStopped) {
    [pscustomobject]@{
        snapshot_created = $false
        reason = "RUNTIME_NOT_STOPPED"
        python_process_count = $pythonProcesses.Count
        snapshot_folder = $snapshotFolder
    } | ConvertTo-Json -Depth 3
    exit 0
}

if (-not (Test-Path -LiteralPath $dailyHoneyFolder)) {
    New-Item -ItemType Directory -Path $dailyHoneyFolder -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $snapshotFolder)) {
    New-Item -ItemType Directory -Path $snapshotFolder -Force | Out-Null
}

$copied = New-Object System.Collections.Generic.List[object]
foreach ($file in $snapshotFiles) {
    $src = Join-Path $sourceFolder $file
    $dst = Join-Path $snapshotFolder $file
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $copied.Add([pscustomobject]@{
            file_name = $file
            source_path = $src
            target_path = $dst
        }) | Out-Null
    }
}

$reportPath = Join-Path $snapshotFolder "STOPPED_RUNTIME_SNAPSHOT_REPORT.txt"
$lines = @()
$lines += "SNAPSHOT_CREATED = YES"
$lines += "SNAPSHOT_FOLDER = $snapshotFolder"
$lines += "SNAPSHOT_TS = $DateString $TimeString"
$lines += "COPIED_FILE_COUNT = $($copied.Count)"
$lines += "PYTHON_PROCESS_COUNT_AT_CAPTURE = $($pythonProcesses.Count)"
$lines | Set-Content -Path $reportPath -Encoding UTF8

[pscustomobject]@{
    snapshot_created = $true
    snapshot_folder = $snapshotFolder
    copied_file_count = $copied.Count
    report_path = $reportPath
} | ConvertTo-Json -Depth 3


