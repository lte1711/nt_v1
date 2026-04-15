$script:NtProjectRoot = Split-Path -Parent $PSScriptRoot
$script:NtReportRoot = Join-Path $script:NtProjectRoot "reports"

function Get-NtTodayReportDateString {
    return (Get-Date).ToString("yyyy-MM-dd")
}

function Resolve-NtRoleReportDir {
    param(
        [Parameter(Mandatory = $true)][string]$RoleFolder,
        [switch]$EnsureExists,
        [switch]$LegacyFallback
    )

    $dailyDir = Join-Path (Join-Path $script:NtReportRoot (Get-NtTodayReportDateString)) $RoleFolder
    $legacyDir = Join-Path $script:NtReportRoot $RoleFolder

    if ($EnsureExists) {
        New-Item -ItemType Directory -Force -Path $dailyDir | Out-Null
        return $dailyDir
    }

    if (Test-Path -LiteralPath $dailyDir) {
        return $dailyDir
    }
    if ($LegacyFallback -and (Test-Path -LiteralPath $legacyDir)) {
        return $legacyDir
    }
    return $dailyDir
}

function Resolve-NtRoleReportFile {
    param(
        [Parameter(Mandatory = $true)][string]$RoleFolder,
        [Parameter(Mandatory = $true)][string]$FileName,
        [switch]$EnsureParent,
        [switch]$LegacyFallback
    )

    $dir = Resolve-NtRoleReportDir -RoleFolder $RoleFolder -EnsureExists:$EnsureParent -LegacyFallback:$LegacyFallback
    if ($EnsureParent -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    return (Join-Path $dir $FileName)
}
