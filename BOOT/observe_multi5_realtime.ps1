param(
    [int]$IntervalSec = 60,
    [int]$DurationMinutes = 480,
    [string]$OutputJsonlPath = "",
    [string]$OutputStatusPath = ""
)

$ErrorActionPreference = "Continue"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

$runtimeLog = "C:\nt_v1\logs\runtime\multi5_runtime_events.jsonl"
$orderLog = "C:\nt_v1\logs\runtime\investor_order_api.jsonl"
$positionsUrl = "http://127.0.0.1:8100/api/v1/investor/positions"
$outDir = Resolve-NtRoleReportDir -RoleFolder "honey_execution_reports" -EnsureExists
$outJsonl = if ([string]::IsNullOrWhiteSpace($OutputJsonlPath)) { Join-Path $outDir "nt_phase2_realtime_observe_metrics.jsonl" } else { $OutputJsonlPath }
$outStatus = if ([string]::IsNullOrWhiteSpace($OutputStatusPath)) { Join-Path $outDir "nt_phase2_realtime_observe_status.txt" } else { $OutputStatusPath }

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Get-RootAlive {
    $roots = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*run_multi5_engine.py*"
    })
    return @{
        alive = ($roots.Count -gt 0)
        count = $roots.Count
        pids = (($roots | Select-Object -ExpandProperty ProcessId) -join ",")
    }
}

function Get-EntrySignalCount {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return 0 }
    $cnt = 0
    foreach ($line in Get-Content $Path) {
        if ($line -match '"engine_entry_attempted"\s*:\s*true') {
            $cnt += 1
        }
    }
    return $cnt
}

function Get-OrderCounts {
    param([string]$Path)
    $submit = 0
    $ack = 0
    $filled = 0
    if (-not (Test-Path $Path)) {
        return @{ submit = 0; ack = 0; filled = 0 }
    }
    foreach ($line in Get-Content $Path) {
        if ($line -match '"event_type"\s*:\s*"ORDER_API_REQUEST"') {
            $submit += 1
        }
        if ($line -match '"event_type"\s*:\s*"ORDER_API_RESPONSE"' -and $line -match '"exchange_order_id"\s*:\s*') {
            $ack += 1
        }
        if ($line -match '"event_type"\s*:\s*"ORDER_API_RESPONSE"' -and $line -match '"status"\s*:\s*"FILLED"') {
            $filled += 1
        }
    }
    return @{ submit = $submit; ack = $ack; filled = $filled }
}

function Get-PositionSnapshot {
    try {
        $resp = Invoke-RestMethod -Uri $positionsUrl -Method Get -TimeoutSec 20
    } catch {
        return @{
            ok = $false
            openCount = 0
            openSymbols = @()
            pnl = 0.0
            longCount = 0
            shortCount = 0
            totalExposure = 0.0
        }
    }
    $openSymbols = @()
    $pnl = 0.0
    $longCount = 0
    $shortCount = 0
    $totalExposure = 0.0
    foreach ($p in $resp.positions) {
        $qty = 0.0
        try { $qty = [double]$p.positionAmt } catch { $qty = 0.0 }
        if ([math]::Abs($qty) -gt 0.0) {
            $openSymbols += [string]$p.symbol
            if ($qty -gt 0) { $longCount += 1 } elseif ($qty -lt 0) { $shortCount += 1 }
            $upnl = 0.0
            try { $upnl = [double]$p.unRealizedProfit } catch { $upnl = 0.0 }
            $pnl += $upnl
            $mark = 0.0
            try { $mark = [double]$p.markPrice } catch { $mark = 0.0 }
            $totalExposure += ([math]::Abs($qty) * $mark)
        }
    }
    return @{
        ok = [bool]$resp.ok
        openCount = $openSymbols.Count
        openSymbols = $openSymbols
        pnl = $pnl
        longCount = $longCount
        shortCount = $shortCount
        totalExposure = $totalExposure
    }
}

