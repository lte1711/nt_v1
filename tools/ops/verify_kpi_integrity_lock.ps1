param(
    [string]$SnapshotPath = "C:\next-trade-ver1.0\logs\runtime\portfolio_metrics_snapshot.json",
    [string]$DashboardHtmlPath = "C:\next-trade-ver1.0\tools\dashboard\multi5_dashboard.html",
    [string]$ApiUrl = "http://127.0.0.1:8788/api/runtime"
)

$ErrorActionPreference = "Stop"

function To-JsonBool([bool]$value) {
    if ($value) { return $true }
    return $false
}

$requiredSnapshotKeys = @("total_trades", "realized_pnl", "win_rate", "drawdown")
$requiredApiKeys = @("kpi_total_trades", "kpi_realized_pnl", "kpi_win_rate", "kpi_drawdown")

$snapshot = Get-Content $SnapshotPath -Raw | ConvertFrom-Json
$api = (Invoke-WebRequest -UseBasicParsing -Uri ($ApiUrl + "?t=" + [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) -TimeoutSec 10).Content | ConvertFrom-Json
$html = Get-Content $DashboardHtmlPath -Raw

$snapshotHasAll = $true
foreach ($k in $requiredSnapshotKeys) {
    if ($null -eq $snapshot.$k) { $snapshotHasAll = $false }
}

$apiHasAll = $true
foreach ($k in $requiredApiKeys) {
    if ($null -eq $api.$k -or "$($api.$k)" -eq "") { $apiHasAll = $false }
}

$htmlUsesStandardKpiOnly = (
    $html -match 'id="kpi_total_trades"' -and
    $html -match 'id="kpi_realized_pnl"' -and
    $html -match 'id="kpi_win_rate"' -and
    $html -match 'id="kpi_drawdown"' -and
    $html -notmatch 'id="portfolio_snapshot_realized_pnl"' -and
    $html -notmatch 'portfolio_snapshot_realized_pnl'
)

$typeConsistency = (
    ($snapshot.total_trades -is [int] -or $snapshot.total_trades -is [long]) -and
    ($snapshot.realized_pnl -is [double] -or $snapshot.realized_pnl -is [decimal]) -and
    ($snapshot.win_rate -is [double] -or $snapshot.win_rate -is [decimal]) -and
    ($snapshot.drawdown -is [double] -or $snapshot.drawdown -is [decimal]) -and
    ($api.kpi_total_trades -is [int] -or $api.kpi_total_trades -is [long]) -and
    ($api.kpi_realized_pnl -is [string]) -and
    ($api.kpi_win_rate -is [string]) -and
    ($api.kpi_drawdown -is [string])
)

$snapshotApiMatch = (
    [int]$snapshot.total_trades -eq [int]$api.kpi_total_trades -and
    [double]$snapshot.realized_pnl -eq [double]$api.kpi_realized_pnl -and
    [double]$snapshot.win_rate -eq [double]$api.kpi_win_rate -and
    [double]$snapshot.drawdown -eq [double]$api.kpi_drawdown
)

[pscustomobject]@{
    snapshot_file_read = To-JsonBool (Test-Path $SnapshotPath)
    snapshot_has_all_kpi = To-JsonBool $snapshotHasAll
    api_has_all_kpi = To-JsonBool $apiHasAll
    dashboard_kpi_binding_locked = To-JsonBool $htmlUsesStandardKpiOnly
    api_dashboard_match = To-JsonBool $htmlUsesStandardKpiOnly
    type_consistency = To-JsonBool $typeConsistency
    snapshot_api_match = To-JsonBool $snapshotApiMatch
    snapshot_values = [pscustomobject]@{
        total_trades = $snapshot.total_trades
        realized_pnl = $snapshot.realized_pnl
        win_rate = $snapshot.win_rate
        drawdown = $snapshot.drawdown
    }
    api_values = [pscustomobject]@{
        kpi_total_trades = $api.kpi_total_trades
        kpi_realized_pnl = $api.kpi_realized_pnl
        kpi_win_rate = $api.kpi_win_rate
        kpi_drawdown = $api.kpi_drawdown
    }
    drift_fail_conditions = @(
        "snapshot != api",
        "api != dashboard display key set",
        "missing KPI key",
        "KPI value type change"
    )
} | ConvertTo-Json -Depth 5
