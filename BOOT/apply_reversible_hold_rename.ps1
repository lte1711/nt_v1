param(
    [string]$RootPath = "C:\nt_v1\reports",
    [string[]]$LegacyRoleFolders = @("honey_execution_reports", "candy_validation_reports"),
    [switch]$Execute
)

$ErrorActionPreference = "Stop"

function Get-HoldPath {
    param([string]$FolderPath)
    return ($FolderPath.TrimEnd('\') + "_legacy_verified_hold")
}

$results = New-Object System.Collections.Generic.List[object]

foreach ($folder in $LegacyRoleFolders) {
    $sourcePath = Join-Path $RootPath $folder
    $holdPath = Get-HoldPath -FolderPath $sourcePath
    $exists = Test-Path -LiteralPath $sourcePath
    $holdExists = Test-Path -LiteralPath $holdPath
    $renamed = $false

    if ($Execute -and $exists -and -not $holdExists) {
        Rename-Item -LiteralPath $sourcePath -NewName ([System.IO.Path]::GetFileName($holdPath))
        $renamed = $true
    }

    $results.Add([pscustomobject]@{
        source_path = $sourcePath
        hold_path = $holdPath
        source_exists = $exists
        hold_exists = $holdExists
        execute_mode = [bool]$Execute
        renamed = $renamed
    }) | Out-Null
}

$results | ConvertTo-Json -Depth 3


