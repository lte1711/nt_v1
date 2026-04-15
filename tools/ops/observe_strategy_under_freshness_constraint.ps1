$ErrorActionPreference = "Stop"

$projectRoot = "C:\nt_v1"
$eventLogPath = Join-Path $projectRoot "logs\runtime\profitmax_v1_events.jsonl"
$runtimeLogPath = Join-Path $projectRoot "logs\runtime\multi5_runtime_events.jsonl"
$snapshotPath = Join-Path $projectRoot "logs\runtime\portfolio_metrics_snapshot.json"
$reportDir = Join-Path $projectRoot "reports\2026-03-28\codex_execution_reports"
$dataDir = Join-Path $projectRoot "data\runtime_observation"

$statePath = Join-Path $reportDir "STEP_BAEKSEOL_STRATEGY_UNDER_FRESHNESS_CONSTRAINT_1.state.json"
$heartbeatPath = Join-Path $reportDir "STEP_BAEKSEOL_STRATEGY_UNDER_FRESHNESS_CONSTRAINT_1.heartbeat.json"
$directiveStatusPath = Join-Path $reportDir "STEP_BAEKSEOL_STRATEGY_UNDER_FRESHNESS_CONSTRAINT_1.status.txt"
$detailedStatePath = Join-Path $reportDir "STEP_BAEKSEOL_STRATEGY_UNDER_FRESHNESS_CONSTRAINT_1.detailed_state.json"

$snapshotJsonlPath = Join-Path $dataDir "strategy_under_freshness_constraint_snapshots_20260328_1540.jsonl"
$eventJsonlPath = Join-Path $dataDir "strategy_under_freshness_constraint_events_20260328_1540.jsonl"
$issueJsonlPath = Join-Path $dataDir "strategy_under_freshness_constraint_issues_20260328_1540.jsonl"

New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

# Locked-profile official observation start:
$windowStart = [datetimeoffset]"2026-03-28T04:40:00+00:00"
$windowEnd = $windowStart.AddHours(2)

function Append-Jsonl {
    param(
        [string]$Path,
        [object]$Payload
    )
    ($Payload | ConvertTo-Json -Depth 8 -Compress) | Add-Content -Path $Path -Encoding UTF8
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
    param([object]$EventRow)
    $eventType = [string]$EventRow.event_type
    $payload = $EventRow.payload

    switch ($eventType) {
        "DATA_STALL" { return "DATA_STALL" }
        "PRICE_FETCH_FAIL" { return "PRICE_FETCH_FAIL" }
        "STATE_VALIDATION_ERROR" { return "STATE_VALIDATION_ERROR" }
        "ACCOUNT_HEALTH_REFRESH_FAILED" { return "ACCOUNT_HEALTH_REFRESH_FAILED" }
        "STATE_LOCAL_POSITION_MISMATCH_TELEMETRY" { return "LOCAL_POSITION_MISMATCH" }
        "STATE_LOCAL_POSITION_BOOTSTRAP_REQUIRED" { return "LOCAL_POSITION_BOOTSTRAP_REQUIRED" }
        "EXTERNAL_STRATEGY_SIGNAL_STALE" { return "STALE_STRATEGY_SIGNAL" }
        "ENTRY_TO_SUBMIT_BLOCKED" { return "ENTRY_BLOCKED" }
        "GLOBAL_RISK_EVALUATION" {
            if ($payload -and $payload.kill_switch_state -eq $true) { return "GLOBAL_KILL_SWITCH_ACTIVE" }
        }
        "DATA_FLOW_TRACE_MARKET" {
            if ($payload -and $payload.stall_detected_fetch -eq $true) { return "FETCH_DELAY_OVER_THRESHOLD" }
        }
        "DATA_FLOW_TRACE_DECISION" {
            if ($payload -and $payload.stall_detected_total -eq $true) { return "TOTAL_DECISION_DELAY_OVER_THRESHOLD" }
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
            $row = $_ | ConvertFrom-Json
            $rows += $row
        } catch {}
    }
    return ,$rows
}

$initialEventCount = if (Test-Path $eventLogPath) { (Get-Content $eventLogPath -Encoding UTF8).Count } else { 0 }
$initialRuntimeCount = if (Test-Path $runtimeLogPath) { (Get-Content $runtimeLogPath -Encoding UTF8).Count } else { 0 }
$processedEventCount = $initialEventCount
$processedRuntimeCount = $initialRuntimeCount
$capturedEventCount = 0
$capturedIssueCount = 0
$issueTypeCounts = @{}
$eventTypeCounts = @{}

$state = [ordered]@{
    status = "ACTIVE"
    mission = "STEP-BAEKSEOL-STRATEGY-UNDER-FRESHNESS-CONSTRAINT-1"
    window_start_utc = $windowStart.ToString("o")
    window_end_utc = $windowEnd.ToString("o")
    window_start_kst = $windowStart.ToOffset([timespan]::FromHours(9)).ToString("yyyy-MM-dd HH:mm:ss zzz")
    window_end_kst = $windowEnd.ToOffset([timespan]::FromHours(9)).ToString("yyyy-MM-dd HH:mm:ss zzz")
    runtime_profile = @{
        universe = 10
        max_active_symbols = 5
        max_open_positions = 5
        scan_interval = 5
        price_source = "mark_price"
    }
    collection_paths = @{
        snapshots = $snapshotJsonlPath
        events = $eventJsonlPath
        issues = $issueJsonlPath
    }
}
$state | ConvertTo-Json -Depth 8 | Set-Content -Path $statePath -Encoding UTF8

