$ErrorActionPreference = "Continue"

$projectRoot = "C:\nt_v1"
$lockDir = Join-Path $projectRoot "logs\runtime"
$lockFiles = @(Get-ChildItem -Path $lockDir -Filter "profitmax_v1_runner_*.lock" -ErrorAction SilentlyContinue)
$removed = 0
$kept = 0

foreach ($lockFile in $lockFiles) {
    $keepFile = $false
    try {
        $raw = Get-Content $lockFile.FullName -Raw -Encoding UTF8
        $lockObj = $raw | ConvertFrom-Json
        $pid = 0
        try {
            $pid = [int]($lockObj.pid)
        } catch {
            $pid = 0
        }
        if ($pid -gt 0) {
            $proc = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $pid) -ErrorAction SilentlyContinue
            if ($null -ne $proc) {
                $keepFile = $true
            }
        }
    } catch {
        $keepFile = $false
    }

    if ($keepFile) {
        $kept += 1
        continue
    }

    try {
        Remove-Item -LiteralPath $lockFile.FullName -Force -ErrorAction Stop
        $removed += 1
    } catch {
    }
}

Write-Output ("STALE_WORKER_LOCKS_REMOVED={0}" -f $removed)
Write-Output ("ACTIVE_WORKER_LOCKS_KEPT={0}" -f $kept)

