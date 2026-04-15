param(
    [string]$RootPath = "C:\nt_v1\reports",
    [string]$RunDate = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RunDate)) {
    $RunDate = Get-Date -Format "yyyy-MM-dd"
}

$legacyRoleFolders = @(
    "honey_execution_reports",
    "candy_validation_reports",
    "gemini_technical_reports",
    "sugar_audit_reports",
    "baekseol_design_reports"
)

function Resolve-ReportDate {
    param(
        [string]$FileName,
        [datetime]$LastWriteTime
    )

    $hyphenMatch = [regex]::Match($FileName, '(20\d{2}-\d{2}-\d{2})')
    if ($hyphenMatch.Success) {
        return @{
            date = $hyphenMatch.Groups[1].Value
            basis = "filename_yyyy-mm-dd"
        }
    }

    $plainMatch = [regex]::Match($FileName, '(20\d{2})(\d{2})(\d{2})')
    if ($plainMatch.Success) {
        $date = "{0}-{1}-{2}" -f $plainMatch.Groups[1].Value, $plainMatch.Groups[2].Value, $plainMatch.Groups[3].Value
        return @{
            date = $date
            basis = "filename_yyyymmdd"
        }
    }

    return @{
        date = $LastWriteTime.ToString("yyyy-MM-dd")
        basis = "lastwritetime_fallback"
    }
}

& "C:\nt_v1\BOOT\ensure_daily_report_folders.ps1" -RootPath $RootPath -DateString $RunDate | Out-Null

$runHoneyFolder = Join-Path (Join-Path $RootPath $RunDate) "honey_execution_reports"
$manifestCsv = Join-Path $runHoneyFolder "LEGACY_ROLE_REPORT_MIGRATION_MANIFEST_$($RunDate).csv"
$manifestJson = Join-Path $runHoneyFolder "LEGACY_ROLE_REPORT_MIGRATION_MANIFEST_$($RunDate).json"
$summaryTxt = Join-Path $runHoneyFolder "LEGACY_ROLE_REPORT_MIGRATION_SUMMARY_$($RunDate).txt"

$manifest = New-Object System.Collections.Generic.List[object]

foreach ($roleFolder in $legacyRoleFolders) {
    $sourceFolder = Join-Path $RootPath $roleFolder
    if (-not (Test-Path -LiteralPath $sourceFolder)) {
        continue
    }

    Get-ChildItem -Path $sourceFolder -File | ForEach-Object {
        $resolution = Resolve-ReportDate -FileName $_.Name -LastWriteTime $_.LastWriteTime
        $targetDaily = Join-Path $RootPath $resolution.date
        $targetRoleFolder = Join-Path $targetDaily $roleFolder

        if (-not (Test-Path -LiteralPath $targetDaily)) {
            New-Item -ItemType Directory -Path $targetDaily -Force | Out-Null
        }
        if (-not (Test-Path -LiteralPath $targetRoleFolder)) {
            New-Item -ItemType Directory -Path $targetRoleFolder -Force | Out-Null
        }

        $targetPath = Join-Path $targetRoleFolder $_.Name
        $copied = $false
        $alreadyPresent = $false

        if (Test-Path -LiteralPath $targetPath) {
            $alreadyPresent = $true
        } else {
            Copy-Item -LiteralPath $_.FullName -Destination $targetPath
            $copied = $true
        }

        $manifest.Add([pscustomobject]@{
            source_path = $_.FullName
            target_path = $targetPath
            role_folder = $roleFolder
            file_name = $_.Name
            date_basis = $resolution.basis
            target_date = $resolution.date
            size_bytes = $_.Length
            last_write_time = $_.LastWriteTime.ToString("s")
            move_type = "copy-first"
            copied = $copied
            already_present = $alreadyPresent
        }) | Out-Null
    }
}

$manifest | Export-Csv -Path $manifestCsv -NoTypeInformation -Encoding UTF8
$manifest | ConvertTo-Json -Depth 4 | Set-Content -Path $manifestJson -Encoding UTF8

$summaryLines = @()
$summaryLines += "RUN_DATE = $RunDate"
$summaryLines += "ROOT_PATH = $RootPath"
$summaryLines += "MANIFEST_CSV = $manifestCsv"
$summaryLines += "MANIFEST_JSON = $manifestJson"
$summaryLines += "TOTAL_ITEMS = $($manifest.Count)"
$summaryLines += "COPIED_ITEMS = $((@($manifest | Where-Object { $_.copied })).Count)"
$summaryLines += "ALREADY_PRESENT_ITEMS = $((@($manifest | Where-Object { $_.already_present })).Count)"
$summaryLines += "FILENAME_YYYYMMDD = $((@($manifest | Where-Object { $_.date_basis -eq 'filename_yyyymmdd' })).Count)"
$summaryLines += "FILENAME_YYYY-MM-DD = $((@($manifest | Where-Object { $_.date_basis -eq 'filename_yyyy-mm-dd' })).Count)"
$summaryLines += "LASTWRITETIME_FALLBACK = $((@($manifest | Where-Object { $_.date_basis -eq 'lastwritetime_fallback' })).Count)"
$summaryLines += "ROLE_FOLDERS_MIGRATED = $((@($manifest | Select-Object -ExpandProperty role_folder -Unique) -join ', '))"
$summaryLines | Set-Content -Path $summaryTxt -Encoding UTF8

[pscustomobject]@{
    run_date = $RunDate
    total_items = $manifest.Count
    copied_items = (@($manifest | Where-Object { $_.copied })).Count
    already_present_items = (@($manifest | Where-Object { $_.already_present })).Count
    manifest_csv = $manifestCsv
    manifest_json = $manifestJson
    summary_txt = $summaryTxt
} | ConvertTo-Json -Depth 3


