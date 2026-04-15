$ErrorActionPreference = "Stop"

$projectRoot = "C:\nt_v1"
$eventLogPath = Join-Path $projectRoot "logs\runtime\profitmax_v1_events.jsonl"
$runtimeLogPath = Join-Path $projectRoot "logs\runtime\multi5_runtime_events.jsonl"
$snapshotPath = Join-Path $projectRoot "logs\runtime\portfolio_metrics_snapshot.json"
$reportDir = Join-Path $projectRoot "reports\2026-03-28\codex_execution_reports"
$dataDir = Join-Path $projectRoot "data\runtime_observation"

$statePath = Join-Path $reportDir "STEP_BAEKSEOL_VALIDATION_COLLECTION_1.state.json"
$heartbeatPath = Join-Path $reportDir "STEP_BAEKSEOL_VALIDATION_COLLECTION_1.heartbeat.json"
$statusPath = Join-Path $reportDir "STEP_BAEKSEOL_VALIDATION_COLLECTION_1.status.txt"
$detailPath = Join-Path $reportDir "STEP_BAEKSEOL_VALIDATION_COLLECTION_1.detailed_state.json"

$eventJsonlPath = Join-Path $dataDir "validation_only_events_20260328.jsonl"
$issueJsonlPath = Join-Path $dataDir "validation_only_issues_20260328.jsonl"
$snapshotJsonlPath = Join-Path $dataDir "validation_only_snapshots_20260328.jsonl"

New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

$validationEventTypes = @(
    "ENTRY_SIGNAL",
    "ENTRY_DECISION_5M",
    "STRATEGY_SIGNAL_EXTERNAL",
    "EXTERNAL_STRATEGY_SIGNAL_STALE",
    "ENTRY_TO_SUBMIT_BLOCKED",
    "PRE_ORDER_SUBMIT",
    "DATA_FLOW_TRACE_PRE_ORDER",
    "ORDER_ACK",
    "ORDER_FILLED",
    "ORDER_SUBMIT_FAILED",
    "TRADE_EXECUTED",
    "POSITION_CLOSED",
    "REALIZED_PNL",
    "EXIT_SIGNAL",
    "EXIT_REASON",
    "TRADE_DURATION",
    "POSITION_HOLD_TIME",
    "TIMEOUT_EXIT_SKIPPED_PROFITABLE_POSITION",
    "DATA_FLOW_TRACE_MARKET",
    "DATA_FLOW_TRACE_DECISION",
    "CANDIDATE_CALL_GATE_CHECK",
    "STATE_API_SOURCE_OF_TRUTH_APPLIED",
    "STATE_RECONCILE_APPLIED",
    "STATE_LOCAL_POSITION_BOOTSTRAP_REQUIRED",
    "STATE_VALIDATION_ERROR",
    "ACCOUNT_HEALTH_REFRESH_FAILED",
    "DATA_STALL",
    "PRICE_FETCH_FAIL",
    "GLOBAL_RISK_EVALUATION"
)

function Append-Jsonl {
    param(
        [string]$Path,
        [object]$Payload
    )
    ($Payload | ConvertTo-Json -Depth 10 -Compress) | Add-Content -Path $Path -Encoding UTF8
}

function Get-SafeJsonFile {
    param([string]$Path)
    try {
        if (Test-Path $Path) {
            return Get-Content $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        }
    } catch {}
    return $null
}

function Classify-Issue {
    param([object]$Row)
    $eventType = [string]$Row.event_type
    $payload = $Row.payload

    switch ($eventType) {
        "EXTERNAL_STRATEGY_SIGNAL_STALE" { return "STALE_STRATEGY_SIGNAL" }
        "ENTRY_TO_SUBMIT_BLOCKED" { return "ENTRY_BLOCKED" }
        "ORDER_SUBMIT_FAILED" { return "ORDER_SUBMIT_FAILED" }
        "STATE_VALIDATION_ERROR" { return "STATE_VALIDATION_ERROR" }
        "ACCOUNT_HEALTH_REFRESH_FAILED" { return "ACCOUNT_HEALTH_REFRESH_FAILED" }
        "DATA_STALL" { return "DATA_STALL" }
        "PRICE_FETCH_FAIL" { return "PRICE_FETCH_FAIL" }
        "STATE_LOCAL_POSITION_BOOTSTRAP_REQUIRED" { return "LOCAL_POSITION_BOOTSTRAP_REQUIRED" }
        "DATA_FLOW_TRACE_MARKET" {
            if ($payload -and $payload.stall_detected_fetch -eq $true) { return "FETCH_DELAY_OVER_THRESHOLD" }
        }
        "DATA_FLOW_TRACE_DECISION" {
            if ($payload -and $payload.stall_detected_total -eq $true) { return "TOTAL_DECISION_DELAY_OVER_THRESHOLD" }
        }
        "EXIT_REASON" {
            if ($payload -and [string]$payload.exit_reason -eq "timeout_exit") { return "TIMEOUT_EXIT_OCCURRED" }
        }
        "GLOBAL_RISK_EVALUATION" {
            if ($payload -and $payload.kill_switch_state -eq $true) { return "GLOBAL_KILL_SWITCH_ACTIVE" }
        }
    }

    return $null
}

function Get-RecentJsonlRows {
    param(
        [string]$Path,
        [int]$SkipCount
    )

    if (-not (Test-Path $Path)) { return @() }

    $rows = @()
    $lineIndex = 0
    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $lineIndex++
        if ($lineIndex -le $SkipCount) { return }
        if (-not $_) { return }
        try {
            $rows += ($_ | ConvertFrom-Json)
        } catch {}
    }
    return ,$rows
}

