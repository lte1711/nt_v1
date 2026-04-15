param(
    [string]$CollectionJsonlPath,
    [string]$ObserveJsonlPath,
    [string]$OutputReportPath = "",
    [string]$OutputSummaryJsonPath = ""
)

$ErrorActionPreference = "Stop"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

function Get-JsonLines {
    param([string]$Path)
    $rows = @()
    if (-not (Test-Path -LiteralPath $Path)) {
        return $rows
    }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        try {
            $rows += ($line | ConvertFrom-Json)
        } catch {
        }
    }
    return @($rows)
}

function Get-IsoDate($value) {
    if ($null -eq $value -or [string]::IsNullOrWhiteSpace([string]$value)) {
        return $null
    }
    try {
        return [datetimeoffset]::Parse([string]$value)
    } catch {
        return $null
    }
}

function Measure-UniqueCsvValues([string[]]$values) {
    $set = New-Object System.Collections.Generic.HashSet[string]
    foreach ($value in $values) {
        if ([string]::IsNullOrWhiteSpace($value)) {
            continue
        }
        foreach ($part in ($value -split ",")) {
            $trimmed = $part.Trim()
            if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
                [void]$set.Add($trimmed)
            }
        }
    }
    return @($set)
}

$reportDir = Resolve-NtRoleReportDir -RoleFolder "honey_execution_reports" -EnsureExists
if ([string]::IsNullOrWhiteSpace($OutputReportPath)) {
    $OutputReportPath = Join-Path $reportDir "runtime_12h_monitor_report.txt"
}
if ([string]::IsNullOrWhiteSpace($OutputSummaryJsonPath)) {
    $OutputSummaryJsonPath = Join-Path $reportDir "runtime_12h_monitor_summary.json"
}

$collectionRows = @(Get-JsonLines -Path $CollectionJsonlPath)
$observeRows = @(Get-JsonLines -Path $ObserveJsonlPath)

$summaryPath = "C:\nt_v1\logs\runtime\profitmax_v1_summary.json"
$healthPath = "C:\nt_v1\logs\runtime\runtime_health_summary.json"
$validationPath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "runtime_health_validation_latest.json" -EnsureParent
$tradeOutcomesPath = "C:\nt_v1\logs\runtime\trade_outcomes.json"

$summary = $null
$health = $null
$validation = $null
$tradeOutcomes = @()

if (Test-Path -LiteralPath $summaryPath) {
    try { $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json } catch {}
}
if (Test-Path -LiteralPath $healthPath) {
    try { $health = Get-Content -LiteralPath $healthPath -Raw | ConvertFrom-Json } catch {}
}
if (Test-Path -LiteralPath $validationPath) {
    try { $validation = Get-Content -LiteralPath $validationPath -Raw | ConvertFrom-Json } catch {}
}
if (Test-Path -LiteralPath $tradeOutcomesPath) {
    try { $tradeOutcomes = @(Get-Content -LiteralPath $tradeOutcomesPath -Raw | ConvertFrom-Json) } catch {}
}

$firstCollection = if ($collectionRows.Count -gt 0) { $collectionRows[0] } else { $null }
$lastCollection = if ($collectionRows.Count -gt 0) { $collectionRows[-1] } else { $null }
$firstObserve = if ($observeRows.Count -gt 0) { $observeRows[0] } else { $null }
$lastObserve = if ($observeRows.Count -gt 0) { $observeRows[-1] } else { $null }

$startTs = $null
$endTs = $null
if ($firstObserve) { $startTs = Get-IsoDate $firstObserve.ts }
if ($lastObserve) { $endTs = Get-IsoDate $lastObserve.ts }
if ($null -eq $startTs -and $firstCollection) { $startTs = Get-IsoDate $firstCollection.ts }
if ($null -eq $endTs -and $lastCollection) { $endTs = Get-IsoDate $lastCollection.ts }

$durationHours = 0.0
if ($startTs -and $endTs) {
    $durationHours = [math]::Round(($endTs - $startTs).TotalHours, 3)
}

$engineDowntimeSamples = @($collectionRows | Where-Object {
    ([int]($_.engine_root_count)) -le 0 -or -not [bool]$_.api_8100_listen
}).Count
$maxWorkerCount = if ($collectionRows.Count -gt 0) { ($collectionRows | Measure-Object -Property worker_count -Maximum).Maximum } else { 0 }
$maxOpenPositions = if ($observeRows.Count -gt 0) { ($observeRows | Measure-Object -Property OPEN_POSITIONS_COUNT -Maximum).Maximum } else { 0 }
$maxExposure = if ($observeRows.Count -gt 0) { [double](($observeRows | Measure-Object -Property TOTAL_EXPOSURE -Maximum).Maximum) } else { 0.0 }
$maxRealtimePnl = if ($observeRows.Count -gt 0) { [double](($observeRows | Measure-Object -Property REALTIME_PNL -Maximum).Maximum) } else { 0.0 }
$minRealtimePnl = if ($observeRows.Count -gt 0) { [double](($observeRows | Measure-Object -Property REALTIME_PNL -Minimum).Minimum) } else { 0.0 }

