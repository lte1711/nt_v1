#Requires -Version 5.1
# NEXT-TRADE Engine Launcher vFINAL
# Boot chain launcher with duplicate-root cleanup and fact-based startup checks.
$ErrorActionPreference = "Stop"

# PATH CONFIG
$bootRoot     = $PSScriptRoot
$projectRoot  = Split-Path -Parent $bootRoot
. (Join-Path $bootRoot "common_process_helpers.ps1")
$pythonExe    = Join-Path $projectRoot ".venv\Scripts\python.exe"
$engineScript = Join-Path $projectRoot "tools\multi5\run_multi5_engine.py"

# RUNTIME CONFIG
$runtimeMinutes       = 480
$scanIntervalSec      = 5
$engineSessionHours   = 2.0
$maxOpenPositions     = 5
$maxSymbolActive      = 5
$maxPositionPerSymbol = 1
$launchCooldownSec    = 120

function Get-EngineProcesses {
    try {
        $processes = @(Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq "python.exe" -and
            $_.CommandLine -ne $null -and
            $_.CommandLine -match "run_multi5_engine\.py"
        })
        return @(Get-RootProcessesFromSet -Processes $processes)
    } catch {
        Write-Warning "PROCESS_DETECTION_ERROR: $_"
        return @()
    }
}

function Stop-DuplicateEngineRoots([array]$processes) {
    $items = @($processes)
    if ($items.Count -le 1) {
        return @($items)
    }

    $ordered = @($items | Sort-Object CreationDate -Descending)
    $keep = $ordered | Select-Object -First 1
    $drop = @($ordered | Select-Object -Skip 1)

    foreach ($proc in $drop) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host "ENGINE_DUPLICATE_ROOT_STOPPED_PID=$($proc.ProcessId)"
        } catch {
            Write-Warning "ENGINE_DUPLICATE_ROOT_STOP_FAILED_PID=$($proc.ProcessId)"
        }
    }

    Start-Sleep -Seconds 1
    return @(Get-EngineProcesses)
}

function Ensure-Guards {
    try {
        $guard = Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -like "*runtime_guard.ps1*"
        }
        if (-not $guard) {
            & (Join-Path $bootRoot "start_runtime_guard.ps1")
            Write-Output "RUNTIME_GUARD_STARTED"
        }
    } catch {
        Write-Warning "RUNTIME_GUARD_FAILED: $_"
    }

    try {
        $autoGuard = Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -like "*phase5_autoguard.ps1*"
        }
        if (-not $autoGuard) {
            & (Join-Path $bootRoot "start_phase5_autoguard.ps1")
            Write-Output "AUTOGUARD_STARTED"
        }
    } catch {
        Write-Warning "AUTOGUARD_FAILED: $_"
    }

    try {
        $workerGuard = Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -like "*worker_watchdog.ps1*"
        }
        if (-not $workerGuard) {
            & (Join-Path $bootRoot "start_worker_watchdog.ps1")
            Write-Output "WORKER_WATCHDOG_STARTED"
        }
    } catch {
        Write-Warning "WORKER_WATCHDOG_FAILED: $_"
    }
}

$mutexName = "Global\NextTrade_Engine_Start"
$mutex     = New-Object System.Threading.Mutex($false, $mutexName)
$hasLock   = $false

try {
    $hasLock = $mutex.WaitOne(5000)

    if (-not $hasLock) {
        Write-Output "ENGINE_START_SKIPPED=LOCK_TIMEOUT"
        exit 0
    }

    # STEP 1: Verify the Python executable exists.
    if (-not (Test-Path $pythonExe)) {
        Write-Output "PYTHON_NOT_FOUND"
        Write-Output "PYTHON_PATH=$pythonExe"
        exit 1
    }

    # STEP 2: Prevent duplicate engine execution.
    $existing = Get-EngineProcesses

    if ($existing.Count -gt 1) {
        Write-Output "ENGINE_DUPLICATE_ROOTS_DETECTED=$($existing.Count)"
        $existing = Stop-DuplicateEngineRoots -processes $existing
    }

    if ($existing.Count -gt 0) {
        Ensure-Guards
        $pids = ($existing | Select-Object -ExpandProperty ProcessId) -join ","
        Write-Output "ENGINE_ALREADY_RUNNING=YES"
        Write-Output "ENGINE_PID_LIST=$pids"
        exit 0
    }

    # STEP 3: Prepare timestamped engine log file paths.
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $logDir    = Join-Path $projectRoot "logs"

    try {
        if (-not (Test-Path $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
    } catch {
        Write-Output "LOG_DIR_CREATE_FAILED=$logDir"
        Write-Warning $_
        exit 1
    }

    $stdoutLog = Join-Path $logDir "engine_stdout_$timestamp.log"
    $stderrLog = Join-Path $logDir "engine_error_$timestamp.log"

    # STEP 4: Build the engine argument list.
    $argList = @(
        $engineScript,
        "--runtime-minutes",         "$runtimeMinutes",
        "--scan-interval-sec",       "$scanIntervalSec",
        "--engine-session-hours",    "$engineSessionHours",
        "--max-open-positions",      "$maxOpenPositions",
        "--max-symbol-active",       "$maxSymbolActive",
        "--max-position-per-symbol", "$maxPositionPerSymbol",
        "--launch-cooldown-sec",     "$launchCooldownSec"
    )

    # STEP 5: Launch the engine process.
    $proc = $null
    try {
        $proc = Start-Process `
            -FilePath $pythonExe `
            -ArgumentList $argList `
            -WorkingDirectory $projectRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdoutLog `
            -RedirectStandardError  $stderrLog `
            -PassThru
    } catch {
        Write-Output "PROCESS_START_EXCEPTION=$_"
        exit 1
    }

    if ($null -eq $proc) {
        Write-Output "PROCESS_START_FAILED"
        exit 1
    }

    Write-Output "PROCESS_LAUNCHED_PID=$($proc.Id)"

    # STEP 6: Verify the engine actually started.
    $retry    = 0
    $maxRetry = 6
    $running  = @()

    do {
        Start-Sleep -Seconds 3
        $running = Get-EngineProcesses
        $retry++
        Write-Output "ENGINE_CHECK_ATTEMPT=$retry"
    } while ($running.Count -eq 0 -and $retry -lt $maxRetry)

    # STEP 7: Handle successful startup.
    if ($running.Count -gt 0) {
        Ensure-Guards
        $pidList = ($running | Select-Object -ExpandProperty ProcessId) -join ","
        Write-Output "ENGINE_START=YES"
        Write-Output "ENGINE_PID_LIST=$pidList"
        Write-Output "STDOUT_LOG=$stdoutLog"
        Write-Output "STDERR_LOG=$stderrLog"
        exit 0
    }

    # STEP 8: Handle startup failure and dump logs.
    Write-Output "ENGINE_START=NO"
    Write-Output "CHECK_ATTEMPTS=$retry"

    if (Test-Path $stdoutLog) {
        Write-Output "==== STDOUT ===="
        Get-Content $stdoutLog
    }

    if (Test-Path $stderrLog) {
        Write-Output "==== STDERR ===="
        Get-Content $stderrLog
    }

    exit 1
}
finally {
    if ($hasLock) {
        try { $mutex.ReleaseMutex() | Out-Null } catch {}
    }
    $mutex.Dispose()
}

