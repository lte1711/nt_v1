param(
    [int]$IntervalSec = 60,
    [int]$DurationMinutes = 360
)

$ErrorActionPreference = "Continue"

$reportDir = "C:\next-trade-ver1.0\reports\phase6_runtime"
$runtimeOut = Join-Path $reportDir "runtime_events.jsonl"
$orderOut = Join-Path $reportDir "order_events.jsonl"
$positionOut = Join-Path $reportDir "position_events.jsonl"
$pnlOut = Join-Path $reportDir "pnl_events.jsonl"
$statusOut = Join-Path $reportDir "phase6_runtime_status.txt"
$orderSource = "C:\next-trade-ver1.0\logs\runtime\investor_order_api.jsonl"

New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

function Append-JsonLine([string]$path, [hashtable]$row) {
    Add-Content -Path $path -Encoding UTF8 -Value ($row | ConvertTo-Json -Compress)
}

$start = Get-Date
$endAt = $start.AddMinutes($DurationMinutes)
$orderLineCursor = if (Test-Path $orderSource) { (Get-Content $orderSource | Measure-Object -Line).Lines } else { 0 }

Set-Content -Path $statusOut -Encoding UTF8 -Value @(
    "PHASE6_COLLECTOR_STARTED_AT=$($start.ToString('s'))"
    "PHASE6_COLLECTOR_DURATION_MIN=$DurationMinutes"
    "PHASE6_COLLECTOR_INTERVAL_SEC=$IntervalSec"
    "PHASE6_COLLECTOR_STATUS=RUNNING"
)

while ((Get-Date) -lt $endAt) {
    $now = Get-Date

    # runtime snapshot
    try {
        $rt = Invoke-RestMethod -Uri "http://127.0.0.1:8787/api/runtime" -TimeoutSec 20
        Append-JsonLine -path $runtimeOut -row @{
            ts = $now.ToString("o")
            engine_status = $rt.engine_status
            runtime_alive = [bool]$rt.runtime_alive
            scan_symbol_count = [int]$rt.scan_symbol_count
            active_mode = [string]$rt.operation_mode
            entry_signal_count = [int]$rt.entry_attempts
            order_ack_count = [int]$rt.order_ack_count
            open_positions_count = [int]$rt.open_positions_count
            active_symbol_count = [int]$rt.open_positions_count
            source = "dashboard_api_runtime"
        }
        Append-JsonLine -path $pnlOut -row @{
            ts = $now.ToString("o")
            realized_pnl = [string]$rt.session_realized_pnl
            unrealized_pnl = [double]$rt.total_exposure  # exposure proxy retained separately from realized
            pnl_realtime = [bool]$rt.pnl_realtime
            pnl_age_sec = [int]$rt.pnl_age_sec
            daily_realized_pnl = [string]$rt.daily_realized_pnl
            source = "dashboard_api_runtime"
        }
    } catch {
        Append-JsonLine -path $runtimeOut -row @{
            ts = $now.ToString("o")
            runtime_api_error = $_.Exception.Message
            source = "dashboard_api_runtime"
        }
    }

    # position snapshot
    try {
        $pos = Invoke-RestMethod -Uri "http://127.0.0.1:8100/api/v1/investor/positions" -TimeoutSec 20
        $open = @()
        foreach ($p in $pos.positions) {
            $qty = 0.0
            try { $qty = [double]$p.positionAmt } catch { $qty = 0.0 }
            if ([math]::Abs($qty) -gt 0.0) {
                $open += @{
                    symbol = [string]$p.symbol
                    positionAmt = [string]$p.positionAmt
                    entryPrice = [string]$p.entryPrice
                    markPrice = [string]$p.markPrice
                    unRealizedProfit = [string]$p.unRealizedProfit
                    positionSide = [string]$p.positionSide
                }
            }
        }
        Append-JsonLine -path $positionOut -row @{
            ts = $now.ToString("o")
            open_position_count = $open.Count
            open_positions = $open
            source = "api_8100_positions"
        }
    } catch {
        Append-JsonLine -path $positionOut -row @{
            ts = $now.ToString("o")
            position_api_error = $_.Exception.Message
            source = "api_8100_positions"
        }
    }

    # order stream append (delta-copy)
    if (Test-Path $orderSource) {
        $totalLines = (Get-Content $orderSource | Measure-Object -Line).Lines
        if ($totalLines -gt $orderLineCursor) {
            $newLines = Get-Content $orderSource | Select-Object -Skip $orderLineCursor
            foreach ($line in $newLines) {
                if (-not $line.Trim()) { continue }
                try {
                    $obj = $line | ConvertFrom-Json
                    Append-JsonLine -path $orderOut -row @{
                        ts = $now.ToString("o")
                        event_ts = [string]$obj.ts
                        event_type = [string]$obj.event_type
                        symbol = [string]$obj.symbol
                        status = [string]$obj.status
                        exchange_order_id = [string]$obj.exchange_order_id
                        side = [string]$obj.side
                        entry_request_qty = [string]$obj.entry_request_qty
                        entry_filled_qty = [string]$obj.entry_filled_qty
                        source = "investor_order_api"
                    }
                } catch {
                    Append-JsonLine -path $orderOut -row @{
                        ts = $now.ToString("o")
                        raw = $line
                        source = "investor_order_api"
                    }
                }
            }
            $orderLineCursor = $totalLines
        }
    }

    Set-Content -Path $statusOut -Encoding UTF8 -Value @(
        "PHASE6_COLLECTOR_STARTED_AT=$($start.ToString('s'))"
        "PHASE6_COLLECTOR_DURATION_MIN=$DurationMinutes"
        "PHASE6_COLLECTOR_INTERVAL_SEC=$IntervalSec"
        "PHASE6_COLLECTOR_STATUS=RUNNING"
        "LAST_TICK_KST=$($now.ToString('yyyy-MM-dd HH:mm:ss'))"
        "ORDER_SOURCE_CURSOR=$orderLineCursor"
    )

    Start-Sleep -Seconds $IntervalSec
}

Set-Content -Path $statusOut -Encoding UTF8 -Value @(
    "PHASE6_COLLECTOR_STARTED_AT=$($start.ToString('s'))"
    "PHASE6_COLLECTOR_ENDED_AT=$((Get-Date).ToString('s'))"
    "PHASE6_COLLECTOR_DURATION_MIN=$DurationMinutes"
    "PHASE6_COLLECTOR_INTERVAL_SEC=$IntervalSec"
    "PHASE6_COLLECTOR_STATUS=COMPLETED"
)