$finalOpenSymbols = @()
if ($lastObserve -and $lastObserve.OPEN_POSITION_SYMBOLS) {
    $finalOpenSymbols = @($lastObserve.OPEN_POSITION_SYMBOLS -split "," | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}
$allObservedSymbols = Measure-UniqueCsvValues -values @($observeRows | ForEach-Object { [string]$_.OPEN_POSITION_SYMBOLS })

$result = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    monitor_start_ts = if ($startTs) { $startTs.ToString("o") } else { "" }
    monitor_end_ts = if ($endTs) { $endTs.ToString("o") } else { "" }
    duration_hours = $durationHours
    collection_samples = $collectionRows.Count
    observe_samples = $observeRows.Count
    engine_downtime_samples = $engineDowntimeSamples
    max_worker_count = [int]$maxWorkerCount
    max_open_positions = [int]$maxOpenPositions
    max_total_exposure = [math]::Round($maxExposure, 6)
    realtime_pnl_min = [math]::Round($minRealtimePnl, 6)
    realtime_pnl_max = [math]::Round($maxRealtimePnl, 6)
    entry_signal_count = if ($lastObserve) { [int]$lastObserve.ENTRY_SIGNAL_COUNT } else { 0 }
    order_filled_count = if ($lastObserve) { [int]$lastObserve.ORDER_FILLED_COUNT } else { 0 }
    position_open_event_count = if ($lastObserve) { [int]$lastObserve.POSITION_OPEN_EVENT_COUNT } else { 0 }
    position_close_event_count = if ($lastObserve) { [int]$lastObserve.POSITION_CLOSE_EVENT_COUNT } else { 0 }
    final_open_positions = $finalOpenSymbols.Count
    final_open_symbols = $finalOpenSymbols
    observed_open_symbols = $allObservedSymbols
    trade_outcomes_count = @($tradeOutcomes).Count
    final_realized_pnl = if ($summary) { [double]$summary.session_realized_pnl } else { 0.0 }
    final_daily_trades = if ($summary) { [int]$summary.daily_trades } else { 0 }
    final_active_symbol_count = if ($summary) { [int]$summary.active_symbol_count } else { 0 }
    final_selected_symbol_count = if ($summary) { [int]$summary.selected_symbol_count } else { 0 }
    final_runtime_health_status = if ($validation) { [string]$validation.status } else { "-" }
    final_runtime_action_class = if ($validation) { [string]$validation.action_class } else { "-" }
    final_health_issues = @(
        if ($validation -and $null -ne $validation.issues) {
            @($validation.issues)
        }
    )
    final_engine_alive = if ($health) { [bool]$health.engine_alive } else { $false }
    final_runtime_alive = if ($health) { [bool]$health.runtime_alive } else { $false }
}

$lines = @(
    "RUNTIME_12H_MONITOR_REPORT"
    "GENERATED_AT=$($result.generated_at)"
    "MONITOR_START_TS=$($result.monitor_start_ts)"
    "MONITOR_END_TS=$($result.monitor_end_ts)"
    "DURATION_HOURS=$($result.duration_hours)"
    "COLLECTION_SAMPLES=$($result.collection_samples)"
    "OBSERVE_SAMPLES=$($result.observe_samples)"
    "ENGINE_DOWNTIME_SAMPLES=$($result.engine_downtime_samples)"
    "MAX_WORKER_COUNT=$($result.max_worker_count)"
    "MAX_OPEN_POSITIONS=$($result.max_open_positions)"
    "MAX_TOTAL_EXPOSURE=$($result.max_total_exposure)"
    "REALTIME_PNL_MIN=$($result.realtime_pnl_min)"
    "REALTIME_PNL_MAX=$($result.realtime_pnl_max)"
    "ENTRY_SIGNAL_COUNT=$($result.entry_signal_count)"
    "ORDER_FILLED_COUNT=$($result.order_filled_count)"
    "POSITION_OPEN_EVENT_COUNT=$($result.position_open_event_count)"
    "POSITION_CLOSE_EVENT_COUNT=$($result.position_close_event_count)"
    "FINAL_OPEN_POSITIONS=$($result.final_open_positions)"
    "FINAL_OPEN_SYMBOLS=$(([string]::Join(',', $result.final_open_symbols)))"
    "OBSERVED_OPEN_SYMBOLS=$(([string]::Join(',', $result.observed_open_symbols)))"
    "TRADE_OUTCOMES_COUNT=$($result.trade_outcomes_count)"
    "FINAL_REALIZED_PNL=$($result.final_realized_pnl)"
    "FINAL_DAILY_TRADES=$($result.final_daily_trades)"
    "FINAL_ACTIVE_SYMBOL_COUNT=$($result.final_active_symbol_count)"
    "FINAL_SELECTED_SYMBOL_COUNT=$($result.final_selected_symbol_count)"
    "FINAL_RUNTIME_HEALTH_STATUS=$($result.final_runtime_health_status)"
    "FINAL_RUNTIME_ACTION_CLASS=$($result.final_runtime_action_class)"
    "FINAL_HEALTH_ISSUES=$(([string]::Join(',', $result.final_health_issues)))"
    "FINAL_ENGINE_ALIVE=$($result.final_engine_alive)"
    "FINAL_RUNTIME_ALIVE=$($result.final_runtime_alive)"
)

Set-Content -LiteralPath $OutputReportPath -Value $lines -Encoding UTF8
Set-Content -LiteralPath $OutputSummaryJsonPath -Value ($result | ConvertTo-Json -Depth 6) -Encoding UTF8

Write-Output "RUNTIME_12H_REPORT_WRITTEN=YES"
Write-Output "RUNTIME_12H_REPORT_PATH=$OutputReportPath"
Write-Output "RUNTIME_12H_SUMMARY_JSON=$OutputSummaryJsonPath"

