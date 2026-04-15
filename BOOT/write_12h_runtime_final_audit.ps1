param(
    [string]$CollectionStatusPath = "",
    [string]$ObserveStatusPath = "",
    [string]$CollectionJsonlPath = "",
    [string]$ObserveJsonlPath = "",
    [string]$OutputReportPath = "",
    [string]$OutputSummaryJsonPath = ""
)

$ErrorActionPreference = "Stop"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

function Read-KeyValueFile {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $map
    }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $idx = $line.IndexOf("=")
        if ($idx -lt 0) {
            continue
        }
        $key = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim()
        if (-not [string]::IsNullOrWhiteSpace($key)) {
            $map[$key] = $value
        }
    }
    return $map
}

function Get-JsonLines {
    param([string]$Path)
    $rows = @()
    if (-not (Test-Path -LiteralPath $Path)) {
        return $rows
    }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
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

function Read-JsonFileWithRetry {
    param(
        [string]$Path,
        [int]$Attempts = 5,
        [int]$DelayMs = 400
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    for ($i = 0; $i -lt $Attempts; $i++) {
        try {
            $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
            if ([string]::IsNullOrWhiteSpace($raw)) {
                return $null
            }
            return ($raw | ConvertFrom-Json)
        } catch {
            if ($i -ge ($Attempts - 1)) {
                return $null
            }
            Start-Sleep -Milliseconds $DelayMs
        }
    }
    return $null
}

function Normalize-Array {
    param($Value)
    if ($null -eq $Value) {
        return @()
    }
    if ($Value -is [System.Array]) {
        return $Value
    }
    if (($Value -is [System.Collections.IEnumerable]) -and -not ($Value -is [string])) {
        return @($Value)
    }
    return @($Value)
}

function Get-IsoDate {
    param($Value)
    if ($null -eq $Value -or [string]::IsNullOrWhiteSpace([string]$Value)) {
        return $null
    }
    try {
        return [datetimeoffset]::Parse([string]$Value)
    } catch {
        return $null
    }
}

function Get-DoubleValue {
    param($Value)
    try {
        return [double]$Value
    } catch {
        return 0.0
    }
}

function Get-IntValue {
    param($Value)
    try {
        return [int]$Value
    } catch {
        return 0
    }
}

function Measure-MaxGapSec {
    param([object[]]$Rows)
    $maxGap = 0
    $prevTs = $null
    foreach ($row in $Rows) {
        $ts = Get-IsoDate $row.ts
        if ($null -eq $ts) {
            continue
        }
        if ($prevTs -ne $null) {
            $gap = [int][math]::Round(($ts - $prevTs).TotalSeconds)
            if ($gap -gt $maxGap) {
                $maxGap = $gap
            }
        }
        $prevTs = $ts
    }
    return $maxGap
}

function Get-LastTimestampGapSec {
    param(
        $EndTs,
        $LastTs
    )
    if ($null -eq $EndTs -or $null -eq $LastTs) {
        return $null
    }
    return [int][math]::Round(($EndTs - $LastTs).TotalSeconds)
}

function Get-CountByPattern {
    param(
        [string]$Path,
        [string]$Pattern
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return 0
    }
    return @(Select-String -Path $Path -Pattern $Pattern -Encoding UTF8 -ErrorAction SilentlyContinue).Count
}

function Get-LastMatchLine {
    param(
        [string]$Path,
        [string]$Pattern
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return ""
    }
    $match = Select-String -Path $Path -Pattern $Pattern -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 1
    if ($null -eq $match) {
        return ""
    }
    return [string]$match.Line
}

$reportDir = Resolve-NtRoleReportDir -RoleFolder "honey_execution_reports" -EnsureExists
if ([string]::IsNullOrWhiteSpace($CollectionStatusPath)) {
    $CollectionStatusPath = Join-Path $reportDir "runtime_12h_collection_status.txt"
}
if ([string]::IsNullOrWhiteSpace($ObserveStatusPath)) {
    $ObserveStatusPath = Join-Path $reportDir "runtime_12h_observe_status.txt"
}
if ([string]::IsNullOrWhiteSpace($CollectionJsonlPath)) {
    $CollectionJsonlPath = Join-Path $reportDir "runtime_12h_collection.jsonl"
}
if ([string]::IsNullOrWhiteSpace($ObserveJsonlPath)) {
    $ObserveJsonlPath = Join-Path $reportDir "runtime_12h_observe_metrics.jsonl"
}
if ([string]::IsNullOrWhiteSpace($OutputReportPath)) {
    $OutputReportPath = Join-Path $reportDir "runtime_12h_final_audit_report.txt"
}
if ([string]::IsNullOrWhiteSpace($OutputSummaryJsonPath)) {
    $OutputSummaryJsonPath = Join-Path $reportDir "runtime_12h_final_audit_summary.json"
}

$monitorReportScript = "C:\nt_v1\BOOT\write_12h_runtime_report.ps1"
$healthValidationScript = "C:\nt_v1\BOOT\validate_runtime_health_summary.ps1"
$monitorReportPath = Join-Path $reportDir "runtime_12h_monitor_report.txt"
$monitorSummaryJsonPath = Join-Path $reportDir "runtime_12h_monitor_summary.json"
$healthValidationPath = Join-Path $reportDir "runtime_health_validation_latest.json"
$guardLogPath = Join-Path $reportDir "runtime_guard_log.txt"
$autoguardLogPath = Join-Path $reportDir "phase5_autoguard_log.txt"
$restartStatePath = Join-Path $reportDir "runtime_health_restart_state.json"
$summaryPath = "C:\nt_v1\logs\runtime\profitmax_v1_summary.json"
$healthPath = "C:\nt_v1\logs\runtime\runtime_health_summary.json"
$tradeOutcomesPath = "C:\nt_v1\logs\runtime\trade_outcomes.json"
$engineStdoutPath = "C:\nt_v1\logs\engine_stdout_.log"
$engineErrorPath = "C:\nt_v1\logs\engine_error_.log"

& $healthValidationScript | Out-Null
& $monitorReportScript -CollectionJsonlPath $CollectionJsonlPath -ObserveJsonlPath $ObserveJsonlPath -OutputReportPath $monitorReportPath -OutputSummaryJsonPath $monitorSummaryJsonPath | Out-Null

$collectionStatus = Read-KeyValueFile -Path $CollectionStatusPath
$observeStatus = Read-KeyValueFile -Path $ObserveStatusPath
$collectionRows = @(Get-JsonLines -Path $CollectionJsonlPath)
$observeRows = @(Get-JsonLines -Path $ObserveJsonlPath)

$monitorSummary = $null
$validation = $null
$summary = $null
$health = $null
$tradeOutcomes = @()
$restartState = $null

if (Test-Path -LiteralPath $monitorSummaryJsonPath) {
    $monitorSummary = Read-JsonFileWithRetry -Path $monitorSummaryJsonPath
}
if (Test-Path -LiteralPath $healthValidationPath) {
    $validation = Read-JsonFileWithRetry -Path $healthValidationPath
}
if (Test-Path -LiteralPath $summaryPath) {
    $summary = Read-JsonFileWithRetry -Path $summaryPath
}
if (Test-Path -LiteralPath $healthPath) {
    $health = Read-JsonFileWithRetry -Path $healthPath
}
if (Test-Path -LiteralPath $tradeOutcomesPath) {
    $tradeOutcomes = Normalize-Array (Read-JsonFileWithRetry -Path $tradeOutcomesPath)
}
if (Test-Path -LiteralPath $restartStatePath) {
    $restartState = Read-JsonFileWithRetry -Path $restartStatePath
}

$collectionStartTs = Get-IsoDate $collectionStatus["COLLECTION_STARTED_AT"]
$collectionEndTs = Get-IsoDate $collectionStatus["COLLECTION_ENDED_AT"]
$observeStartTs = Get-IsoDate $observeStatus["OBSERVE_STARTED_AT"]
$collectionLastTs = if ($collectionRows.Count -gt 0) { Get-IsoDate $collectionRows[-1].ts } else { $null }
$observeLastTs = if ($observeRows.Count -gt 0) { Get-IsoDate $observeRows[-1].ts } else { $null }

$collectionMaxGapSec = Measure-MaxGapSec -Rows $collectionRows
$observeMaxGapSec = Measure-MaxGapSec -Rows $observeRows
$collectionEndGapSec = Get-LastTimestampGapSec -EndTs $collectionEndTs -LastTs $collectionLastTs
$observeEndGapSec = Get-LastTimestampGapSec -EndTs $collectionEndTs -LastTs $observeLastTs

$expectedDurationMin = Get-IntValue $collectionStatus["COLLECTION_DURATION_MIN"]
$expectedSamples = 0
if ($expectedDurationMin -gt 0) {
    $expectedSamples = $expectedDurationMin
}

$collectionSamples = $collectionRows.Count
$observeSamples = $observeRows.Count
$collectionCoveragePct = if ($expectedSamples -gt 0) { [math]::Round(($collectionSamples / $expectedSamples) * 100.0, 2) } else { 0.0 }
$observeCoveragePct = if ($expectedSamples -gt 0) { [math]::Round(($observeSamples / $expectedSamples) * 100.0, 2) } else { 0.0 }

$summaryTradeCount = if ($summary) { Get-IntValue $summary.daily_trades } else { 0 }
$summaryPnl = if ($summary) { Get-DoubleValue $summary.session_realized_pnl } else { 0.0 }
$tradeOutcomesCount = @($tradeOutcomes).Count
$tradeOutcomesPnlRaw = 0.0
foreach ($row in @($tradeOutcomes)) {
    if ($null -eq $row) {
        continue
    }
    $tradeOutcomesPnlRaw += Get-DoubleValue $row.pnl
}
$tradeOutcomesPnl = [math]::Round($tradeOutcomesPnlRaw, 6)
$tradeCountDiff = $summaryTradeCount - $tradeOutcomesCount
$tradePnlDiff = [math]::Round(($summaryPnl - $tradeOutcomesPnl), 6)

$restartTriggeredCount = Get-CountByPattern -Path $guardLogPath -Pattern "RESTART_TRIGGERED"
$orphanDetectedCount = Get-CountByPattern -Path $guardLogPath -Pattern "orphan_workers_detected="
$placeholderCount = Get-CountByPattern -Path $engineStdoutPath -Pattern "Portfolio state evaluation: \{'status': 'placeholder', 'state': 'unknown'\}"
$placeholderLastLine = Get-LastMatchLine -Path $engineStdoutPath -Pattern "Portfolio state evaluation: \{'status': 'placeholder', 'state': 'unknown'\}"
$engineErrorLineCount = if (Test-Path -LiteralPath $engineErrorPath) { @(Get-Content -LiteralPath $engineErrorPath -Encoding UTF8 | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }).Count } else { 0 }
$healthPolicyFailSoftCount = Get-CountByPattern -Path $autoguardLogPath -Pattern "HEALTH_POLICY_FAIL_SOFT"
$healthValidationFailCount = Get-CountByPattern -Path $autoguardLogPath -Pattern "RUNTIME_HEALTH_VALIDATION status=FAIL"
$healthValidationWarnCount = Get-CountByPattern -Path $autoguardLogPath -Pattern "RUNTIME_HEALTH_VALIDATION status=WARN"

$issues = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

if (($collectionStatus["COLLECTION_STATUS"]) -ne "COMPLETED") {
    [void]$issues.Add("COLLECTION_STATUS_NOT_COMPLETED")
}
if ($collectionSamples -lt 680) {
    [void]$issues.Add("COLLECTION_SAMPLE_COUNT_TOO_LOW")
} elseif ($collectionSamples -lt 700) {
    [void]$warnings.Add("COLLECTION_SAMPLE_COUNT_BORDERLINE")
}
if ($observeSamples -lt 680) {
    [void]$issues.Add("OBSERVE_SAMPLE_COUNT_TOO_LOW")
} elseif ($observeSamples -lt 700) {
    [void]$warnings.Add("OBSERVE_SAMPLE_COUNT_BORDERLINE")
}
if ($collectionMaxGapSec -gt 180) {
    [void]$issues.Add("COLLECTION_TIMELINE_GAP_DETECTED")
} elseif ($collectionMaxGapSec -gt 90) {
    [void]$warnings.Add("COLLECTION_TIMELINE_GAP_ELEVATED")
}
if ($observeMaxGapSec -gt 180) {
    [void]$issues.Add("OBSERVE_TIMELINE_GAP_DETECTED")
} elseif ($observeMaxGapSec -gt 90) {
    [void]$warnings.Add("OBSERVE_TIMELINE_GAP_ELEVATED")
}
if ($collectionEndGapSec -ne $null -and $collectionEndGapSec -gt 180) {
    [void]$issues.Add("COLLECTION_END_COVERAGE_TOO_SHORT")
} elseif ($collectionEndGapSec -ne $null -and $collectionEndGapSec -gt 90) {
    [void]$warnings.Add("COLLECTION_END_COVERAGE_BORDERLINE")
}
if ($observeEndGapSec -ne $null -and $observeEndGapSec -gt 180) {
    [void]$issues.Add("OBSERVE_END_COVERAGE_TOO_SHORT")
} elseif ($observeEndGapSec -ne $null -and $observeEndGapSec -gt 90) {
    [void]$warnings.Add("OBSERVE_END_COVERAGE_BORDERLINE")
}
if ($validation -and [string]$validation.status -eq "FAIL") {
    [void]$issues.Add("FINAL_HEALTH_VALIDATION_FAIL")
} elseif ($validation -and [string]$validation.status -eq "WARN") {
    [void]$warnings.Add("FINAL_HEALTH_VALIDATION_WARN")
}
if ($tradeCountDiff -ne 0) {
    [void]$issues.Add("TRADE_COUNT_MISMATCH")
}
if ([math]::Abs($tradePnlDiff) -gt 0.0001) {
    [void]$issues.Add("REALIZED_PNL_MISMATCH")
}
if ($restartTriggeredCount -ge 3) {
    [void]$issues.Add("EXCESSIVE_RUNTIME_RESTARTS")
} elseif ($restartTriggeredCount -ge 1) {
    [void]$warnings.Add("RUNTIME_RESTARTS_RECORDED")
}
if ($orphanDetectedCount -gt 0) {
    [void]$warnings.Add("ORPHAN_WORKERS_DETECTED_DURING_SESSION")
}
if ($healthValidationFailCount -gt 0) {
    [void]$warnings.Add("AUTOGUARD_HEALTH_FAIL_EVENTS_RECORDED")
}
if ($healthValidationWarnCount -gt 0) {
    [void]$warnings.Add("AUTOGUARD_HEALTH_WARN_EVENTS_RECORDED")
}
if ($engineErrorLineCount -gt 0) {
    [void]$warnings.Add("ENGINE_ERROR_LOG_NOT_EMPTY")
}
if ($placeholderCount -gt 0) {
    [void]$warnings.Add("PORTFOLIO_STATE_PLACEHOLDER_PERSISTED")
}
if ($summary -and [bool]$summary.position_open) {
    [void]$warnings.Add("FINAL_POSITION_STILL_OPEN")
}

$grade = "PASS"
if ($issues.Count -gt 0) {
    $grade = "FAIL"
} elseif ($warnings.Count -gt 0) {
    $grade = "PASS_WITH_WARNING"
}

$result = [ordered]@{
    generated_at = (Get-Date).ToString("o")
    grade = $grade
    collection_status = $collectionStatus["COLLECTION_STATUS"]
    observe_status = $observeStatus["OBSERVE_STATUS"]
    collection_started_at = if ($collectionStartTs) { $collectionStartTs.ToString("o") } else { "" }
    collection_ended_at = if ($collectionEndTs) { $collectionEndTs.ToString("o") } else { "" }
    observe_started_at = if ($observeStartTs) { $observeStartTs.ToString("o") } else { "" }
    collection_samples = $collectionSamples
    observe_samples = $observeSamples
    expected_samples = $expectedSamples
    collection_coverage_pct = $collectionCoveragePct
    observe_coverage_pct = $observeCoveragePct
    collection_max_gap_sec = $collectionMaxGapSec
    observe_max_gap_sec = $observeMaxGapSec
    collection_end_gap_sec = $collectionEndGapSec
    observe_end_gap_sec = $observeEndGapSec
    monitor_duration_hours = if ($monitorSummary) { Get-DoubleValue $monitorSummary.duration_hours } else { 0.0 }
    engine_downtime_samples = if ($monitorSummary) { Get-IntValue $monitorSummary.engine_downtime_samples } else { 0 }
    max_worker_count = if ($monitorSummary) { Get-IntValue $monitorSummary.max_worker_count } else { 0 }
    max_open_positions = if ($monitorSummary) { Get-IntValue $monitorSummary.max_open_positions } else { 0 }
    max_total_exposure = if ($monitorSummary) { Get-DoubleValue $monitorSummary.max_total_exposure } else { 0.0 }
    realtime_pnl_min = if ($monitorSummary) { Get-DoubleValue $monitorSummary.realtime_pnl_min } else { 0.0 }
    realtime_pnl_max = if ($monitorSummary) { Get-DoubleValue $monitorSummary.realtime_pnl_max } else { 0.0 }
    final_runtime_health_status = if ($validation) { [string]$validation.status } else { "-" }
    final_runtime_action_class = if ($validation) { [string]$validation.action_class } else { "-" }
    final_health_issues = if ($validation) { Normalize-Array $validation.issues } else { @() }
    final_engine_alive = if ($health) { [bool]$health.engine_alive } else { $false }
    final_runtime_alive = if ($health) { [bool]$health.runtime_alive } else { $false }
    final_ops_health_status = if ($health) { [string]$health.ops_health_status } else { "-" }
    final_account_equity = if ($health) { Get-DoubleValue $health.account_equity } else { 0.0 }
    final_realized_pnl = $summaryPnl
    trade_outcomes_pnl = $tradeOutcomesPnl
    pnl_diff = $tradePnlDiff
    final_daily_trades = $summaryTradeCount
    trade_outcomes_count = $tradeOutcomesCount
    trade_count_diff = $tradeCountDiff
    restart_triggered_count = $restartTriggeredCount
    orphan_detected_count = $orphanDetectedCount
    health_validation_fail_count = $healthValidationFailCount
    health_validation_warn_count = $healthValidationWarnCount
    health_policy_fail_soft_count = $healthPolicyFailSoftCount
    engine_error_line_count = $engineErrorLineCount
    placeholder_count = $placeholderCount
    placeholder_last_line = $placeholderLastLine
    final_open_position = if ($summary) { [bool]$summary.position_open } else { $false }
    final_active_symbol_count = if ($summary) { Get-IntValue $summary.active_symbol_count } else { 0 }
    final_selected_symbol_count = if ($summary) { Get-IntValue $summary.selected_symbol_count } else { 0 }
    final_writer_symbol = if ($health) { [string]$health.writer_symbol } else { "-" }
    top_allocation_symbol = if ($validation) { [string]$validation.top_allocation_symbol } else { "-" }
    top_allocation_weight = if ($validation) { Get-DoubleValue $validation.top_allocation_weight } else { 0.0 }
    restart_state = if ($restartState) { $restartState } else { $null }
    issues = @($issues)
    warnings = @($warnings)
    source_paths = [ordered]@{
        collection_status = $CollectionStatusPath
        observe_status = $ObserveStatusPath
        collection_jsonl = $CollectionJsonlPath
        observe_jsonl = $ObserveJsonlPath
        monitor_summary_json = $monitorSummaryJsonPath
        validation_json = $healthValidationPath
        summary_json = $summaryPath
        health_json = $healthPath
        trade_outcomes_json = $tradeOutcomesPath
        runtime_guard_log = $guardLogPath
        autoguard_log = $autoguardLogPath
        engine_stdout_log = $engineStdoutPath
        engine_error_log = $engineErrorPath
    }
}

$lines = @(
    "RUNTIME_12H_FINAL_AUDIT_REPORT"
    "GENERATED_AT=$($result.generated_at)"
    "FINAL_GRADE=$($result.grade)"
    "COLLECTION_STATUS=$($result.collection_status)"
    "OBSERVE_STATUS=$($result.observe_status)"
    "COLLECTION_STARTED_AT=$($result.collection_started_at)"
    "COLLECTION_ENDED_AT=$($result.collection_ended_at)"
    "COLLECTION_SAMPLES=$($result.collection_samples)"
    "OBSERVE_SAMPLES=$($result.observe_samples)"
    "EXPECTED_SAMPLES=$($result.expected_samples)"
    "COLLECTION_COVERAGE_PCT=$($result.collection_coverage_pct)"
    "OBSERVE_COVERAGE_PCT=$($result.observe_coverage_pct)"
    "COLLECTION_MAX_GAP_SEC=$($result.collection_max_gap_sec)"
    "OBSERVE_MAX_GAP_SEC=$($result.observe_max_gap_sec)"
    "COLLECTION_END_GAP_SEC=$($result.collection_end_gap_sec)"
    "OBSERVE_END_GAP_SEC=$($result.observe_end_gap_sec)"
    "ENGINE_DOWNTIME_SAMPLES=$($result.engine_downtime_samples)"
    "MAX_WORKER_COUNT=$($result.max_worker_count)"
    "MAX_OPEN_POSITIONS=$($result.max_open_positions)"
    "MAX_TOTAL_EXPOSURE=$($result.max_total_exposure)"
    "REALTIME_PNL_MIN=$($result.realtime_pnl_min)"
    "REALTIME_PNL_MAX=$($result.realtime_pnl_max)"
    "FINAL_RUNTIME_HEALTH_STATUS=$($result.final_runtime_health_status)"
    "FINAL_RUNTIME_ACTION_CLASS=$($result.final_runtime_action_class)"
    "FINAL_OPS_HEALTH_STATUS=$($result.final_ops_health_status)"
    "FINAL_ENGINE_ALIVE=$($result.final_engine_alive)"
    "FINAL_RUNTIME_ALIVE=$($result.final_runtime_alive)"
    "FINAL_ACCOUNT_EQUITY=$($result.final_account_equity)"
    "FINAL_REALIZED_PNL=$($result.final_realized_pnl)"
    "TRADE_OUTCOMES_PNL=$($result.trade_outcomes_pnl)"
    "PNL_DIFF=$($result.pnl_diff)"
    "FINAL_DAILY_TRADES=$($result.final_daily_trades)"
    "TRADE_OUTCOMES_COUNT=$($result.trade_outcomes_count)"
    "TRADE_COUNT_DIFF=$($result.trade_count_diff)"
    "RESTART_TRIGGERED_COUNT=$($result.restart_triggered_count)"
    "ORPHAN_DETECTED_COUNT=$($result.orphan_detected_count)"
    "HEALTH_VALIDATION_FAIL_COUNT=$($result.health_validation_fail_count)"
    "HEALTH_VALIDATION_WARN_COUNT=$($result.health_validation_warn_count)"
    "HEALTH_POLICY_FAIL_SOFT_COUNT=$($result.health_policy_fail_soft_count)"
    "ENGINE_ERROR_LINE_COUNT=$($result.engine_error_line_count)"
    "PLACEHOLDER_COUNT=$($result.placeholder_count)"
    "PLACEHOLDER_LAST_LINE=$($result.placeholder_last_line)"
    "FINAL_OPEN_POSITION=$($result.final_open_position)"
    "FINAL_ACTIVE_SYMBOL_COUNT=$($result.final_active_symbol_count)"
    "FINAL_SELECTED_SYMBOL_COUNT=$($result.final_selected_symbol_count)"
    "FINAL_WRITER_SYMBOL=$($result.final_writer_symbol)"
    "TOP_ALLOCATION_SYMBOL=$($result.top_allocation_symbol)"
    "TOP_ALLOCATION_WEIGHT=$($result.top_allocation_weight)"
    "ISSUES=$(([string]::Join(',', $result.issues)))"
    "WARNINGS=$(([string]::Join(',', $result.warnings)))"
)

Set-Content -LiteralPath $OutputReportPath -Value $lines -Encoding UTF8
Set-Content -LiteralPath $OutputSummaryJsonPath -Value ($result | ConvertTo-Json -Depth 8) -Encoding UTF8

Write-Output "RUNTIME_12H_FINAL_AUDIT_WRITTEN=YES"
Write-Output "RUNTIME_12H_FINAL_AUDIT_REPORT=$OutputReportPath"
Write-Output "RUNTIME_12H_FINAL_AUDIT_SUMMARY_JSON=$OutputSummaryJsonPath"

