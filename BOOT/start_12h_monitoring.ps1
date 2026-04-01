$ErrorActionPreference = "Stop"
. "C:\next-trade-ver1.0\BOOT\report_path_resolver.ps1"

$collectorScript = "C:\next-trade-ver1.0\BOOT\collect_runtime_12h.ps1"
$observeScript = "C:\next-trade-ver1.0\BOOT\observe_multi5_realtime.ps1"
$reportScript = "C:\next-trade-ver1.0\BOOT\write_12h_runtime_report.ps1"

$reportDir = Resolve-NtRoleReportDir -RoleFolder "honey_execution_reports" -EnsureExists
$collectionJsonl = Join-Path $reportDir "runtime_12h_collection.jsonl"
$collectionStatus = Join-Path $reportDir "runtime_12h_collection_status.txt"
$observeJsonl = Join-Path $reportDir "runtime_12h_observe_metrics.jsonl"
$observeStatus = Join-Path $reportDir "runtime_12h_observe_status.txt"
$finalReport = Join-Path $reportDir "runtime_12h_monitor_report.txt"
$finalSummary = Join-Path $reportDir "runtime_12h_monitor_summary.json"
$baselineJson = Join-Path $reportDir "runtime_12h_baseline.json"

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like "*collect_runtime_12h.ps1*" -and
    $_.CommandLine -notlike "* -Command *"
}
if ($existing) {
    Write-Output "RUNTIME_12H_MONITOR_ALREADY_RUNNING=YES"
    Write-Output "RUNTIME_12H_MONITOR_PID_LIST=$((($existing | Select-Object -ExpandProperty ProcessId) -join ','))"
    Write-Output "RUNTIME_12H_REPORT_DIR=$reportDir"
    exit 0
}

$baseline = [ordered]@{
    captured_at = (Get-Date).ToString("o")
    runtime_api = $null
}
try {
    $baseline.runtime_api = Invoke-RestMethod -Uri "http://127.0.0.1:8788/api/runtime" -Method Get -TimeoutSec 10
} catch {
    $baseline.runtime_api = @{ error = "$_" }
}
Set-Content -LiteralPath $baselineJson -Value ($baseline | ConvertTo-Json -Depth 8) -Encoding UTF8

$collectorArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $collectorScript,
    "-IntervalSec", "60",
    "-DurationMinutes", "720",
    "-OutputJsonlPath", $collectionJsonl,
    "-OutputStatusPath", $collectionStatus
)
$observeArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $observeScript,
    "-IntervalSec", "60",
    "-DurationMinutes", "720",
    "-OutputJsonlPath", $observeJsonl,
    "-OutputStatusPath", $observeStatus
)

$collectorProc = Start-Process -FilePath "powershell.exe" -ArgumentList $collectorArgs -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1
$observeProc = Start-Process -FilePath "powershell.exe" -ArgumentList $observeArgs -WindowStyle Hidden -PassThru

$orchestrator = @"
`$ErrorActionPreference = 'Stop'
`$deadline = (Get-Date).AddHours(12.5)
do {
  Start-Sleep -Seconds 30
  `$collectDone = (Test-Path -LiteralPath '$collectionStatus') -and ((Get-Content -LiteralPath '$collectionStatus' -Raw) -match 'COLLECTION_STATUS=COMPLETED')
  `$observeDone = (Test-Path -LiteralPath '$observeStatus') -and ((Get-Content -LiteralPath '$observeStatus' -Raw) -match 'OBSERVE_STATUS=COMPLETED')
  if (`$collectDone -and `$observeDone) { break }
} while ((Get-Date) -lt `$deadline)
& '$reportScript' -CollectionJsonlPath '$collectionJsonl' -ObserveJsonlPath '$observeJsonl' -OutputReportPath '$finalReport' -OutputSummaryJsonPath '$finalSummary' | Out-Null
"@
$watcherProc = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-Command",$orchestrator) -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1

Write-Output "RUNTIME_12H_MONITOR_START=YES"
Write-Output "RUNTIME_12H_COLLECTION_PID=$($collectorProc.Id)"
Write-Output "RUNTIME_12H_OBSERVE_PID=$($observeProc.Id)"
Write-Output "RUNTIME_12H_WATCHER_PID=$($watcherProc.Id)"
Write-Output "RUNTIME_12H_BASELINE=$baselineJson"
Write-Output "RUNTIME_12H_COLLECTION_STATUS=$collectionStatus"
Write-Output "RUNTIME_12H_OBSERVE_STATUS=$observeStatus"
Write-Output "RUNTIME_12H_REPORT_PATH=$finalReport"
Write-Output "RUNTIME_12H_SUMMARY_JSON=$finalSummary"
