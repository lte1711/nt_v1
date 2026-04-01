param(
    [string]$ProjectRoot = "C:\next-trade-ver1.0",
    [int]$IntervalSeconds = 30
)

$ErrorActionPreference = "Continue"

$today = Get-Date
$endAt = Get-Date -Hour 12 -Minute 0 -Second 0
if ($today -ge $endAt) {
    $endAt = $endAt.AddDays(1)
}

$dateFolder = $today.ToString("yyyy-MM-dd")
$reportDir = Join-Path $ProjectRoot ("reports\" + $dateFolder + "\codex_execution_reports")
$dataDir = Join-Path $ProjectRoot "data\runtime_observation"
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

$runTag = $today.ToString("yyyyMMdd_HHmmss")
$snapshotPath = Join-Path $dataDir ("observe_until_noon_snapshots_" + $runTag + ".jsonl")
$issuesPath = Join-Path $dataDir ("observe_until_noon_issues_" + $runTag + ".jsonl")
$summaryPath = Join-Path $reportDir ("OBSERVE_UNTIL_NOON_SUMMARY_" + $runTag + ".md")
$statePath = Join-Path $reportDir ("OBSERVE_UNTIL_NOON_STATE_" + $runTag + ".json")

$runtimeLogPath = Join-Path $ProjectRoot "logs\runtime\profitmax_v1_events.jsonl"

function Append-JsonLine {
    param([string]$Path, [hashtable]$Row)
    $json = ($Row | ConvertTo-Json -Compress -Depth 8)
    Add-Content -Path $Path -Value $json -Encoding UTF8
}

function Read-JsonHttp {
    param([string]$Uri)
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 10
        return @{
            ok = $true
            status_code = [int]$resp.StatusCode
            body = $resp.Content
            error = ""
        }
    } catch {
        return @{
            ok = $false
            status_code = 0
            body = ""
            error = $_.Exception.Message
        }
    }
}

function Safe-JsonValue {
    param($Obj, [string]$Name, $Default = $null)
    if ($null -ne $Obj -and $null -ne $Obj.PSObject.Properties[$Name]) {
        return $Obj.$Name
    }
    return $Default
}

function Parse-Json {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    try { return ($Text | ConvertFrom-Json) } catch { return $null }
}

function Get-OpenPositions {
    param($InvestorJson)
    $result = @()
    if ($null -eq $InvestorJson -or $null -eq $InvestorJson.positions) {
        return $result
    }
    foreach ($p in @($InvestorJson.positions)) {
        try {
            $amt = [double]$p.positionAmt
        } catch {
            $amt = 0.0
        }
        if ([math]::Abs($amt) -gt 0.0) {
            $result += $p
        }
    }
    return $result
}

function Get-RecentEventWindow {
    param([string]$Path, [int]$TailLines = 120)
    if (-not (Test-Path $Path)) { return @() }
    $rows = @()
    foreach ($line in (Get-Content -Path $Path -Tail $TailLines -ErrorAction SilentlyContinue)) {
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        try { $rows += ($line | ConvertFrom-Json) } catch {}
    }
    return $rows
}

function Add-Issue {
    param(
        [string]$Type,
        [string]$Severity,
        [string]$Message,
        [hashtable]$Context
    )
    $row = @{
        ts = (Get-Date).ToString("o")
        issue_type = $Type
        severity = $Severity
        message = $Message
        context = $Context
    }
    Append-JsonLine -Path $issuesPath -Row $row
    $script:issueCount++
    $currentCount = 0
    if ($script:issueTypeCounts.ContainsKey($Type)) {
        $currentCount = [int]$script:issueTypeCounts[$Type]
    }
    $script:issueTypeCounts[$Type] = $currentCount + 1
}

$issueCount = 0
$issueTypeCounts = @{}
$snapshotCount = 0
$lastRuntimeTs = $null
$lastWorkerTs = $null

Append-JsonLine -Path $snapshotPath -Row @{
    ts = (Get-Date).ToString("o")
    phase = "START"
    end_at = $endAt.ToString("o")
    interval_seconds = $IntervalSeconds
}

