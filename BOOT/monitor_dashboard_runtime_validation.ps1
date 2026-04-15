param(
    [int]$IntervalSec = 30,
    [int]$ObserveMinutes = 10080,
    [int]$ApiTimeoutSec = 20,
    [int]$SlowRuntimeThresholdMs = 2000
)

$ErrorActionPreference = 'Continue'
. 'C:\nt_v1\BOOT\report_path_resolver.ps1'

$latestPath = Resolve-NtRoleReportFile -RoleFolder 'honey_execution_reports' -FileName 'dashboard_runtime_validation_latest.json' -EnsureParent
$historyPath = Resolve-NtRoleReportFile -RoleFolder 'honey_execution_reports' -FileName 'dashboard_runtime_validation_history.jsonl' -EnsureParent
$logPath = Resolve-NtRoleReportFile -RoleFolder 'honey_execution_reports' -FileName 'dashboard_runtime_validation_log.txt' -EnsureParent
$endAt = (Get-Date).AddMinutes($ObserveMinutes)

function Log([string]$line) {
    Add-Content -Path $logPath -Value ("{0} {1}" -f (Get-Date).ToString('s'), $line)
}

function Measure-HttpJson([string]$Uri, [int]$TimeoutSec) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $resp = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec $TimeoutSec
        $sw.Stop()
        $json = $null
        try {
            $json = $resp.Content | ConvertFrom-Json
        } catch {
            $json = $null
        }
        return [pscustomobject]@{
            ok = $true
            status_code = [int]$resp.StatusCode
            elapsed_ms = [int]$sw.ElapsedMilliseconds
            content_length = [int]$resp.Content.Length
            json = $json
            error = '-'
        }
    } catch {
        $sw.Stop()
        return [pscustomobject]@{
            ok = $false
            status_code = -1
            elapsed_ms = [int]$sw.ElapsedMilliseconds
            content_length = 0
            json = $null
            error = $_.Exception.Message
        }
    }
}

Log ("DASHBOARD_RUNTIME_VALIDATION_START interval_sec={0} observe_minutes={1} slow_threshold_ms={2}" -f $IntervalSec, $ObserveMinutes, $SlowRuntimeThresholdMs)

while ((Get-Date) -lt $endAt) {
    $rootCheck = Measure-HttpJson -Uri 'http://127.0.0.1:8788/' -TimeoutSec $ApiTimeoutSec
    $runtimeCheck = Measure-HttpJson -Uri 'http://127.0.0.1:8788/api/runtime' -TimeoutSec $ApiTimeoutSec

    $runtimeJson = $runtimeCheck.json
    $listenerCount = -1
    $processCount = -1
    $singleListenerHealth = $false
    $runtimeAlive = $false
    $exchangeApiOk = $false
    $currentOperationStatus = '-'
    $entryWindow = -1
    $entryBuy = -1
    $entrySell = -1

    if ($runtimeJson) {
        try { $listenerCount = [int]$runtimeJson.dashboard_listener_count } catch {}
        try { $processCount = [int]$runtimeJson.dashboard_process_count } catch {}
        try { $singleListenerHealth = [bool]$runtimeJson.dashboard_single_listener_health } catch {}
        try { $runtimeAlive = [bool]$runtimeJson.runtime_alive } catch {}
        try { $exchangeApiOk = [bool]$runtimeJson.exchange_api_ok } catch {}
        try { $currentOperationStatus = [string]$runtimeJson.current_operation_status } catch {}
        try { $entryWindow = [int]$runtimeJson.recent_entry_window } catch {}
        try { $entryBuy = [int]$runtimeJson.recent_entry_buy_count } catch {}
        try { $entrySell = [int]$runtimeJson.recent_entry_sell_count } catch {}
    }

    $record = [ordered]@{
        ts = (Get-Date).ToString('o')
        root_ok = [bool]$rootCheck.ok
        root_status_code = [int]$rootCheck.status_code
        root_elapsed_ms = [int]$rootCheck.elapsed_ms
        runtime_ok = [bool]$runtimeCheck.ok
        runtime_status_code = [int]$runtimeCheck.status_code
        runtime_elapsed_ms = [int]$runtimeCheck.elapsed_ms
        runtime_slow = ([bool]($runtimeCheck.ok -and $runtimeCheck.elapsed_ms -ge $SlowRuntimeThresholdMs))
        runtime_error = [string]$runtimeCheck.error
        dashboard_listener_count = $listenerCount
        dashboard_process_count = $processCount
        dashboard_single_listener_health = [bool]$singleListenerHealth
        runtime_alive = [bool]$runtimeAlive
        exchange_api_ok = [bool]$exchangeApiOk
        current_operation_status = [string]$currentOperationStatus
        recent_entry_window = $entryWindow
        recent_entry_buy_count = $entryBuy
        recent_entry_sell_count = $entrySell
    }

    $json = $record | ConvertTo-Json -Depth 6
    Set-Content -Path $latestPath -Value $json -Encoding UTF8
    Add-Content -Path $historyPath -Value $json

    if (-not $rootCheck.ok -or -not $runtimeCheck.ok) {
        Log ("DASHBOARD_VALIDATION_FAIL root_ok={0} runtime_ok={1} runtime_error={2}" -f $rootCheck.ok, $runtimeCheck.ok, $runtimeCheck.error)
    } elseif ($runtimeCheck.elapsed_ms -ge $SlowRuntimeThresholdMs) {
        Log ("DASHBOARD_VALIDATION_SLOW runtime_elapsed_ms={0} listener_count={1} process_count={2}" -f $runtimeCheck.elapsed_ms, $listenerCount, $processCount)
    } else {
        Log ("DASHBOARD_VALIDATION_OK runtime_elapsed_ms={0} listener_count={1} process_count={2}" -f $runtimeCheck.elapsed_ms, $listenerCount, $processCount)
    }

    Start-Sleep -Seconds $IntervalSec
}

Log 'DASHBOARD_RUNTIME_VALIDATION_END'

