param(
    [string]$BaseDir = "C:\next-trade-ver1.0\data\runtime_observation",
    [int]$DurationHours = 168,
    [int]$IntervalSeconds = 300
)

$ErrorActionPreference = "Continue"

$obsStart = Get-Date
$obsEnd = $obsStart.AddHours($DurationHours)

$logFile = Join-Path $BaseDir "evergreen_runtime_7d_log.txt"
$summaryFile = Join-Path $BaseDir "evergreen_runtime_7d_summary.txt"
$finalReportFile = Join-Path $BaseDir "evergreen_runtime_7d_final_report.md"
$engineLogPath = "C:\next-trade-ver1.0\logs\runtime\multi5_runtime_events.jsonl"
$orderEventLogPath = "C:\next-trade-ver1.0\logs\runtime\profitmax_v1_events.jsonl"
$checkpointHours = @(6, 12, 24, 48, 72, 120)
$checkpointWritten = @{}
$lastCpuSample = @{}
$logicalCpu = [Math]::Max(1, (Get-CimInstance Win32_ComputerSystem).NumberOfLogicalProcessors)

New-Item -ItemType Directory -Force -Path $BaseDir | Out-Null

function Write-Line {
    param([string]$Path, [string]$Text)
    Add-Content -Path $Path -Value $Text -Encoding UTF8
}

function Read-JsonHttp {
    param([string]$Uri)
    try {
        $resp = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 10
        return @{
            ok = $true
            status = $resp.StatusCode
            body = $resp.Content
            error = ""
        }
    } catch {
        return @{
            ok = $false
            status = "ERROR"
            body = ""
            error = $_.Exception.Message
        }
    }
}

function Safe-JsonValue {
    param($obj, [string]$name, $default = "")
    if ($null -ne $obj -and $null -ne $obj.PSObject.Properties[$name]) {
        return $obj.$name
    }
    return $default
}

function Get-LatestRuntimeEvent {
    if (-not (Test-Path $engineLogPath)) { return $null }
    $line = Get-Content -Path $engineLogPath -Tail 1 -ErrorAction SilentlyContinue
    if (-not $line) { return $null }
    try { return $line | ConvertFrom-Json } catch { return $null }
}

function Get-OrderCounters {
    $counts = @{
        submit = 0
        ack = 0
        reject = 0
        fills = 0
    }
    if (-not (Test-Path $orderEventLogPath)) { return $counts }
    Get-Content -Path $orderEventLogPath -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $row = $_ | ConvertFrom-Json
            $eventType = [string]$row.event_type
            switch -Regex ($eventType) {
                "ORDER_SUBMIT|SUBMIT_ORDER|ENTRY_SUBMIT" { $counts.submit++ }
                "ORDER_ACK|ENTRY_ACK|ACK" { $counts.ack++ }
                "ORDER_REJECT|ORDER_FAIL|API_ERROR|REJECT" { $counts.reject++ }
                "FILL|FILLED|ORDER_FILL|TRADE_FILL" { $counts.fills++ }
            }
        } catch {}
    }
    return $counts
}

function Get-MonitoredProcesses {
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -match "run_multi5_engine.py|profitmax_v1_runner.py|runtime_guard.ps1|phase5_autoguard.ps1" -and
        $_.CommandLine -notmatch "runtime_observer_7d.ps1"
    } | Select-Object ProcessId, ParentProcessId, Name, CommandLine, WorkingSetSize)
}

function Get-CpuUsageEstimate {
    param($Processes)
    $now = Get-Date
    $totalDeltaCpu = 0.0
    foreach ($proc in $Processes) {
        $pid = [int]$proc.ProcessId
        try {
            $p = Get-Process -Id $pid -ErrorAction Stop
            $cpu = [double]$p.CPU
            if ($lastCpuSample.ContainsKey($pid)) {
                $prev = $lastCpuSample[$pid]
                $elapsed = ($now - $prev.ts).TotalSeconds
                if ($elapsed -gt 0) {
                    $totalDeltaCpu += [Math]::Max(0.0, ($cpu - $prev.cpu))
                }
            }
            $lastCpuSample[$pid] = @{
                cpu = $cpu
                ts = $now
            }
        } catch {}
    }
    if ($Processes.Count -eq 0) { return 0.0 }
    $interval = [Math]::Max(1.0, [double]$IntervalSeconds)
    return [Math]::Round(($totalDeltaCpu / ($interval * $logicalCpu)) * 100.0, 3)
}

function Get-SafeStartState {
    param($RuntimeJson)
    $activeCount = 0
    try { $activeCount = [int](Safe-JsonValue $RuntimeJson "active_symbol_count" 0) } catch { $activeCount = 0 }
    $targetMax = 0
    try { $targetMax = [int](Safe-JsonValue $RuntimeJson "target_max_positions" 0) } catch { $targetMax = 0 }
    if ($targetMax -eq 5 -and $activeCount -le 5) { return "OK" }
    return "CHECK_REQUIRED"
}