while ((Get-Date) -lt $endAt) {
    $now = Get-Date

    $runtimeResp = Read-JsonHttp -Uri "http://127.0.0.1:8788/api/runtime"
    $investorResp = Read-JsonHttp -Uri "http://127.0.0.1:8100/api/v1/investor/positions"

    $runtimeJson = Parse-Json -Text $runtimeResp.body
    $investorJson = Parse-Json -Text $investorResp.body
    $openPositions = Get-OpenPositions -InvestorJson $investorJson
    $recentEvents = Get-RecentEventWindow -Path $runtimeLogPath

    $runtimeLast = Safe-JsonValue $runtimeJson "last_update" ""
    $workerLast = Safe-JsonValue $runtimeJson "worker_last_ts" ""
    $engineStatus = [string](Safe-JsonValue $runtimeJson "engine_status" "")
    $opsStatus = [string](Safe-JsonValue $runtimeJson "current_operation_status" "")
    $apiStatus = [string](Safe-JsonValue $runtimeJson "ops_health_status" "")
    $binanceStatus = [string](Safe-JsonValue $runtimeJson "binance_link_status" "")
    $openCountApi = [int](Safe-JsonValue $runtimeJson "open_positions_count" 0)
    $openCountExchange = [int](Safe-JsonValue $runtimeJson "exchange_open_position_count" 0)
    $globalKill = [string](Safe-JsonValue $runtimeJson "global_kill_switch_state" "false")
    $selectedSymbol = [string](Safe-JsonValue $runtimeJson "selected_symbol" "-")

    $snapshot = @{
        ts = $now.ToString("o")
        engine_status = $engineStatus
        operation_status = $opsStatus
        api_status = $apiStatus
        binance_link_status = $binanceStatus
        selected_symbol = $selectedSymbol
        open_positions_count = $openCountApi
        exchange_open_position_count = $openCountExchange
        investor_open_positions_count = @($openPositions).Count
        global_kill_switch_state = $globalKill
        runtime_last_ts = $runtimeLast
        worker_last_ts = $workerLast
        current_position_symbol = [string](Safe-JsonValue $runtimeJson "current_position_symbol" "-")
        invested_margin = [string](Safe-JsonValue $runtimeJson "invested_margin" "0")
        unrealized_pnl_live = [string](Safe-JsonValue $runtimeJson "unrealized_pnl_live" "0")
        kpi_total_trades = [int](Safe-JsonValue $runtimeJson "kpi_total_trades" 0)
        kpi_realized_pnl = [string](Safe-JsonValue $runtimeJson "kpi_realized_pnl" "0")
    }
    Append-JsonLine -Path $snapshotPath -Row $snapshot
    $snapshotCount++

    if (-not $runtimeResp.ok) {
        Add-Issue -Type "RUNTIME_API_UNREACHABLE" -Severity "high" -Message "dashboard runtime api unreachable" -Context @{
            error = $runtimeResp.error
        }
    }
    if (-not $investorResp.ok) {
        Add-Issue -Type "INVESTOR_API_UNREACHABLE" -Severity "high" -Message "investor positions api unreachable" -Context @{
            error = $investorResp.error
        }
    }
    if ($runtimeResp.ok -and $engineStatus -ne "RUNNING") {
        Add-Issue -Type "ENGINE_NOT_RUNNING" -Severity "high" -Message "engine status is not RUNNING" -Context @{
            engine_status = $engineStatus
            operation_status = $opsStatus
        }
    }
    if ($runtimeResp.ok -and $apiStatus -ne "OK") {
        Add-Issue -Type "OPS_HEALTH_NOT_OK" -Severity "medium" -Message "ops health status is not OK" -Context @{
            ops_health_status = $apiStatus
        }
    }
    if ($runtimeResp.ok -and $binanceStatus -ne "TESTNET_REALTIME_LINKED") {
        Add-Issue -Type "BINANCE_LINK_DEGRADED" -Severity "high" -Message "binance link status degraded" -Context @{
            binance_link_status = $binanceStatus
        }
    }
    if ($runtimeResp.ok -and $globalKill -eq "true") {
        Add-Issue -Type "GLOBAL_KILL_SWITCH_ACTIVE" -Severity "high" -Message "global kill switch activated" -Context @{
            global_kill_switch_state = $globalKill
            global_kill_reason = [string](Safe-JsonValue $runtimeJson "global_kill_reason" "-")
        }
    }
    if ($runtimeResp.ok -and $openCountApi -ne $openCountExchange) {
        Add-Issue -Type "OPEN_COUNT_MISMATCH" -Severity "medium" -Message "runtime open count and exchange open count differ" -Context @{
            open_positions_count = $openCountApi
            exchange_open_position_count = $openCountExchange
        }
    }
    if ($runtimeResp.ok -and $openCountExchange -ne @($openPositions).Count) {
        Add-Issue -Type "INVESTOR_RUNTIME_POSITION_MISMATCH" -Severity "medium" -Message "runtime and investor api open counts differ" -Context @{
            exchange_open_position_count = $openCountExchange
            investor_open_positions_count = @($openPositions).Count
        }
    }

    foreach ($p in $openPositions) {
        try {
            $updateTime = [int64]$p.updateTime
        } catch {
            $updateTime = 0
        }
        if ($updateTime -gt 0) {
            $ageMin = ((Get-Date) - [DateTimeOffset]::FromUnixTimeMilliseconds($updateTime).LocalDateTime).TotalMinutes
            if ($ageMin -ge 20) {
                Add-Issue -Type "POSITION_OVERDUE_OVER_20MIN" -Severity "medium" -Message "open position persisted beyond 20 minutes" -Context @{
                    symbol = [string]$p.symbol
                    age_min = [math]::Round($ageMin, 3)
                    position_amt = [string]$p.positionAmt
                    entry_price = [string]$p.entryPrice
                    unrealized_pnl = [string]$p.unRealizedProfit
                }
            }
        }
    }

    foreach ($evt in $recentEvents) {
        $etype = [string]$evt.event_type
        if ($etype -eq "STATE_LOCAL_POSITION_MISMATCH_TELEMETRY") {
            Add-Issue -Type "LOCAL_POSITION_MISMATCH" -Severity "medium" -Message "local position mismatch telemetry observed" -Context @{
                symbol = [string]$evt.symbol
                ts = [string]$evt.ts
                payload = $evt.payload
            }
        } elseif ($etype -eq "ENTRY_TO_SUBMIT_BLOCKED") {
            $blockClass = [string](Safe-JsonValue $evt.payload "block_class" "")
            if ($blockClass -in @("GLOBAL_RISK_KILL_SWITCH", "ORDER_SUBMIT_GUARD")) {
                Add-Issue -Type "ENTRY_BLOCKED_CRITICAL" -Severity "medium" -Message "entry blocked by critical guard" -Context @{
                    symbol = [string]$evt.symbol
                    ts = [string]$evt.ts
                    block_class = $blockClass
                    block_reason = [string](Safe-JsonValue $evt.payload "block_reason" "")
                }
            }
        } elseif ($etype -eq "EXTERNAL_STRATEGY_SIGNAL_STALE") {
            Add-Issue -Type "STALE_STRATEGY_SIGNAL" -Severity "low" -Message "external strategy signal stale observed" -Context @{
                symbol = [string]$evt.symbol
                ts = [string]$evt.ts
                signal_age_sec = [string](Safe-JsonValue $evt.payload "signal_age_sec" "")
            }
        }
    }

    $state = @{
        ts = $now.ToString("o")
        end_at = $endAt.ToString("o")
        snapshot_count = $snapshotCount
        issue_count = $issueCount
        issue_type_counts = $issueTypeCounts
        latest_runtime = $snapshot
        snapshot_path = $snapshotPath
        issues_path = $issuesPath
        summary_path = $summaryPath
    }
    ($state | ConvertTo-Json -Depth 8) | Set-Content -Path $statePath -Encoding UTF8

    Start-Sleep -Seconds $IntervalSeconds
}

$finalLines = @()
$finalLines += "# OBSERVE UNTIL NOON SUMMARY"
$finalLines += ""
$finalLines += "- START_TIME: $($today.ToString('yyyy-MM-dd HH:mm:ss K'))"
$finalLines += "- END_TIME: $($endAt.ToString('yyyy-MM-dd HH:mm:ss K'))"
$finalLines += "- SNAPSHOT_COUNT: $snapshotCount"
$finalLines += "- ISSUE_COUNT: $issueCount"
$finalLines += "- SNAPSHOT_PATH: $snapshotPath"
$finalLines += "- ISSUES_PATH: $issuesPath"
$finalLines += "- STATE_PATH: $statePath"
$finalLines += ""
$finalLines += "## ISSUE TYPE COUNTS"
foreach ($k in ($issueTypeCounts.Keys | Sort-Object)) {
    $finalLines += "- ${k}: $($issueTypeCounts[$k])"
}
$finalLines -join "`r`n" | Set-Content -Path $summaryPath -Encoding UTF8