$processedEventCount = if (Test-Path $eventLogPath) { (Get-Content $eventLogPath -Encoding UTF8).Count } else { 0 }
$processedRuntimeCount = if (Test-Path $runtimeLogPath) { (Get-Content $runtimeLogPath -Encoding UTF8).Count } else { 0 }
$capturedEventCount = 0
$capturedIssueCount = 0
$eventTypeCounts = @{}
$issueTypeCounts = @{}

$state = [ordered]@{
    status = "ACTIVE"
    mission = "STEP-BAEKSEOL-VALIDATION-COLLECTION-1"
    mode = "VALIDATION_ONLY"
    runtime_profile = @{
        universe = 10
        max_active_symbols = 5
        max_open_positions = 5
        scan_interval = 5
        price_source = "mark_price"
    }
    collection_paths = @{
        events = $eventJsonlPath
        issues = $issueJsonlPath
        snapshots = $snapshotJsonlPath
    }
    validation_event_types = $validationEventTypes
}
$state | ConvertTo-Json -Depth 10 | Set-Content -Path $statePath -Encoding UTF8

while ($true) {
    $now = [datetimeoffset]::UtcNow
    $runtimeTail = $null
    $portfolioSnapshot = Get-SafeJsonFile -Path $snapshotPath

    try { $runtimeTail = Get-Content $runtimeLogPath -Tail 1 -Encoding UTF8 | ConvertFrom-Json } catch {}

    $newRuntimeRows = Get-RecentJsonlRows -Path $runtimeLogPath -SkipCount $processedRuntimeCount
    $newEventRows = Get-RecentJsonlRows -Path $eventLogPath -SkipCount $processedEventCount

    if (Test-Path $runtimeLogPath) { $processedRuntimeCount = (Get-Content $runtimeLogPath -Encoding UTF8).Count }
    if (Test-Path $eventLogPath) { $processedEventCount = (Get-Content $eventLogPath -Encoding UTF8).Count }

    foreach ($row in $newEventRows) {
        $eventType = [string]$row.event_type
        if ($validationEventTypes -notcontains $eventType) { continue }

        Append-Jsonl -Path $eventJsonlPath -Payload ([ordered]@{
            observed_ts = $now.ToString("o")
            row = $row
        })

        $capturedEventCount++
        if (-not $eventTypeCounts.ContainsKey($eventType)) { $eventTypeCounts[$eventType] = 0 }
        $eventTypeCounts[$eventType]++

        $issueType = Classify-Issue -Row $row
        if ($null -ne $issueType) {
            if (-not $issueTypeCounts.ContainsKey($issueType)) { $issueTypeCounts[$issueType] = 0 }
            $issueTypeCounts[$issueType]++
            $capturedIssueCount++
            Append-Jsonl -Path $issueJsonlPath -Payload ([ordered]@{
                observed_ts = $now.ToString("o")
                issue_type = $issueType
                symbol = $row.symbol
                event_type = $row.event_type
                payload = $row.payload
            })
        }
    }

    foreach ($row in $newRuntimeRows) {
        Append-Jsonl -Path $snapshotJsonlPath -Payload ([ordered]@{
            observed_ts = $now.ToString("o")
            source = "multi5_runtime_events"
            row = $row
        })
    }

    $heartbeat = [ordered]@{
        ts_utc = $now.ToString("o")
        ts_kst = $now.ToOffset([timespan]::FromHours(9)).ToString("yyyy-MM-dd HH:mm:ss zzz")
        runtime_alive = [bool]($runtimeTail -ne $null)
        selected_symbol = if ($runtimeTail) { $runtimeTail.selected_symbol } else { $null }
        active_symbol_count = if ($runtimeTail) { $runtimeTail.active_symbol_count } else { $null }
        universe_symbol_count = if ($runtimeTail) { $runtimeTail.universe_symbol_count } else { $null }
        portfolio_total_trades = if ($portfolioSnapshot) { $portfolioSnapshot.total_trades } else { $null }
        portfolio_realized_pnl = if ($portfolioSnapshot) { $portfolioSnapshot.realized_pnl } else { $null }
        captured_event_count = $capturedEventCount
        captured_issue_count = $capturedIssueCount
        event_type_counts = $eventTypeCounts
        issue_type_counts = $issueTypeCounts
    }

    Append-Jsonl -Path $snapshotJsonlPath -Payload ([ordered]@{
        observed_ts = $now.ToString("o")
        source = "validation_heartbeat"
        heartbeat = $heartbeat
    })

    $heartbeat | ConvertTo-Json -Depth 10 | Set-Content -Path $heartbeatPath -Encoding UTF8
    $detail = [ordered]@{
        ts_utc = $now.ToString("o")
        status = "ACTIVE"
        mode = "VALIDATION_ONLY"
        counters = @{
            captured_event_count = $capturedEventCount
            captured_issue_count = $capturedIssueCount
            event_type_counts = $eventTypeCounts
            issue_type_counts = $issueTypeCounts
        }
    }
    $detail | ConvertTo-Json -Depth 10 | Set-Content -Path $detailPath -Encoding UTF8
    "ACTIVE_VALIDATION_ONLY" | Set-Content -Path $statusPath -Encoding UTF8
    Start-Sleep -Seconds 30
}

