param(
    [int]$IntervalSec = 60,
    [int]$DurationMinutes = 1440
)

$ErrorActionPreference = "Continue"
. "C:\next-trade-ver1.0\BOOT\report_path_resolver.ps1"

$reportDir = Resolve-NtRoleReportDir -RoleFolder "honey_execution_reports" -EnsureExists
$metricsFile = Join-Path $reportDir "nt_phase5_multi_symbol_metrics.jsonl"

New-Item -ItemType Directory -Force -Path $reportDir | Out-Null

function Get-LatestMetric {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return $null }
    $line = Get-Content $Path -Tail 1
    if (-not $line) { return $null }
    try { return ($line | ConvertFrom-Json) } catch { return $null }
}

function Get-StatsFromAllRows {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        return @{
            maxOpen = 0
            symbolDistribution = ""
        }
    }

    $maxOpen = 0
    $symbolCounts = @{}
    foreach ($line in Get-Content $Path) {
        if (-not $line) { continue }
        try { $row = $line | ConvertFrom-Json } catch { continue }
        $openCount = 0
        try { $openCount = [int]$row.OPEN_POSITIONS_COUNT } catch { $openCount = 0 }
        if ($openCount -gt $maxOpen) { $maxOpen = $openCount }
        $symbolsRaw = [string]$row.OPEN_POSITION_SYMBOLS
        if ($symbolsRaw) {
            foreach ($s in $symbolsRaw.Split(",", [System.StringSplitOptions]::RemoveEmptyEntries)) {
                $k = $s.Trim().ToUpper()
                if (-not $k) { continue }
                if (-not $symbolCounts.ContainsKey($k)) { $symbolCounts[$k] = 0 }
                $symbolCounts[$k] += 1
            }
        }
    }

    $pairs = @()
    foreach ($k in ($symbolCounts.Keys | Sort-Object)) {
        $pairs += ("{0}:{1}" -f $k, $symbolCounts[$k])
    }
    return @{
        maxOpen = $maxOpen
        symbolDistribution = ($pairs -join ",")
    }
}

function Write-MilestoneReport {
    param(
        [string]$Label,
        [object]$M,
        [hashtable]$Agg
    )
    if ($null -eq $M) { return }
    $path = Join-Path $reportDir ("nt_phase5_portfolio_observe_{0}.txt" -f $Label.ToLower())
    $firstMulti = "NO"
    try {
        if ([int]$M.OPEN_POSITIONS_COUNT -ge 2) { $firstMulti = "YES" }
    } catch {}

    $lines = @(
        ("ENGINE_ALIVE={0}" -f $M.ENGINE_ALIVE),
        ("ENTRY_SIGNAL_COUNT={0}" -f $M.ENTRY_SIGNAL_COUNT),
        ("ORDER_SUBMIT_COUNT={0}" -f $M.ORDER_SUBMIT_COUNT),
        ("ORDER_FILLED_COUNT={0}" -f $M.ORDER_FILLED_COUNT),
        ("POSITION_OPEN_EVENT_COUNT={0}" -f $M.POSITION_OPEN_EVENT_COUNT),
        ("POSITION_CLOSE_EVENT_COUNT={0}" -f $M.POSITION_CLOSE_EVENT_COUNT),
        ("OPEN_POSITIONS_COUNT={0}" -f $M.OPEN_POSITIONS_COUNT),
        ("OPEN_POSITION_SYMBOLS={0}" -f $M.OPEN_POSITION_SYMBOLS),
        ("LONG_POSITION_COUNT={0}" -f $M.LONG_POSITION_COUNT),
        ("SHORT_POSITION_COUNT={0}" -f $M.SHORT_POSITION_COUNT),
        ("TOTAL_EXPOSURE={0}" -f $M.TOTAL_EXPOSURE),
        ("MAX_CONCURRENT_POSITIONS_REACHED={0}" -f $Agg.maxOpen),
        ("SYMBOL_DISTRIBUTION={0}" -f $Agg.symbolDistribution),
        ("REALTIME_PNL={0}" -f $M.REALTIME_PNL),
        ("FIRST_MULTI_POSITION_OPEN={0}" -f $firstMulti),
        "TP_HIT_COUNT=UNKNOWN",
        "SL_HIT_COUNT=UNKNOWN",
        ("REPORT_LABEL={0}" -f $Label),
        ("REPORT_TS={0}" -f (Get-Date).ToString("o"))
    )
    Set-Content -Path $path -Encoding UTF8 -Value $lines
}

$milestones = @(
    @{ min = 15; label = "15m"; done = $false },
    @{ min = 30; label = "30m"; done = $false },
    @{ min = 60; label = "60m"; done = $false },
    @{ min = 180; label = "3h"; done = $false },
    @{ min = 360; label = "6h"; done = $false },
    @{ min = 1440; label = "24h"; done = $false }
)

$start = Get-Date
$endAt = $start.AddMinutes($DurationMinutes)

while ((Get-Date) -lt $endAt) {
    $elapsedMin = [int]((Get-Date) - $start).TotalMinutes
    $m = Get-LatestMetric -Path $metricsFile
    $agg = Get-StatsFromAllRows -Path $metricsFile

    foreach ($ms in $milestones) {
        if (-not $ms.done -and $elapsedMin -ge $ms.min) {
            Write-MilestoneReport -Label $ms.label -M $m -Agg $agg
            $ms.done = $true
        }
    }
    Start-Sleep -Seconds $IntervalSec
}

$mFinal = Get-LatestMetric -Path $metricsFile
$aggFinal = Get-StatsFromAllRows -Path $metricsFile
Write-MilestoneReport -Label "24h_final" -M $mFinal -Agg $aggFinal
