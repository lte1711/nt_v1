param(
    [string]$ManifestCsv = "C:\nt_v1\reports\2026-03-15\honey_execution_reports\LEGACY_ROLE_REPORT_MIGRATION_MANIFEST_2026-03-15.csv",
    [string[]]$ActivePatterns = @("*.jsonl", "*_status.txt", "*_log.txt", "nt_phase5_portfolio_observe_*.txt")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ManifestCsv)) {
    throw "Manifest not found: $ManifestCsv"
}

function Test-ActiveRuntimePattern {
    param(
        [string]$FileName,
        [string[]]$Patterns
    )

    foreach ($pattern in $Patterns) {
        if ($FileName -like $pattern) {
            return $true
        }
    }
    return $false
}

$rows = Import-Csv -Path $ManifestCsv
$results = New-Object System.Collections.Generic.List[object]

foreach ($row in $rows) {
    $sourceExists = Test-Path -LiteralPath $row.source_path
    $targetExists = Test-Path -LiteralPath $row.target_path
    $isActiveExcluded = Test-ActiveRuntimePattern -FileName $row.file_name -Patterns $ActivePatterns

    $sourceSize = $null
    $targetSize = $null
    $sizeMatch = $false

    if ($sourceExists) {
        $sourceSize = (Get-Item -LiteralPath $row.source_path).Length
    }
    if ($targetExists) {
        $targetSize = (Get-Item -LiteralPath $row.target_path).Length
    }

    if (($null -ne $sourceSize) -and ($null -ne $targetSize) -and ($sourceSize -eq $targetSize)) {
        $sizeMatch = $true
    }

    $results.Add([pscustomobject]@{
        source_path = $row.source_path
        target_path = $row.target_path
        role_folder = $row.role_folder
        file_name = $row.file_name
        source_exists = $sourceExists
        target_exists = $targetExists
        source_size = $sourceSize
        target_size = $targetSize
        size_match = $sizeMatch
        active_runtime_excluded = $isActiveExcluded
        date_basis = $row.date_basis
    }) | Out-Null
}

$manifestDir = Split-Path -Parent $ManifestCsv
$validationCsv = Join-Path $manifestDir "LEGACY_ROLE_REPORT_MIGRATION_VALIDATION_EXCLUDING_ACTIVE.csv"
$validationJson = Join-Path $manifestDir "LEGACY_ROLE_REPORT_MIGRATION_VALIDATION_EXCLUDING_ACTIVE.json"
$summaryTxt = Join-Path $manifestDir "LEGACY_ROLE_REPORT_MIGRATION_VALIDATION_EXCLUDING_ACTIVE_SUMMARY.txt"

$results | Export-Csv -Path $validationCsv -NoTypeInformation -Encoding UTF8
$results | ConvertTo-Json -Depth 4 | Set-Content -Path $validationJson -Encoding UTF8

$effectiveRows = @($results | Where-Object { -not $_.active_runtime_excluded })
$excludedRows = @($results | Where-Object { $_.active_runtime_excluded })
$missingSources = @($effectiveRows | Where-Object { -not $_.source_exists }).Count
$missingTargets = @($effectiveRows | Where-Object { -not $_.target_exists }).Count
$sizeMismatches = @($effectiveRows | Where-Object { $_.source_exists -and $_.target_exists -and -not $_.size_match }).Count
$validatedItems = @($effectiveRows | Where-Object { $_.source_exists -and $_.target_exists -and $_.size_match }).Count

$summaryLines = @()
$summaryLines += "MANIFEST_CSV = $ManifestCsv"
$summaryLines += "TOTAL_ITEMS = $($results.Count)"
$summaryLines += "EXCLUDED_ACTIVE_RUNTIME_ITEMS = $($excludedRows.Count)"
$summaryLines += "EFFECTIVE_ITEMS = $($effectiveRows.Count)"
$summaryLines += "VALIDATED_ITEMS = $validatedItems"
$summaryLines += "MISSING_SOURCES = $missingSources"
$summaryLines += "MISSING_TARGETS = $missingTargets"
$summaryLines += "SIZE_MISMATCHES = $sizeMismatches"
$summaryLines += "VALIDATION_CSV = $validationCsv"
$summaryLines += "VALIDATION_JSON = $validationJson"
$summaryLines += "READY_FOR_REVERSIBLE_CLEANUP = $(if (($missingTargets -eq 0) -and ($sizeMismatches -eq 0)) { 'YES' } else { 'NO' })"
$summaryLines += "EXCLUDED_PATTERNS = $($ActivePatterns -join ', ')"
$summaryLines | Set-Content -Path $summaryTxt -Encoding UTF8

[pscustomobject]@{
    total_items = $results.Count
    excluded_active_runtime_items = $excludedRows.Count
    effective_items = $effectiveRows.Count
    validated_items = $validatedItems
    missing_sources = $missingSources
    missing_targets = $missingTargets
    size_mismatches = $sizeMismatches
    validation_csv = $validationCsv
    validation_json = $validationJson
    summary_txt = $summaryTxt
    ready_for_reversible_cleanup = (($missingTargets -eq 0) -and ($sizeMismatches -eq 0))
} | ConvertTo-Json -Depth 3