while ([datetimeoffset]::UtcNow -lt $windowEnd) {
    $now = [datetimeoffset]::UtcNow

    $runtimeTail = $null
    $eventTail = $null
    $portfolioSnapshot = Get-SafeJsonFile -Path $snapshotPath
    try {
        $runtimeTail = Get-Content $runtimeLogPath -Tail 1 -Encoding UTF8 | ConvertFrom-Json
    } catch {}
    try {
        $eventTail = Get-Content $eventLogPath -Tail 1 -Encoding UTF8 | ConvertFrom-Json
    } catch {}

    $newRuntimeRows = Get-RecentJsonlRows -Path $runtimeLogPath -SkipCount $processedRuntimeCount
    $newEventRows = Get-RecentJsonlRows -Path $eventLogPath -SkipCount $processedEventCount

    if (Test-Path $runtimeLogPath) { $processedRuntimeCount = (Get-Content $runtimeLogPath -Encoding UTF8).Count }
    if (Test-Path $eventLogPath) { $processedEventCount = (Get-Content $eventLogPath -Encoding UTF8).Count }

    foreach ($row in $newRuntimeRows) {
        Append-Jsonl -Path $eventJsonlPath -Payload ([ordered]@{
            ts = $now.ToString("o")
            source = "multi5_runtime_events"
            row = $row
        })
        $capturedEventCount++
        $eventType = "RUNTIME_SNAPSHOT_ROW"
        if (-not $eventTypeCounts.ContainsKey($eventType)) { $eventTypeCounts[$eventType] = 0 }
        $eventTypeCounts[$eventType]++
    }

    foreach ($row in $newEventRows) {
        $rowTs = $null
        try { if ($row.ts) { $rowTs = [datetimeoffset]$row.ts } } catch {}
        if ($rowTs -and $rowTs -lt $windowStart) { continue }

        Append-Jsonl -Path $eventJsonlPath -Payload ([ordered]@{
            ts = $now.ToString("o")
            source = "profitmax_v1_events"
            row = $row
        })
        $capturedEventCount++

        $eventType = [string]$row.event_type
        if (-not $eventTypeCounts.ContainsKey($eventType)) { $eventTypeCounts[$eventType] = 0 }
        $eventTypeCounts[$eventType]++

        $issueType = Classify-Issue -EventRow $row
        if ($null -ne $issueType) {
            if (-not $issueTypeCounts.ContainsKey($issueType)) { $issueTypeCounts[$issueType] = 0 }
            $issueTypeCounts[$issueType]++
            $capturedIssueCount++
            Append-Jsonl -Path $issueJsonlPath -Payload ([ordered]@{
                ts = $now.ToString("o")
                issue_type = $issueType
                symbol = $row.symbol
                event_type = $row.event_type
                payload = $row.payload
            })
        }
    }

    $snapshotPayload = [ordered]@{
        ts_utc = $now.ToString("o")
        ts_kst = $now.ToOffset([timespan]::FromHours(9)).ToString("yyyy-MM-dd HH:mm:ss zzz")
        seconds_remaining = [math]::Max(0, [int](($windowEnd - $now).TotalSeconds))
        runtime_alive = [bool]($runtimeTail -ne $null)
        last_runtime_ts = if ($runtimeTail) { $runtimeTail.ts } else { $null }
        selected_symbol = if ($runtimeTail) { $runtimeTail.selected_symbol } else { $null }
        active_symbol_count = if ($runtimeTail) { $runtimeTail.active_symbol_count } else { $null }
        universe_symbol_count = if ($runtimeTail) { $runtimeTail.universe_symbol_count } else { $null }
        max_symbol_active = if ($runtimeTail) { $runtimeTail.max_symbol_active } else { $null }
        max_open_positions = if ($runtimeTail) { $runtimeTail.max_open_positions } else { $null }
        engine_running = if ($runtimeTail) { $runtimeTail.engine_running } else { $null }
        api_server_reachable = if ($runtimeTail) { $runtimeTail.api_server_reachable } else { $null }
        last_event_ts = if ($eventTail) { $eventTail.ts } else { $null }
        last_event_type = if ($eventTail) { $eventTail.event_type } else { $null }
        portfolio_snapshot = $portfolioSnapshot
        captured_event_count = $capturedEventCount
        captured_issue_count = $capturedIssueCount
    }

    Append-Jsonl -Path $snapshotJsonlPath -Payload $snapshotPayload
    $snapshotPayload | ConvertTo-Json -Depth 8 | Set-Content -Path $heartbeatPath -Encoding UTF8

    $detailedState = [ordered]@{
        ts_utc = $now.ToString("o")
        status = "ACTIVE"
        mission = "STEP-BAEKSEOL-STRATEGY-UNDER-FRESHNESS-CONSTRAINT-1"
        window_end_kst = $windowEnd.ToOffset([timespan]::FromHours(9)).ToString("yyyy-MM-dd HH:mm:ss zzz")
        collected = @{
            snapshots = $snapshotJsonlPath
            events = $eventJsonlPath
            issues = $issueJsonlPath
        }
        counters = @{
            captured_event_count = $capturedEventCount
            captured_issue_count = $capturedIssueCount
            event_type_counts = $eventTypeCounts
            issue_type_counts = $issueTypeCounts
        }
    }
    $detailedState | ConvertTo-Json -Depth 10 | Set-Content -Path $detailedStatePath -Encoding UTF8

    "ACTIVE until $($windowEnd.ToOffset([timespan]::FromHours(9)).ToString('yyyy-MM-dd HH:mm:ss zzz'))" | Set-Content -Path $directiveStatusPath -Encoding UTF8
    Start-Sleep -Seconds 30
}

"OBSERVATION_WINDOW_COMPLETE" | Set-Content -Path $directiveStatusPath -Encoding UTF8

