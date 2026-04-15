param(
    [int]$IntervalMinutes = 5,
    [int]$Iterations = 1,
    [string]$OutputDir = "C:\nt_v1\reports\kpi_drift_monitor"
)

$ErrorActionPreference = "Stop"
$verifyScript = "C:\nt_v1\tools\ops\verify_kpi_integrity_lock.ps1"

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

for ($i = 1; $i -le $Iterations; $i++) {
    $ts = Get-Date
    $stamp = $ts.ToString("yyyyMMdd_HHmmss")
    $result = powershell -NoProfile -ExecutionPolicy Bypass -File $verifyScript | ConvertFrom-Json

    $snapshotApiMatch = [bool]$result.snapshot_api_match
    $apiDashboardMatch = [bool]$result.api_dashboard_match
    $kpiKeysPresent = [bool]$result.api_has_all_kpi
    $typeConsistency = [bool]$result.type_consistency
    $driftDetected = (-not $snapshotApiMatch) -or (-not $apiDashboardMatch) -or (-not $kpiKeysPresent) -or (-not $typeConsistency)

    $report = @(
        "[FACT]",
        "TIMESTAMP = $($ts.ToString('o'))",
        "SNAPSHOT_API_MATCH = " + ($(if ($snapshotApiMatch) { "YES" } else { "NO" })),
        "API_DASHBOARD_MATCH = " + ($(if ($apiDashboardMatch) { "YES" } else { "NO" })),
        "KPI_KEYS_PRESENT = " + ($(if ($kpiKeysPresent) { "YES" } else { "NO" })),
        "TYPE_CONSISTENCY = " + ($(if ($typeConsistency) { "YES" } else { "NO" })),
        "DRIFT_DETECTED = " + ($(if ($driftDetected) { "YES" } else { "NO" })),
        "SNAPSHOT_TOTAL_TRADES = $($result.snapshot_values.total_trades)",
        "SNAPSHOT_REALIZED_PNL = $($result.snapshot_values.realized_pnl)",
        "SNAPSHOT_WIN_RATE = $($result.snapshot_values.win_rate)",
        "SNAPSHOT_DRAWDOWN = $($result.snapshot_values.drawdown)",
        "API_KPI_TOTAL_TRADES = $($result.api_values.kpi_total_trades)",
        "API_KPI_REALIZED_PNL = $($result.api_values.kpi_realized_pnl)",
        "API_KPI_WIN_RATE = $($result.api_values.kpi_win_rate)",
        "API_KPI_DRAWDOWN = $($result.api_values.kpi_drawdown)",
        "",
        "[INFERENCE]",
        "DRIFT_PATTERN = " + ($(if ($driftDetected) { "DETECTED" } else { "NONE" })),
        "",
        "[ASSUMPTION]",
        "NONE",
        "",
        "[UNKNOWN]",
        "NONE"
    )

    $outFile = Join-Path $OutputDir ("KPI_DRIFT_MONITOR_{0}.txt" -f $stamp)
    Set-Content -Path $outFile -Value $report -Encoding UTF8

    if ($i -lt $Iterations) {
        Start-Sleep -Seconds ($IntervalMinutes * 60)
    }
}