$start = Get-Date
$endAt = $start.AddMinutes($DurationMinutes)
$positionOpenEventCount = 0
$positionCloseEventCount = 0
$prevOpen = @()

Set-Content -Path $outStatus -Encoding UTF8 -Value @(
    "OBSERVE_STARTED_AT=$($start.ToString('s'))"
    "OBSERVE_DURATION_MIN=$DurationMinutes"
    "OBSERVE_INTERVAL_SEC=$IntervalSec"
    "OBSERVE_STATUS=RUNNING"
)

while ((Get-Date) -lt $endAt) {
    $engine = Get-RootAlive
    $entrySignals = Get-EntrySignalCount -Path $runtimeLog
    $orders = Get-OrderCounts -Path $orderLog
    $pos = Get-PositionSnapshot

    $currentOpen = @($pos.openSymbols)
    $openedNow = @($currentOpen | Where-Object { $_ -notin $prevOpen })
    $closedNow = @($prevOpen | Where-Object { $_ -notin $currentOpen })
    $positionOpenEventCount += $openedNow.Count
    $positionCloseEventCount += $closedNow.Count
    $prevOpen = $currentOpen

    $row = [ordered]@{
        ts = (Get-Date).ToString("o")
        ENGINE_ALIVE = [bool]$engine.alive
        ENGINE_ROOT_COUNT = [int]$engine.count
        ENGINE_ROOT_PIDS = [string]$engine.pids
        ENTRY_SIGNAL_COUNT = [int]$entrySignals
        ORDER_SUBMIT_COUNT = [int]$orders.submit
        ORDER_ACK_COUNT = [int]$orders.ack
        ORDER_FILLED_COUNT = [int]$orders.filled
        POSITION_OPEN_EVENT_COUNT = [int]$positionOpenEventCount
        POSITION_CLOSE_EVENT_COUNT = [int]$positionCloseEventCount
        # Backward compatibility
        POSITION_CLOSE_COUNT = [int]$positionCloseEventCount
        OPEN_POSITIONS_COUNT = [int]$pos.openCount
        LONG_POSITION_COUNT = [int]$pos.longCount
        SHORT_POSITION_COUNT = [int]$pos.shortCount
        TOTAL_EXPOSURE = [double]$pos.totalExposure
        REALTIME_PNL = [double]$pos.pnl
        OPEN_POSITION_SYMBOLS = ($currentOpen -join ",")
        POSITION_API_OK = [bool]$pos.ok
    }
    Add-Content -Path $outJsonl -Encoding UTF8 -Value ($row | ConvertTo-Json -Compress)
    Set-Content -Path $outStatus -Encoding UTF8 -Value @(
        "OBSERVE_STARTED_AT=$($start.ToString('s'))"
        "OBSERVE_DURATION_MIN=$DurationMinutes"
        "OBSERVE_INTERVAL_SEC=$IntervalSec"
        "OBSERVE_STATUS=RUNNING"
        "ORDER_ACK_COUNT=$($orders.ack)"
        "ORDER_FILLED_COUNT=$($orders.filled)"
        "POSITION_OPEN_EVENT_COUNT=$positionOpenEventCount"
        "POSITION_CLOSE_EVENT_COUNT=$positionCloseEventCount"
        "OPEN_POSITIONS_COUNT=$($pos.openCount)"
        "LONG_POSITION_COUNT=$($pos.longCount)"
        "SHORT_POSITION_COUNT=$($pos.shortCount)"
        "TOTAL_EXPOSURE=$($pos.totalExposure)"
    )
    Start-Sleep -Seconds $IntervalSec
}

Set-Content -Path $outStatus -Encoding UTF8 -Value @(
    "OBSERVE_STARTED_AT=$($start.ToString('s'))"
    "OBSERVE_ENDED_AT=$((Get-Date).ToString('s'))"
    "OBSERVE_DURATION_MIN=$DurationMinutes"
    "OBSERVE_INTERVAL_SEC=$IntervalSec"
    "OBSERVE_OUTPUT=$outJsonl"
    "OBSERVE_STATUS=COMPLETED"
)


