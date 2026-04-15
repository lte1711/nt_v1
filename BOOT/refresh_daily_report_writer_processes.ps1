param(
    [switch]$Execute
)

$ErrorActionPreference = "Stop"

$targets = @(
    @{
        name = "observe_multi5_realtime.ps1"
        match = "*observe_multi5_realtime.ps1*"
        restart = { & "C:\nt_v1\BOOT\start_realtime_observe.ps1" | Out-Null }
    },
    @{
        name = "collect_runtime_8h.ps1"
        match = "*collect_runtime_8h.ps1*"
        restart = { & "C:\nt_v1\BOOT\start_8h_collection.ps1" | Out-Null }
    },
    @{
        name = "phase5_portfolio_milestone_reporter.ps1"
        match = "*phase5_portfolio_milestone_reporter.ps1*"
        restart = {
            Start-Process -FilePath "powershell.exe" -ArgumentList @(
                "-NoProfile","-ExecutionPolicy","Bypass","-File","C:\nt_v1\BOOT\phase5_portfolio_milestone_reporter.ps1",
                "-IntervalSec","60","-DurationMinutes","1440"
            ) -WindowStyle Hidden | Out-Null
        }
    },
    @{
        name = "first_order_milestone_reporter.ps1"
        match = "*first_order_milestone_reporter.ps1*"
        restart = {
            Start-Process -FilePath "powershell.exe" -ArgumentList @(
                "-NoProfile","-ExecutionPolicy","Bypass","-File","C:\nt_v1\BOOT\first_order_milestone_reporter.ps1",
                "-IntervalSec","60","-DurationMinutes","360"
            ) -WindowStyle Hidden | Out-Null
        }
    }
)

$results = New-Object System.Collections.Generic.List[object]

foreach ($target in $targets) {
    $procs = @(Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -eq "powershell.exe" -or $_.Name -eq "pwsh.exe") -and
        [string]$_.CommandLine -like $target.match -and
        [string]$_.CommandLine -notlike "* -Command *"
    })

    $stopped = 0
    $restarted = $false

    if ($Execute -and $procs.Count -gt 0) {
        foreach ($proc in $procs) {
            try {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                $stopped += 1
            } catch {}
        }
        Start-Sleep -Seconds 1
        & $target.restart
        $restarted = $true
    }

    $results.Add([pscustomobject]@{
        script = $target.name
        detected_count = $procs.Count
        detected_pids = (($procs | Select-Object -ExpandProperty ProcessId) -join ",")
        execute_mode = [bool]$Execute
        stopped_count = $stopped
        restarted = $restarted
    }) | Out-Null
}

$results | ConvertTo-Json -Depth 3

