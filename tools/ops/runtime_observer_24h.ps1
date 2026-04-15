param(
    [string]$BaseDir = "C:\nt_v1\data\runtime_observation",
    [int]$DurationHours = 24,
    [int]$IntervalSeconds = 300
)

$ErrorActionPreference = "Continue"

$obsStart = Get-Date
$obsEnd = $obsStart.AddHours($DurationHours)

$logFile = Join-Path $BaseDir "runtime_observation_24h_log.txt"
$orderFile = Join-Path $BaseDir "runtime_observation_24h_orders.txt"
$summaryFile = Join-Path $BaseDir "runtime_observation_24h_summary.txt"
$engineLogPath = "C:\nt_v1\logs\runtime\multi5_runtime_events.jsonl"
$orderEventLogPath = "C:\nt_v1\logs\runtime\profitmax_v1_events.jsonl"

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

function Get-HealthJson {
    return Read-JsonHttp -Uri "http://127.0.0.1:8100/api/v1/ops/health"
}

function Get-PositionsJson {
    return Read-JsonHttp -Uri "http://127.0.0.1:8100/api/v1/investor/positions"
}

function Get-ObserverProcesses {
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -match "run_multi5_engine.py|profitmax_v1_runner.py|runtime_guard.ps1" -and
        $_.CommandLine -notmatch "runtime_observer_24h.ps1"
    } | Select-Object ProcessId, ParentProcessId, Name, CommandLine)
}

function Safe-JsonValue {
    param($obj, [string]$name, $default = "")
    if ($null -ne $obj -and $null -ne $obj.PSObject.Properties[$name]) {
        return $obj.$name
    }
    return $default
}

function Get-LatestRuntimeEvent {
    if (-not (Test-Path $engineLogPath)) {
        return $null
    }
    $line = Get-Content -Path $engineLogPath -Tail 1 -ErrorAction SilentlyContinue
    if (-not $line) {
        return $null
    }
    try {
        return $line | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-OrderCounters {
    $counts = @{
        submit = 0
        ack = 0
        reject = 0
        fills = 0
    }
    if (-not (Test-Path $orderEventLogPath)) {
        return $counts
    }

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
        } catch {
        }
    }

    return $counts
}

function Get-SafeStartState {
    param($Processes)
    $engineCmds = @($Processes | Where-Object { $_.CommandLine -match "run_multi5_engine.py" } | Select-Object -ExpandProperty CommandLine)
    $workerCmds = @($Processes | Where-Object { $_.CommandLine -match "profitmax_v1_runner.py" } | Select-Object -ExpandProperty CommandLine)

    if ($engineCmds.Count -eq 0) {
        return "NO_ENGINE"
    }

    $engineOkay = $false
    foreach ($cmd in $engineCmds) {
        if ($cmd -match "--max-open-positions\s+(?!1)\d+" -or $cmd -match "--max-symbol-active\s+(?!1)\d+" -or $cmd -match "--max-position-per-symbol\s+(?!1)\d+") {
            return "BROKEN"
        }
        if ($cmd -match "--max-open-positions\s+1" -and $cmd -match "--max-symbol-active\s+1" -and $cmd -match "--max-position-per-symbol\s+1") {
            $engineOkay = $true
        }
    }

    $workerOkay = $true
    foreach ($cmd in $workerCmds) {
        if ($cmd -match "--max-positions\s+(?!1)\d+") {
            return "BROKEN"
        }
        if ($cmd -match "--max-positions\s+1") {
            continue
        }
    }

    if ($engineOkay -and $workerOkay) {
        return "OK"
    }
    return "BROKEN"
}

Write-Line $logFile "OBS_START_TIME=$($obsStart.ToString('yyyy-MM-dd HH:mm:ss K'))"
Write-Line $logFile "OBS_EXPECTED_END_TIME=$($obsEnd.ToString('yyyy-MM-dd HH:mm:ss K'))"
Write-Line $logFile "CURRENT_GATE=NT-RUNTIME-OBSERVATION-24H-AUTOLOG"
Write-Line $logFile "SAFE_START_MODE=ACTIVE"
Write-Line $logFile "HOSTNAME=$env:COMPUTERNAME"
Write-Line $logFile "USERNAME=$env:USERNAME"
Write-Line $logFile "-----"

$totalSnapshots = 0
$apiWarnCount = 0
$safeStartBrokenCount = 0
$watchdogSignalCount = 0
$maxActiveSymbolObserved = 0
$lastWatchdogAlive = $true

