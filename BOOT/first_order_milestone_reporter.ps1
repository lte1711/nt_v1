param(
    [int]$IntervalSec = 60,
    [int]$DurationMinutes = 360
)

$ErrorActionPreference = "Continue"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

$reportDir = Resolve-NtRoleReportDir -RoleFolder "honey_execution_reports" -EnsureExists
$metricsFile = Join-Path $reportDir "nt_phase2_realtime_observe_metrics.jsonl"
$statusFile = Join-Path $reportDir "nt_phase2_realtime_observe_status.txt"
$positionsUrl = "http://127.0.0.1:8100/api/v1/investor/positions"

New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

function Get-StartTime {
    if (-not (Test-Path $statusFile)) { return $null }
    $line = Get-Content $statusFile | Where-Object { $_ -like "OBSERVE_STARTED_AT=*" } | Select-Object -First 1
    if (-not $line) { return $null }
    $raw = $line.Substring("OBSERVE_STARTED_AT=".Length)
    try { return [datetime]::Parse($raw) } catch { return $null }
}

function Get-LatestMetrics {
    if (-not (Test-Path $metricsFile)) { return $null }
    $last = Get-Content $metricsFile -Tail 1
    if (-not $last) { return $null }
    try { return $last | ConvertFrom-Json } catch { return $null }
}

function Get-FirstOpenPosition {
    try {
        $resp = Invoke-RestMethod -Uri $positionsUrl -Method Get -TimeoutSec 20
    } catch {
        return $null
    }
    foreach ($p in $resp.positions) {
        $qty = 0.0
        try { $qty = [double]$p.positionAmt } catch { $qty = 0.0 }
        if ([math]::Abs($qty) -gt 0.0) {
            return $p
        }
    }
    return $null
}

function Get-ChainStatus($m) {
    if ($null -eq $m) { return @{ chain = "UNKNOWN"; gate = "RUNNING" } }
    if ([int]$m.ORDER_FILLED_COUNT -gt 0 -and [int]$m.POSITION_OPEN_EVENT_COUNT -gt 0) {
        return @{ chain = "CONFIRMED"; gate = "PASS" }
    }
    if ([int]$m.ENTRY_SIGNAL_COUNT -gt 0 -and [int]$m.ORDER_SUBMIT_COUNT -eq 0) {
        return @{ chain = "NO_EXECUTION"; gate = "RUNNING" }
    }
    return @{ chain = "AWAITING"; gate = "RUNNING" }
}

function Write-Report($label, $m) {
    $chain = Get-ChainStatus $m
    $firstPos = Get-FirstOpenPosition
    $symbol = ""
    $side = ""
    $qty = ""
    $entry = ""
    if ($firstPos) {
        $symbol = [string]$firstPos.symbol
        $qty = [string]$firstPos.positionAmt
        $entry = [string]$firstPos.entryPrice
        try {
            $q = [double]$firstPos.positionAmt
            if ($q -gt 0) { $side = "LONG" } elseif ($q -lt 0) { $side = "SHORT" } else { $side = [string]$firstPos.positionSide }
        } catch {
            $side = [string]$firstPos.positionSide
        }
    }

    $path = Join-Path $reportDir ("nt_multi5_first_order_observe_{0}.txt" -f $label.ToLower())
    $lines = @(
        "ENGINE_ALIVE=$($m.ENGINE_ALIVE)"
        "ENTRY_SIGNAL_COUNT=$($m.ENTRY_SIGNAL_COUNT)"
        "ORDER_SUBMIT_COUNT=$($m.ORDER_SUBMIT_COUNT)"
        "ORDER_ACK_COUNT=$($m.ORDER_ACK_COUNT)"
        "ORDER_FILLED_COUNT=$($m.ORDER_FILLED_COUNT)"
        "POSITION_OPEN_EVENT_COUNT=$($m.POSITION_OPEN_EVENT_COUNT)"
        "POSITION_CLOSE_EVENT_COUNT=$($m.POSITION_CLOSE_EVENT_COUNT)"
        # Backward compatibility key requested
        "POSITION_CLOSE_COUNT=$($m.POSITION_CLOSE_COUNT)"
        "REALTIME_PNL=$($m.REALTIME_PNL)"
        ""
        "FIRST_ORDER_SYMBOL=$symbol"
        "FIRST_ORDER_SIDE=$side"
        "FIRST_ORDER_QTY=$qty"
        "FIRST_ORDER_ENTRY_PRICE=$entry"
        ""
        "FIRST_ORDER_CHAIN_STATUS=$($chain.chain)"
        "MULTI5_FIRST_ORDER_GATE_STATUS=$($chain.gate)"
    )
    Set-Content -Path $path -Value $lines -Encoding UTF8
}

$start = Get-StartTime
if ($null -eq $start) { exit 1 }
$endAt = (Get-Date).AddMinutes($DurationMinutes)

$milestones = @(
    @{ min = 15; label = "15m" },
    @{ min = 30; label = "30m" },
    @{ min = 60; label = "60m" },
    @{ min = 180; label = "3h" },
    @{ min = 360; label = "6h" }
)

while ((Get-Date) -lt $endAt) {
    $elapsed = ((Get-Date) - $start).TotalMinutes
    $m = Get-LatestMetrics
    foreach ($ms in $milestones) {
        $targetFile = Join-Path $reportDir ("nt_multi5_first_order_observe_{0}.txt" -f $ms.label)
        if ($elapsed -ge $ms.min -and -not (Test-Path $targetFile) -and $m) {
            Write-Report -label $ms.label -m $m
        }
    }
    Start-Sleep -Seconds $IntervalSec
}