function Write-Checkpoint {
    param(
        [int]$Hour,
        [hashtable]$Snapshot
    )
    $name = "evergreen_checkpoint_${Hour}h.txt"
    $path = Join-Path $BaseDir $name
    @(
        "CHECKPOINT_HOUR=$Hour"
        "TS=$($Snapshot.ts)"
        "ENGINE_ALIVE=$($Snapshot.engine_alive)"
        "WATCHDOG_STATUS=$($Snapshot.watchdog_status)"
        "API_HEALTH=$($Snapshot.api_health)"
        "ORDER_SUBMIT_COUNT=$($Snapshot.order_submit)"
        "ORDER_ACK_COUNT=$($Snapshot.order_ack)"
        "ORDER_REJECT_COUNT=$($Snapshot.order_reject)"
        "FILL_COUNT=$($Snapshot.fills)"
        "OPEN_POSITION_COUNT=$($Snapshot.open_position_count)"
        "ACTIVE_SYMBOL_COUNT=$($Snapshot.active_symbol_count)"
        "SAFE_START_BREAK=$($Snapshot.safe_start_break)"
        "MEMORY_USAGE_MB=$($Snapshot.memory_mb)"
        "CPU_USAGE_PCT=$($Snapshot.cpu_pct)"
    ) | Set-Content -Path $path -Encoding UTF8
}

Write-Line $logFile "EVERGREEN_START_TS=$($obsStart.ToString('yyyy-MM-dd HH:mm:ss K'))"
Write-Line $logFile "EVERGREEN_EXPECTED_END_TS=$($obsEnd.ToString('yyyy-MM-dd HH:mm:ss K'))"
Write-Line $logFile "CURRENT_GATE=NT-RUNTIME-EXPAND-5POS-7D"
Write-Line $logFile "ACTIVE_ROLE=HONEY"
Write-Line $logFile "-----"

$totalSnapshots = 0
$apiHealthWarnOrFailCount = 0
$orderRejectPeak = 0
$safeStartBreakCount = 0
$maxActiveSymbolObserved = 0
$watchdogRestartSignalCount = 0
$lastWatchdogAlive = $true

while ((Get-Date) -lt $obsEnd) {
    $now = Get-Date
    $health = Read-JsonHttp -Uri "http://127.0.0.1:8100/api/v1/ops/health"
    $runtime = Read-JsonHttp -Uri "http://127.0.0.1:8788/api/runtime"
    $positions = Read-JsonHttp -Uri "http://127.0.0.1:8100/api/v1/investor/positions"
    $latestRuntime = Get-LatestRuntimeEvent
    $orderCounts = Get-OrderCounters
    $procs = Get-MonitoredProcesses

    $runtimeJson = $null
    $healthJson = $null
    $healthStatus = "HTTP_ERROR"
    $engineAlive = ""
    if ($health.ok -and $health.body) {
        try {
            $healthJson = $health.body | ConvertFrom-Json
            $healthStatus = [string](Safe-JsonValue $healthJson "health_status" (Safe-JsonValue $healthJson "status" "OK"))
            $engineAlive = [string](Safe-JsonValue $healthJson "engine_alive" "")
        } catch {
            $healthStatus = "PARSE_ERROR"
        }
    }
    if ($runtime.ok -and $runtime.body) {
        try { $runtimeJson = $runtime.body | ConvertFrom-Json } catch {}
    }
    if ($healthStatus -ne "OK") { $apiHealthWarnOrFailCount++ }

    $activeSymbolCount = ""
    $activeSymbols = ""
    $openPositionCount = ""
    if ($runtimeJson) {
        $activeSymbolCount = [string](Safe-JsonValue $runtimeJson "scan_symbol_count" "")
        $openPositionCount = [string](Safe-JsonValue $runtimeJson "open_positions_count" "")
    }
    if ($latestRuntime) {
        $activeSymbolCount = [string](Safe-JsonValue $latestRuntime "active_symbol_count" $activeSymbolCount)
        $activeSymbols = @((Safe-JsonValue $latestRuntime "active_symbols" @())) -join ","
    }

    $watchdogCount = @($procs | Where-Object { $_.CommandLine -match "runtime_guard.ps1|phase5_autoguard.ps1" }).Count
    $watchdogAlive = ($watchdogCount -gt 0)
    if ($lastWatchdogAlive -and -not $watchdogAlive) { $watchdogRestartSignalCount++ }
    $lastWatchdogAlive = $watchdogAlive

    $safeStartState = Get-SafeStartState -RuntimeJson $runtimeJson
    if ($safeStartState -ne "OK") { $safeStartBreakCount++ }

    $memoryBytes = 0.0
    foreach ($proc in $procs) { $memoryBytes += [double]($proc.WorkingSetSize) }
    $memoryMb = [Math]::Round($memoryBytes / 1MB, 3)
    $cpuPct = Get-CpuUsageEstimate -Processes $procs

    $asCount = 0
    if ([int]::TryParse([string]$activeSymbolCount, [ref]$asCount)) {
        if ($asCount -gt $maxActiveSymbolObserved) { $maxActiveSymbolObserved = $asCount }
    }
    if ($orderCounts.reject -gt $orderRejectPeak) { $orderRejectPeak = $orderCounts.reject }

    Write-Line $logFile "TIMESTAMP=$($now.ToString('yyyy-MM-dd HH:mm:ss K'))"
    Write-Line $logFile "ENGINE_ALIVE=$engineAlive"
    Write-Line $logFile "WATCHDOG_STATUS=$watchdogAlive"
    Write-Line $logFile "API_HEALTH=$healthStatus"
    Write-Line $logFile "ORDER_SUBMIT_COUNT=$($orderCounts.submit)"
    Write-Line $logFile "ORDER_ACK_COUNT=$($orderCounts.ack)"
    Write-Line $logFile "ORDER_REJECT_COUNT=$($orderCounts.reject)"
    Write-Line $logFile "FILL_COUNT=$($orderCounts.fills)"
    Write-Line $logFile "OPEN_POSITION_COUNT=$openPositionCount"
    Write-Line $logFile "ACTIVE_SYMBOL_COUNT=$activeSymbolCount"
    Write-Line $logFile "ACTIVE_SYMBOLS=$activeSymbols"
    Write-Line $logFile "SAFE_START_BREAK=$safeStartState"
    Write-Line $logFile "MEMORY_USAGE_MB=$memoryMb"
    Write-Line $logFile "CPU_USAGE_PCT=$cpuPct"
    Write-Line $logFile "-----"

    $elapsedHours = ($now - $obsStart).TotalHours
    foreach ($checkpointHour in $checkpointHours) {
        if (-not $checkpointWritten.ContainsKey($checkpointHour) -and $elapsedHours -ge $checkpointHour) {
            Write-Checkpoint -Hour $checkpointHour -Snapshot @{
                ts = $now.ToString('yyyy-MM-dd HH:mm:ss K')
                engine_alive = $engineAlive
                watchdog_status = $watchdogAlive
                api_health = $healthStatus
                order_submit = $orderCounts.submit
                order_ack = $orderCounts.ack
                order_reject = $orderCounts.reject
                fills = $orderCounts.fills
                open_position_count = $openPositionCount
                active_symbol_count = $activeSymbolCount
                safe_start_break = $safeStartState
                memory_mb = $memoryMb
                cpu_pct = $cpuPct
            }
            $checkpointWritten[$checkpointHour] = $true
        }
    }

    $totalSnapshots++
    Start-Sleep -Seconds $IntervalSeconds
}