while ((Get-Date) -lt $obsEnd) {
    $now = Get-Date
    $health = Get-HealthJson
    $positions = Get-PositionsJson
    $procs = Get-ObserverProcesses
    $latestRuntime = Get-LatestRuntimeEvent
    $orderCounts = Get-OrderCounters

    $engineCount = @($procs | Where-Object { $_.CommandLine -match "run_multi5_engine.py|profitmax_v1_runner.py" }).Count
    $watchdogCount = @($procs | Where-Object { $_.CommandLine -match "runtime_guard.ps1" }).Count
    $pidSet = (@($procs | Select-Object -ExpandProperty ProcessId | Sort-Object -Unique) -join ",")

    $healthStatus = ""
    $engineAlive = ""
    $activeSymbolCount = ""
    $activeSymbols = ""

    if ($health.ok -and $health.body) {
        try {
            $json = $health.body | ConvertFrom-Json
            $healthStatus = [string](Safe-JsonValue $json "health_status" (Safe-JsonValue $json "status" $health.status))
            $engineAlive = [string](Safe-JsonValue $json "engine_alive" "")
        } catch {
            $healthStatus = "PARSE_ERROR"
            $engineAlive = ""
            $apiWarnCount++
        }
    } else {
        $healthStatus = "HTTP_ERROR"
        $engineAlive = ""
        $apiWarnCount++
    }

    if ($latestRuntime) {
        $activeSymbolCount = [string](Safe-JsonValue $latestRuntime "active_symbol_count" "")
        $activeSymbols = @((Safe-JsonValue $latestRuntime "active_symbols" @())) -join ","
    }

    if ($healthStatus -ne "OK") {
        $apiWarnCount++
    }

    $safeStartState = Get-SafeStartState -Processes $procs
    if ($safeStartState -eq "BROKEN") {
        $safeStartBrokenCount++
    }

    $asCount = 0
    if ([int]::TryParse([string]$activeSymbolCount, [ref]$asCount)) {
        if ($asCount -gt $maxActiveSymbolObserved) {
            $maxActiveSymbolObserved = $asCount
        }
    }

    $watchdogAlive = ($watchdogCount -gt 0)
    if ($lastWatchdogAlive -and -not $watchdogAlive) {
        $watchdogSignalCount++
    }
    $lastWatchdogAlive = $watchdogAlive

    Write-Line $logFile "TIMESTAMP=$($now.ToString('yyyy-MM-dd HH:mm:ss K'))"
    Write-Line $logFile "ENGINE_PROCESS_COUNT=$engineCount"
    Write-Line $logFile "ENGINE_PID_SET=$pidSet"
    Write-Line $logFile "WATCHDOG_PROCESS_COUNT=$watchdogCount"
    Write-Line $logFile "API_8100_HEALTH_STATUS=$healthStatus"
    Write-Line $logFile "API_8100_ENGINE_ALIVE=$engineAlive"
    Write-Line $logFile "ACTIVE_SYMBOL_COUNT=$activeSymbolCount"
    Write-Line $logFile "ACTIVE_SYMBOLS=$activeSymbols"
    Write-Line $logFile "ORDER_SUBMIT_COUNT_CUM=$($orderCounts.submit)"
    Write-Line $logFile "ORDER_ACK_COUNT_CUM=$($orderCounts.ack)"
    Write-Line $logFile "ORDER_REJECT_COUNT_CUM=$($orderCounts.reject)"
    Write-Line $logFile "FILLS_COUNT_CUM=$($orderCounts.fills)"
    Write-Line $logFile "SAFE_START_PARAMETER_STATE=$safeStartState"
    Write-Line $logFile "-----"

    Write-Line $orderFile "TIMESTAMP=$($now.ToString('yyyy-MM-dd HH:mm:ss K'))"
    Write-Line $orderFile "POSITIONS_STATUS=$($positions.status)"
    if ($positions.ok) {
        Write-Line $orderFile "POSITIONS_BODY=$($positions.body)"
    } else {
        Write-Line $orderFile "POSITIONS_BODY_ERROR=$($positions.error)"
    }
    Write-Line $orderFile "-----"

    $totalSnapshots++
    Start-Sleep -Seconds $IntervalSeconds
}

Write-Line $summaryFile "OBS_START_TIME=$($obsStart.ToString('yyyy-MM-dd HH:mm:ss K'))"
Write-Line $summaryFile "OBS_END_TIME=$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss K'))"
Write-Line $summaryFile "TOTAL_SNAPSHOTS=$totalSnapshots"
Write-Line $summaryFile "TOTAL_ORDER_SUBMIT=$((Get-OrderCounters).submit)"
Write-Line $summaryFile "TOTAL_ORDER_ACK=$((Get-OrderCounters).ack)"
Write-Line $summaryFile "TOTAL_ORDER_REJECT=$((Get-OrderCounters).reject)"
Write-Line $summaryFile "TOTAL_FILLS=$((Get-OrderCounters).fills)"
Write-Line $summaryFile "MAX_ACTIVE_SYMBOL_OBSERVED=$maxActiveSymbolObserved"
Write-Line $summaryFile "WATCHDOG_RESTART_SIGNAL_COUNT=$watchdogSignalCount"
Write-Line $summaryFile "API_HEALTH_WARN_OR_FAIL_COUNT=$apiWarnCount"
Write-Line $summaryFile "SAFE_START_BROKEN_COUNT=$safeStartBrokenCount"

$finalStatus = "PASS"
if ($apiWarnCount -gt 0 -or $safeStartBrokenCount -gt 0) {
    $finalStatus = "WARN_OR_FAIL_REVIEW_NEEDED"
}
Write-Line $summaryFile "FINAL_RUNTIME_STATUS=$finalStatus"


