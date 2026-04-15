param(
    [int]$PollSec = 15,
    [int]$TimeoutMinutes = 240
)

$ErrorActionPreference = "Stop"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

function Read-KeyValueFile {
    param([string]$Path)
    $map = @{}
    if (-not (Test-Path -LiteralPath $Path)) {
        return $map
    }
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        $idx = $line.IndexOf("=")
        if ($idx -lt 0) {
            continue
        }
        $key = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim()
        if (-not [string]::IsNullOrWhiteSpace($key)) {
            $map[$key] = $value
        }
    }
    return $map
}

$reportDir = Resolve-NtRoleReportDir -RoleFolder "honey_execution_reports" -EnsureExists
$collectionStatusPath = Join-Path $reportDir "runtime_12h_collection_status.txt"
$watchLogPath = Join-Path $reportDir "runtime_12h_final_audit_watch.log"
$auditScript = "C:\nt_v1\BOOT\write_12h_runtime_final_audit.ps1"

$startedAt = Get-Date
Add-Content -LiteralPath $watchLogPath -Encoding UTF8 -Value ("{0} WATCH_START poll_sec={1} timeout_min={2}" -f (Get-Date).ToString("o"), $PollSec, $TimeoutMinutes)

while ($true) {
    if ((Get-Date) -gt $startedAt.AddMinutes($TimeoutMinutes)) {
        Add-Content -LiteralPath $watchLogPath -Encoding UTF8 -Value ("{0} WATCH_TIMEOUT" -f (Get-Date).ToString("o"))
        throw "Timed out waiting for runtime 12h collection completion."
    }

    $status = Read-KeyValueFile -Path $collectionStatusPath
    $collectionState = [string]$status["COLLECTION_STATUS"]
    if ($collectionState -eq "COMPLETED") {
        Add-Content -LiteralPath $watchLogPath -Encoding UTF8 -Value ("{0} COLLECTION_COMPLETED" -f (Get-Date).ToString("o"))
        Start-Sleep -Seconds 5
        & $auditScript | Tee-Object -FilePath $watchLogPath -Append | Out-Null
        Add-Content -LiteralPath $watchLogPath -Encoding UTF8 -Value ("{0} AUDIT_DONE" -f (Get-Date).ToString("o"))
        break
    }

    Add-Content -LiteralPath $watchLogPath -Encoding UTF8 -Value ("{0} WAITING status={1}" -f (Get-Date).ToString("o"), $collectionState)
    Start-Sleep -Seconds $PollSec
}

