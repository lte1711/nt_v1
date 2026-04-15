$ErrorActionPreference = "Stop"

$guardScript = "C:\nt_v1\BOOT\runtime_guard.ps1"
$intervalSec = 30
$observeMinutes = 480

$mutexName = "Global\NextTrade_RuntimeGuard_Start"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$hasLock = $false

try {
    $hasLock = $mutex.WaitOne(5000)
    if (-not $hasLock) {
        Write-Output "RUNTIME_GUARD_START_SKIPPED=LOCK_TIMEOUT"
        exit 0
    }

    $existing = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "powershell.exe" -and
        $_.CommandLine -like "*runtime_guard.ps1*" -and
        $_.CommandLine -notlike "* -Command *"
    }
    if ($existing) {
        Write-Output "RUNTIME_GUARD_ALREADY_RUNNING=YES"
        Write-Output "RUNTIME_GUARD_PID_LIST=$((($existing | Select-Object -ExpandProperty ProcessId) -join ','))"
        exit 0
    }

    $argList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$guardScript`"",
        "-IntervalSec", "$intervalSec",
        "-ObserveMinutes", "$observeMinutes"
    )

    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $argList -WindowStyle Hidden -PassThru
    Start-Sleep -Seconds 1

    Write-Output "RUNTIME_GUARD_START=YES"
    Write-Output "RUNTIME_GUARD_PID=$($proc.Id)"
    Write-Output "RUNTIME_GUARD_INTERVAL_SEC=$intervalSec"
    Write-Output "RUNTIME_GUARD_OBSERVE_MINUTES=$observeMinutes"
}
finally {
    if ($hasLock) {
        try { $mutex.ReleaseMutex() | Out-Null } catch {}
    }
    $mutex.Dispose()
}

