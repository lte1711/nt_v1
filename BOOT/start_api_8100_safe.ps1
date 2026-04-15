$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $projectRoot "BOOT\common_process_helpers.ps1")
$cmdPath = Join-Path $projectRoot "tools\ops\run_api_8100.cmd"

function Get-ApiProcesses {
    @(Get-PythonProcessesByCommandPatterns -Patterns @("*next_trade.api.app:app*", "*uvicorn*--port 8100*"))
}

function Get-ApiListenerPids {
    @(Get-ListenerPidsByPort -Port 8100)
}

function Stop-ApiProcesses([array]$processes, [int[]]$keepPids = @()) {
    foreach ($proc in @($processes)) {
        if ($keepPids -contains [int]$proc.ProcessId) {
            continue
        }
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Output "API_8100_DUPLICATE_STOPPED_PID=$($proc.ProcessId)"
        } catch {
            Write-Output "API_8100_DUPLICATE_STOP_FAILED_PID=$($proc.ProcessId)"
        }
    }
    Start-Sleep -Seconds 1
}

$apiProcesses = @(Get-ApiProcesses)
$listenerPids = @(Get-ApiListenerPids)
$apiProcessPids = @($apiProcesses | Select-Object -ExpandProperty ProcessId)
$healthyApiPids = @($listenerPids | Where-Object { $_ -in $apiProcessPids })

if ($apiProcesses.Count -gt 1) {
    $preferred = $null
    if ($healthyApiPids.Count -ge 1) {
        $preferred = $apiProcesses | Where-Object { $_.ProcessId -eq $healthyApiPids[0] } | Select-Object -First 1
    }
    if (-not $preferred) {
        $preferred = $apiProcesses | Sort-Object CreationDate -Descending | Select-Object -First 1
    }
    Write-Output "API_8100_DUPLICATES_DETECTED=$($apiProcesses.Count)"
    Stop-ApiProcesses -processes $apiProcesses -keepPids @([int]$preferred.ProcessId)
    $apiProcesses = @(Get-ApiProcesses)
    $listenerPids = @(Get-ApiListenerPids)
    $apiProcessPids = @($apiProcesses | Select-Object -ExpandProperty ProcessId)
    $healthyApiPids = @($listenerPids | Where-Object { $_ -in $apiProcessPids })
}

if ($listenerPids.Count -gt 0) {
    if ($healthyApiPids.Count -ge 1) {
        Write-Output "API_8100_ALREADY_RUNNING=YES"
        Write-Output "API_8100_PID_LIST=$((@($healthyApiPids) -join ','))"
        exit 0
    }

    Write-Output "API_8100_PORT_CONFLICT=YES"
    Write-Output "API_8100_PORT_OWNER_PID_LIST=$((@($listenerPids) -join ','))"
    exit 1
}

if ($apiProcesses.Count -gt 0) {
    Write-Output "API_8100_STALE_PROCESS_DETECTED=$($apiProcesses.Count)"
    Stop-ApiProcesses -processes $apiProcesses
}

if (-not (Test-Path $cmdPath)) {
    Write-Output "API_8100_CMD_MISSING=YES"
    exit 1
}

cmd.exe /c $cmdPath | Out-Null
Start-Sleep -Seconds 2

$apiProcesses = @(Get-ApiProcesses)
$listenerPids = @(Get-ApiListenerPids)
$apiProcessPids = @($apiProcesses | Select-Object -ExpandProperty ProcessId)
$healthyApiPids = @($listenerPids | Where-Object { $_ -in $apiProcessPids })

if ($listenerPids.Count -gt 0 -and $healthyApiPids.Count -ge 1) {
    Write-Output "API_8100_START=YES"
    Write-Output "API_8100_PID_LIST=$((@($healthyApiPids) -join ','))"
    exit 0
}

if ($listenerPids.Count -gt 0 -and $healthyApiPids.Count -eq 0) {
    Write-Output "API_8100_PORT_CONFLICT=YES"
    Write-Output "API_8100_PORT_OWNER_PID_LIST=$((@($listenerPids) -join ','))"
    exit 1
}

Write-Output "API_8100_START=NO"
exit 1