Write-Line $summaryFile "EVERGREEN_START_TS=$($obsStart.ToString('yyyy-MM-dd HH:mm:ss K'))"
Write-Line $summaryFile "EVERGREEN_END_TS=$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss K'))"
Write-Line $summaryFile "TOTAL_SNAPSHOTS=$totalSnapshots"
Write-Line $summaryFile "ORDER_SUBMIT_COUNT=$((Get-OrderCounters).submit)"
Write-Line $summaryFile "ORDER_ACK_COUNT=$((Get-OrderCounters).ack)"
Write-Line $summaryFile "ORDER_REJECT_COUNT=$((Get-OrderCounters).reject)"
Write-Line $summaryFile "FILL_COUNT=$((Get-OrderCounters).fills)"
Write-Line $summaryFile "MAX_ACTIVE_SYMBOL_OBSERVED=$maxActiveSymbolObserved"
Write-Line $summaryFile "WATCHDOG_RESTART_COUNT=$watchdogRestartSignalCount"
Write-Line $summaryFile "API_HEALTH_WARN_OR_FAIL_COUNT=$apiHealthWarnOrFailCount"
Write-Line $summaryFile "SAFE_START_BREAK_COUNT=$safeStartBreakCount"
Write-Line $summaryFile "FINAL_RUNTIME_STATUS=$(if ($apiHealthWarnOrFailCount -eq 0 -and $safeStartBreakCount -eq 0 -and $orderRejectPeak -eq 0) { 'PASS' } else { 'WARN_OR_FAIL_REVIEW_NEEDED' })"

@"
# Evergreen Runtime 7D Final Report

- EVERGREEN_START_TS: $($obsStart.ToString('yyyy-MM-dd HH:mm:ss K'))
- EVERGREEN_END_TS: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss K'))
- TOTAL_SNAPSHOTS: $totalSnapshots
- ORDER_SUBMIT_COUNT: $((Get-OrderCounters).submit)
- ORDER_ACK_COUNT: $((Get-OrderCounters).ack)
- ORDER_REJECT_COUNT: $((Get-OrderCounters).reject)
- FILL_COUNT: $((Get-OrderCounters).fills)
- MAX_ACTIVE_SYMBOL_OBSERVED: $maxActiveSymbolObserved
- WATCHDOG_RESTART_COUNT: $watchdogRestartSignalCount
- API_HEALTH_WARN_OR_FAIL_COUNT: $apiHealthWarnOrFailCount
- SAFE_START_BREAK_COUNT: $safeStartBreakCount
"@ | Set-Content -Path $finalReportFile -Encoding UTF8

