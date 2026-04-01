param()

$ErrorActionPreference = 'Stop'
$root = 'C:\next-trade-ver1.0\reports'
$datedRoot = Join-Path $root '2026-03-15'
$manifestCsv = Join-Path $datedRoot 'honey_execution_reports\LEGACY_ROLE_REPORT_MIGRATION_MANIFEST_2026-03-15.csv'

$legacyHoney = Join-Path $root 'honey_execution_reports'
$legacyCandy = Join-Path $root 'candy_validation_reports'
$holdHoney = Join-Path $root 'honey_execution_reports_legacy_verified_hold'
$holdCandy = Join-Path $root 'candy_validation_reports_legacy_verified_hold'
$datedHoney = Join-Path $datedRoot 'honey_execution_reports'
$datedCandy = Join-Path $datedRoot 'candy_validation_reports'

$rows = @()
$manifestRows = @()
if (Test-Path $manifestCsv) {
    $manifestRows = @(Import-Csv $manifestCsv)
}

$missingTargets = 0
foreach ($row in $manifestRows) {
    $targetPath = $row.target_path
    $targetExists = Test-Path $targetPath
    if (-not $targetExists) { $missingTargets++ }
    $rows += [pscustomobject]@{
        source_path = $row.source_path
        target_path = $targetPath
        target_exists = $targetExists
        role_folder = $row.role_folder
        date_basis = $row.date_basis
    }
}

$dashboardApi = 'ERROR'
try {
    $resp = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8788/api/runtime' -TimeoutSec 10
    $dashboardApi = [string][int]$resp.StatusCode
} catch {
    $dashboardApi = 'ERROR:' + $_.Exception.Message
}

$summary = [pscustomobject]@{
    legacy_honey_present = Test-Path $legacyHoney
    legacy_candy_present = Test-Path $legacyCandy
    hold_honey_present = Test-Path $holdHoney
    hold_candy_present = Test-Path $holdCandy
    dated_honey_present = Test-Path $datedHoney
    dated_candy_present = Test-Path $datedCandy
    manifest_present = Test-Path $manifestCsv
    manifest_rows = $manifestRows.Count
    missing_targets = $missingTargets
    dashboard_api_status = $dashboardApi
    post_hold_state_ok = ((-not (Test-Path $legacyHoney)) -and (-not (Test-Path $legacyCandy)) -and (Test-Path $holdHoney) -and (Test-Path $holdCandy) -and (Test-Path $datedHoney) -and (Test-Path $datedCandy) -and ($missingTargets -eq 0))
}

$detailPathCsv = Join-Path $datedHoney 'POST_HOLD_VALIDATION_DETAIL.csv'
$detailPathJson = Join-Path $datedHoney 'POST_HOLD_VALIDATION_DETAIL.json'
$summaryPath = Join-Path $datedHoney 'POST_HOLD_VALIDATION_SUMMARY.txt'

$rows | Export-Csv -Path $detailPathCsv -NoTypeInformation -Encoding UTF8
$rows | ConvertTo-Json -Depth 4 | Set-Content -Path $detailPathJson -Encoding UTF8
($summary | ConvertTo-Json -Depth 4) | Set-Content -Path $summaryPath -Encoding UTF8
$summary | ConvertTo-Json -Depth 4

