param(
    [string]$RootPath = "C:\nt_v1\reports",
    [string]$DateString = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($DateString)) {
    $DateString = Get-Date -Format "yyyy-MM-dd"
}

$dailyPath = Join-Path $RootPath $DateString
$teamFolders = @(
    "honey_execution_reports",
    "candy_validation_reports",
    "gemini_technical_reports",
    "sugar_audit_reports",
    "baekseol_design_reports"
)

if (-not (Test-Path -LiteralPath $RootPath)) {
    New-Item -ItemType Directory -Path $RootPath -Force | Out-Null
}

if (-not (Test-Path -LiteralPath $dailyPath)) {
    New-Item -ItemType Directory -Path $dailyPath -Force | Out-Null
}

$createdFolders = @()
foreach ($folder in $teamFolders) {
    $folderPath = Join-Path $dailyPath $folder
    if (-not (Test-Path -LiteralPath $folderPath)) {
        New-Item -ItemType Directory -Path $folderPath -Force | Out-Null
        $createdFolders += $folderPath
    }
}

$result = [ordered]@{
    root_path = $RootPath
    date = $DateString
    daily_path = $dailyPath
    team_folders = $teamFolders
    created_folders = $createdFolders
    ready = $true
}

$result | ConvertTo-Json -Depth 3


