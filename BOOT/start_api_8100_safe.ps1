$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$apiScriptPath = Join-Path $projectRoot "tools\ops\run_api_8100.py"

function Resolve-ApiPythonExe {
    $venvCfg = Join-Path $projectRoot ".venv\pyvenv.cfg"
    if (Test-Path $venvCfg) {
        $homeLine = Get-Content $venvCfg | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
        if ($homeLine) {
            $homeValue = ($homeLine -split "=", 2)[1].Trim()
            $candidate = Join-Path $homeValue "python.exe"
            if (Test-Path $candidate) {
                return $candidate
            }
        }
    }

    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    throw "API python executable could not be resolved"
}

function Get-ApiProcesses {
    @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and (
            $_.CommandLine -match "run_api_8100\.py" -or
            $_.CommandLine -match "next_trade\.api\.app:app" -or
            $_.CommandLine -match "uvicorn.*8100"
        )
    })
}

function Get-PortOwners([int]$Port) {
    @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique)
}

function Test-ApiHealthy([int]$TimeoutSec = 4) {
    foreach ($url in @(
        "http://127.0.0.1:8100/api/status",
        "http://127.0.0.1:8100/openapi.json"
    )) {
        try {
            $status = & curl.exe -s -o NUL -w "%{http_code}" --max-time $TimeoutSec $url
            if ($LASTEXITCODE -eq 0 -and "$status".Trim() -eq "200") {
                return $true
            }
        } catch {
        }
    }
    return $false
}

function Stop-ApiProcesses([array]$Processes) {
    foreach ($proc in @($Processes | Sort-Object ProcessId -Descending)) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Output "API_8100_STOPPED_PID=$($proc.ProcessId)"
        } catch {
            Write-Output "API_8100_STOP_FAILED_PID=$($proc.ProcessId)"
        }
    }
    Start-Sleep -Seconds 2
}

function Wait-ForApiHealthy([int]$TimeoutSec = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        if (Test-ApiHealthy -TimeoutSec 4) {
            return $true
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    return $false
}

if (-not (Test-Path $apiScriptPath)) {
    Write-Output "API_8100_SCRIPT_MISSING=YES"
    exit 1
}

$apiProcesses = @(Get-ApiProcesses)
$listenerPids = @(Get-PortOwners -Port 8100)
$apiPids = @($apiProcesses | Select-Object -ExpandProperty ProcessId)
$apiListenerPids = @($listenerPids | Where-Object { $_ -in $apiPids })

if ($apiListenerPids.Count -ge 1 -and (Test-ApiHealthy)) {
    Write-Output "API_8100_ALREADY_RUNNING=YES"
    Write-Output "API_8100_PID_LIST=$((@($apiListenerPids) -join ','))"
    exit 0
}

if ($apiProcesses.Count -gt 0) {
    Write-Output "API_8100_RESTARTING=YES"
    Stop-ApiProcesses -Processes $apiProcesses
    $listenerPids = @(Get-PortOwners -Port 8100)
}

if ($listenerPids.Count -gt 0) {
    Write-Output "API_8100_PORT_CONFLICT=YES"
    Write-Output "API_8100_PORT_OWNER_PID_LIST=$((@($listenerPids) -join ','))"
    exit 1
}

$pythonExe = Resolve-ApiPythonExe
Start-Process -FilePath $pythonExe -ArgumentList $apiScriptPath -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null

if (-not (Wait-ForApiHealthy -TimeoutSec 30)) {
    Write-Output "API_8100_START=NO"
    exit 1
}

$apiProcesses = @(Get-ApiProcesses)
$apiPids = @($apiProcesses | Select-Object -ExpandProperty ProcessId)
$listenerPids = @(Get-PortOwners -Port 8100)
$apiListenerPids = @($listenerPids | Where-Object { $_ -in $apiPids })

if ($apiListenerPids.Count -ge 1) {
    Write-Output "API_8100_START=YES"
    Write-Output "API_8100_PID_LIST=$((@($apiListenerPids) -join ','))"
    exit 0
}

Write-Output "API_8100_START=NO"
exit 1
