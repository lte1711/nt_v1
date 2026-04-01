param(
    [int]$IntervalSec = 30,
    [int]$ObserveMinutes = 10080,
    [int]$WorkerStaleSec = 300,
    [int]$WarmWorkerTargetCount = 3,
    [int]$DashboardRestartCooldownSec = 90,
    [int]$HealthRestartCooldownSec = 600,
    [int]$WarnRestartThreshold = 3
)

$ErrorActionPreference = "Continue"
. "C:\next-trade-ver1.0\BOOT\report_path_resolver.ps1"
. "C:\next-trade-ver1.0\BOOT\common_process_helpers.ps1"

$projectRoot = "C:\next-trade-ver1.0"
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = Join-Path $projectRoot "venv\Scripts\python.exe"
}
$dashboardScript = Join-Path $projectRoot "tools\dashboard\multi5_dashboard_server.py"
$dashboardStartScript = "C:\next-trade-ver1.0\BOOT\start_dashboard_8787.ps1"
$dashboardValidationScript = "C:\next-trade-ver1.0\BOOT\monitor_dashboard_runtime_validation.ps1"
$runtimeHealthValidationScript = "C:\next-trade-ver1.0\BOOT\validate_runtime_health_summary.ps1"
$runtimeHealthValidationPath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "runtime_health_validation_latest.json" -EnsureParent
$restartEngineScript = "C:\next-trade-ver1.0\BOOT\restart_engine.ps1"
$healthRestartStatePath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "runtime_health_restart_state.json" -EnsureParent
$apiStartScript = Join-Path $projectRoot "BOOT\start_api_8100_safe.ps1"
$workerScript = Join-Path $projectRoot "tools\ops\profitmax_v1_runner.py"
$workerLogPath = Join-Path $projectRoot "logs\runtime\profitmax_v1_events.jsonl"
$workerSummaryPath = Join-Path $projectRoot "logs\runtime\profitmax_v1_summary.json"
$workerStrategyUnit = "momentum_intraday_v1"
$workerStrategySignalDir = Join-Path $projectRoot "logs\runtime\strategy_signals"
$workerTakeProfitPct = "0.012"
$workerStopLossPct = "0.006"
$workerMaxPositions = 1
$phase5Metrics = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "nt_phase5_multi_symbol_metrics.jsonl" -EnsureParent
$phase5Status = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "nt_phase5_multi_symbol_status.txt" -EnsureParent
$autoguardLog = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "phase5_autoguard_log.txt" -EnsureParent
$endAt = (Get-Date).AddMinutes($ObserveMinutes)

New-Item -ItemType Directory -Force -Path (Split-Path $autoguardLog -Parent) | Out-Null
$script:LastDashboardStartAt = $null
$script:LastHealthRestartAt = $null
$script:ConsecutiveHealthWarnCount = 0

$script:ImmediateRestartIssues = @(
    "HEALTH_SUMMARY_MISSING",
    "HEALTH_SUMMARY_INVALID_JSON",
    "API_8100_NOT_LISTENING",
    "DASHBOARD_8787_NOT_LISTENING",
    "ENGINE_NOT_ALIVE",
    "RUNTIME_NOT_ALIVE",
    "KILL_SWITCH_ACTIVE",
    "ENGINE_RUNTIME_LOG_STALE",
    "WORKER_EVENT_LOG_STALE",
    "RUNTIME_HEALTH_VALIDATION_EXECUTION_FAILED",
    "RUNTIME_HEALTH_VALIDATION_MISSING_REPORT"
)

$script:SoftFailIssues = @(
    "ACCOUNT_EQUITY_TOO_LOW",
    "OPS_HEALTH_NOT_OK",
    "ENGINE_ERROR_PRESENT",
    "PORTFOLIO_SNAPSHOT_STALE",
    "PORTFOLIO_SNAPSHOT_TS_INVALID",
    "HEALTH_SUMMARY_STALE"
)

$script:NoRestartIssues = @(
    "ALLOCATION_TARGET_EMPTY"
)

function Log([string]$line) {
    Add-Content -Path $autoguardLog -Value ("{0} {1}" -f (Get-Date).ToString("s"), $line)
}

function Ensure-RuntimeGuard {
    $p = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "powershell.exe" -and
        $_.CommandLine -like "*runtime_guard.ps1*" -and
        $_.CommandLine -notlike "* -Command *"
    }
    if (-not $p) {
        & "C:\next-trade-ver1.0\BOOT\start_runtime_guard.ps1" | Out-Null
        Log "START runtime_guard"
    }
}

function Ensure-Engine {
    $roots = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*run_multi5_engine.py*"
    }
    if (@($roots).Count -gt 1) {
        $ordered = @($roots | Sort-Object CreationDate -Descending)
        $keep = $ordered | Select-Object -First 1
        $dups = @($ordered | Select-Object -Skip 1)
        foreach ($dup in $dups) {
            try {
                Stop-Process -Id $dup.ProcessId -Force -ErrorAction Stop
                Log "STOP duplicate_engine_root pid=$($dup.ProcessId)"
            } catch {
                Log "STOP duplicate_engine_root_failed pid=$($dup.ProcessId)"
            }
        }
        Start-Sleep -Seconds 1
        $roots = @(Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq "python.exe" -and $_.CommandLine -like "*run_multi5_engine.py*"
        })
        Log "ENGINE_DUPLICATES_DETECTED count=$(@($ordered).Count) keep_pid=$($keep.ProcessId)"
    }
    if (-not $roots) {
        & "C:\next-trade-ver1.0\BOOT\start_engine.ps1" | Out-Null
        Log "START engine"
    }
}

function Ensure-Dashboard {
    $listenerPids = @(Get-ListenerPidsByPort -Port 8787)
    $p = @(Get-PythonProcessesByCommandPatterns -Patterns @("*multi5_dashboard_server.py*"))
    $rootProcesses = @(Get-RootProcessesFromSet -Processes $p)
    $chains = @(Get-ProcessChainGroupsFromSet -Processes $p)
    if ($listenerPids.Count -eq 1 -and $p.Count -ge 1 -and @($rootProcesses).Count -eq 1 -and $chains.Count -eq 1) {
        return
    }
    if ($chains.Count -gt 1) {
        $preferredChain = $null
        foreach ($chain in $chains) {
            if ((@($chain.MemberPids | Where-Object { $listenerPids -contains $_ }).Count) -ge 1) {
                $preferredChain = $chain
                break
            }
        }
        if (-not $preferredChain) {
            $preferredChain = @($chains | Where-Object { $_.RootProcess.CommandLine -like "*\.venv\Scripts\python.exe*" } | Select-Object -First 1)
            if ($preferredChain.Count -ge 1) {
                $preferredChain = $preferredChain[0]
            }
        }
        if (-not $preferredChain) {
            $preferredChain = @($chains | Select-Object -First 1)[0]
        }
        foreach ($chain in $chains) {
            if ($chain.RootProcessId -ne $preferredChain.RootProcessId) {
                foreach ($member in @($chain.Members | Sort-Object ProcessId -Descending)) {
                    try {
                        Stop-Process -Id $member.ProcessId -Force -ErrorAction Stop
                        Log "DASHBOARD_DUPLICATE_CHAIN_CLEANUP stopped_pid=$($member.ProcessId) keep_root_pid=$($preferredChain.RootProcessId)"
                    } catch {
                        Log "DASHBOARD_DUPLICATE_CHAIN_CLEANUP_FAIL pid=$($member.ProcessId) error=$($_.Exception.Message)"
                    }
                }
            }
        }
        Start-Sleep -Seconds 1
        $listenerPids = @(Get-ListenerPidsByPort -Port 8787)
        $p = @(Get-PythonProcessesByCommandPatterns -Patterns @("*multi5_dashboard_server.py*"))
        $rootProcesses = @(Get-RootProcessesFromSet -Processes $p)
        $chains = @(Get-ProcessChainGroupsFromSet -Processes $p)
        if ($listenerPids.Count -eq 1 -and $p.Count -ge 1 -and @($rootProcesses).Count -eq 1 -and $chains.Count -eq 1) {
            return
        }
    }
    $listenerMissing = ($listenerPids.Count -eq 0)
    if ($listenerMissing -and $p.Count -ge 1) {
        $ageSec = -1
        if ($script:LastDashboardStartAt) {
            $ageSec = [int]((Get-Date) - $script:LastDashboardStartAt).TotalSeconds
            if ($ageSec -lt $DashboardRestartCooldownSec) {
                Log "DASHBOARD_RESTART_COOLDOWN_ACTIVE age_sec=$ageSec cooldown_sec=$DashboardRestartCooldownSec process_count=$($p.Count)"
                return
            }
        }
        foreach ($stale in $p) {
            try {
                Stop-Process -Id $stale.ProcessId -Force -ErrorAction Stop
                Log "DASHBOARD_STALE_PROCESS_STOPPED pid=$($stale.ProcessId) age_sec=$ageSec"
            } catch {
                Log "DASHBOARD_STALE_PROCESS_STOP_FAIL pid=$($stale.ProcessId) error=$($_.Exception.Message)"
            }
        }
        Start-Sleep -Seconds 1
        $p = @()
        $chains = @()
    }
    if ($p.Count -gt 1) {
        $preferred = $p | Where-Object { $_.CommandLine -like "*\.venv\Scripts\python.exe*" } | Select-Object -First 1
        if (-not $preferred) {
            $preferred = $p | Select-Object -First 1
        }
        foreach ($dup in $p) {
            if ($dup.ProcessId -ne $preferred.ProcessId) {
                try {
                    Stop-Process -Id $dup.ProcessId -Force -ErrorAction Stop
                    Log "DASHBOARD_DUPLICATE_CLEANUP stopped_pid=$($dup.ProcessId) keep_pid=$($preferred.ProcessId)"
                } catch {
                    Log "DASHBOARD_DUPLICATE_CLEANUP_FAIL pid=$($dup.ProcessId) error=$($_.Exception.Message)"
                }
            }
        }
        $p = @($preferred)
    }
    if (-not $p) {
        & $dashboardStartScript | Out-Null
        $script:LastDashboardStartAt = Get-Date
        Log "START dashboard_8787"
    }
}

function Ensure-Api {
    $ok = $false
    try {
        $code = (Invoke-WebRequest -Uri "http://127.0.0.1:8100/api/v1/ops/health" -UseBasicParsing -TimeoutSec 6).StatusCode
        $ok = ($code -eq 200)
    } catch {
        $ok = $false
    }
    if (-not $ok) {
        Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $apiStartScript
        ) -WindowStyle Hidden | Out-Null
        Log "START api_8100"
    }
}

function Ensure-Phase5Observe {
    $p = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "powershell.exe" -and
        $_.CommandLine -like "*observe_multi5_realtime.ps1*" -and
        $_.CommandLine -like "*nt_phase5_multi_symbol_metrics.jsonl*" -and
        $_.CommandLine -notlike "* -Command *"
    }
    if (-not $p) {
        Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile","-ExecutionPolicy","Bypass","-File","C:\next-trade-ver1.0\BOOT\observe_multi5_realtime.ps1",
            "-IntervalSec","60","-DurationMinutes","1440",
            "-OutputJsonlPath",$phase5Metrics,
            "-OutputStatusPath",$phase5Status
        ) -WindowStyle Hidden | Out-Null
        Log "START phase5_observe"
    }
}

function Ensure-Phase5Milestones {
    $p = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "powershell.exe" -and
        $_.CommandLine -like "*phase5_portfolio_milestone_reporter.ps1*" -and
        $_.CommandLine -notlike "* -Command *"
    }
    if (-not $p) {
        Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile","-ExecutionPolicy","Bypass","-File","C:\next-trade-ver1.0\BOOT\phase5_portfolio_milestone_reporter.ps1",
            "-IntervalSec","60","-DurationMinutes","1440"
        ) -WindowStyle Hidden | Out-Null
        Log "START phase5_milestones"
    }
}

function Ensure-DashboardValidationMonitor {
    $p = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "powershell.exe" -and
        $_.CommandLine -like "*monitor_dashboard_runtime_validation.ps1*" -and
        $_.CommandLine -notlike "* -Command *"
    }
    if (-not $p) {
        Start-Process -FilePath "powershell.exe" -ArgumentList @(
            "-NoProfile","-ExecutionPolicy","Bypass","-File",$dashboardValidationScript,
            "-IntervalSec","30","-ObserveMinutes","10080","-ApiTimeoutSec","20","-SlowRuntimeThresholdMs","2000"
        ) -WindowStyle Hidden | Out-Null
        Log "START dashboard_runtime_validation_monitor"
    }
}

function Run-RuntimeHealthValidation {
    if (-not (Test-Path $runtimeHealthValidationScript)) {
        Log "RUNTIME_HEALTH_VALIDATION_SCRIPT_MISSING"
        return $null
    }
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $runtimeHealthValidationScript | Out-Null
        if (-not (Test-Path $runtimeHealthValidationPath)) {
            Log "RUNTIME_HEALTH_VALIDATION status=MISSING_REPORT"
            return [pscustomobject]@{
                status = "MISSING_REPORT"
                issues = @("RUNTIME_HEALTH_VALIDATION_MISSING_REPORT")
            }
        }
        $validationRaw = [string](Get-Content $runtimeHealthValidationPath -Raw -ErrorAction SilentlyContinue)
        $validation = $validationRaw | ConvertFrom-Json
        $status = [string]$validation.status
        $issues = @($validation.issues | ForEach-Object { [string]$_ }) -join ","
        if ([string]::IsNullOrWhiteSpace($issues)) {
            $issues = "-"
        }
        Log "RUNTIME_HEALTH_VALIDATION status=$status issues=$issues"
        return $validation
    } catch {
        Log "RUNTIME_HEALTH_VALIDATION_FAILED error=$($_.Exception.Message)"
        return [pscustomobject]@{
            status = "FAIL"
            issues = @("RUNTIME_HEALTH_VALIDATION_EXECUTION_FAILED")
        }
    }
}

function Test-HealthRestartCooldownActive([int]$CooldownSec) {
    $lastRestartAt = $script:LastHealthRestartAt
    if ((-not $lastRestartAt) -and (Test-Path $healthRestartStatePath)) {
        try {
            $state = Get-Content $healthRestartStatePath -Raw -Encoding UTF8 | ConvertFrom-Json
            $lastRestartAt = [datetime]::Parse([string]$state.last_restart_at)
            $script:LastHealthRestartAt = $lastRestartAt
        } catch {
            $lastRestartAt = $null
        }
    }
    if (-not $lastRestartAt) {
        return $false
    }
    $ageSec = [int]((Get-Date) - $lastRestartAt).TotalSeconds
    return ($ageSec -lt $CooldownSec)
}

function Write-HealthRestartState([string]$Reason, [string]$Status, [string[]]$Issues) {
    $payload = [ordered]@{
        last_restart_at = (Get-Date).ToString("o")
        reason = $Reason
        status = $Status
        issues = @($Issues)
    }
    $payload | ConvertTo-Json -Depth 4 | Set-Content -Path $healthRestartStatePath -Encoding UTF8
}

function Invoke-HealthDrivenRestart([string]$Reason, [string]$Status, [string[]]$Issues) {
    $issuesText = @($Issues | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -join ","
    if ([string]::IsNullOrWhiteSpace($issuesText)) {
        $issuesText = "-"
    }
    if (Test-HealthRestartCooldownActive -CooldownSec $HealthRestartCooldownSec) {
        $ageSec = [int]((Get-Date) - $script:LastHealthRestartAt).TotalSeconds
        Log "HEALTH_RESTART_SKIPPED status=$Status reason=$Reason issues=$issuesText cooldown_remaining_sec=$($HealthRestartCooldownSec - $ageSec)"
        return
    }
    if (-not (Test-Path $restartEngineScript)) {
        Log "HEALTH_RESTART_SKIPPED status=$Status reason=$Reason issues=$issuesText restart_script_missing=YES"
        return
    }
    $script:LastHealthRestartAt = Get-Date
    Write-HealthRestartState -Reason $Reason -Status $Status -Issues $Issues
    Log "HEALTH_RESTART_TRIGGER status=$Status reason=$Reason issues=$issuesText"
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $restartEngineScript | Out-Null
        Log "HEALTH_RESTART_DISPATCHED status=$Status reason=$Reason"
    } catch {
        Log "HEALTH_RESTART_FAILED status=$Status reason=$Reason error=$($_.Exception.Message)"
    }
}

function Get-HealthActionClass([string[]]$Issues) {
    $issueSet = @($Issues | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    if ($issueSet.Count -eq 0) {
        return "none"
    }
    foreach ($issue in $issueSet) {
        if ($script:ImmediateRestartIssues -contains $issue) {
            return "restart_immediate"
        }
    }
    $allNoRestart = $true
    foreach ($issue in $issueSet) {
        if (-not ($script:NoRestartIssues -contains $issue)) {
            $allNoRestart = $false
            break
        }
    }
    if ($allNoRestart) {
        return "no_restart"
    }
    foreach ($issue in $issueSet) {
        if ($script:SoftFailIssues -contains $issue) {
            return "restart_soft"
        }
    }
    return "restart_immediate"
}

function Apply-RuntimeHealthPolicy($validation) {
    if (-not $validation) {
        return
    }

    $status = [string]$validation.status
    $issues = @($validation.issues | ForEach-Object { [string]$_ })
    $actionClass = Get-HealthActionClass -Issues $issues

    switch ($status) {
        "PASS" {
            $script:ConsecutiveHealthWarnCount = 0
            return
        }
        "WARN" {
            if ($actionClass -eq "no_restart") {
                Log "HEALTH_POLICY_NO_RESTART status=$status issues=$(@($issues) -join ',')"
                $script:ConsecutiveHealthWarnCount = 0
                return
            }
            $script:ConsecutiveHealthWarnCount += 1
            Log "HEALTH_POLICY_WARN_COUNT class=$actionClass count=$($script:ConsecutiveHealthWarnCount) threshold=$WarnRestartThreshold"
            if ($script:ConsecutiveHealthWarnCount -ge $WarnRestartThreshold) {
                Invoke-HealthDrivenRestart -Reason "WARN_THRESHOLD" -Status $status -Issues $issues
                $script:ConsecutiveHealthWarnCount = 0
            }
            return
        }
        "FAIL" {
            if ($actionClass -eq "no_restart") {
                Log "HEALTH_POLICY_NO_RESTART status=$status issues=$(@($issues) -join ',')"
                $script:ConsecutiveHealthWarnCount = 0
                return
            }
            if ($actionClass -eq "restart_soft") {
                $script:ConsecutiveHealthWarnCount += 1
                Log "HEALTH_POLICY_FAIL_SOFT issues=$(@($issues) -join ',') count=$($script:ConsecutiveHealthWarnCount) threshold=$WarnRestartThreshold"
                if ($script:ConsecutiveHealthWarnCount -ge $WarnRestartThreshold) {
                    Invoke-HealthDrivenRestart -Reason "SOFT_FAIL_THRESHOLD" -Status $status -Issues $issues
                    $script:ConsecutiveHealthWarnCount = 0
                }
                return
            }
            $script:ConsecutiveHealthWarnCount = 0
            Invoke-HealthDrivenRestart -Reason "FAIL_STATUS" -Status $status -Issues $issues
            return
        }
        default {
            Log "HEALTH_POLICY_UNKNOWN_STATUS status=$status"
            return
        }
    }
}

function Get-WorkerProcesses {
    return @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*profitmax_v1_runner.py*"
    })
}

function Get-SymbolWorkerLockState([string]$symbol) {
    $symbolKey = ([string]$symbol).ToLowerInvariant()
    $lockPath = Join-Path $projectRoot ("logs\\runtime\\profitmax_v1_runner_{0}.lock" -f $symbolKey)
    if (-not (Test-Path $lockPath)) {
        return [pscustomobject]@{
            exists = $false
            pid = 0
            alive = $false
            path = $lockPath
        }
    }
    try {
        $lockObj = Get-Content $lockPath | ConvertFrom-Json
        $lockPid = [int]$lockObj.pid
        $lockProc = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $lockPid) -ErrorAction SilentlyContinue
        return [pscustomobject]@{
            exists = $true
            pid = $lockPid
            alive = ($null -ne $lockProc)
            path = $lockPath
        }
    } catch {
        return [pscustomobject]@{
            exists = $true
            pid = 0
            alive = $false
            path = $lockPath
        }
    }
}

function Get-OpenSymbols {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8100/api/v1/investor/positions" -TimeoutSec 10
    } catch {
        return @()
    }
    $open = @()
    foreach ($p in $resp.positions) {
        $qty = 0.0
        try { $qty = [double]$p.positionAmt } catch { $qty = 0.0 }
        if ([math]::Abs($qty) -gt 0.0) {
            $open += ([string]$p.symbol).ToUpper()
        }
    }
    return @($open | Sort-Object -Unique)
}

function Get-LatestSelectedSymbols {
    if (-not (Test-Path $workerSummaryPath)) {
        return @()
    }
    try {
        $summary = Get-Content $workerSummaryPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $selected = @()
        foreach ($symbol in @($summary.selected_symbols_batch)) {
            $symbolText = [string]$symbol
            if ([string]::IsNullOrWhiteSpace($symbolText)) {
                continue
            }
            $selected += $symbolText.ToUpperInvariant()
        }
        return @($selected | Select-Object -Unique)
    } catch {
        return @()
    }
}

function WorkerLogStale {
    if (-not (Test-Path $workerLogPath)) { return $true }
    try {
        $line = Get-Content $workerLogPath -Tail 1
        if (-not $line) { return $true }
        $obj = $line | ConvertFrom-Json
        $ts = [datetimeoffset]::Parse([string]$obj.ts)
        $age = [int](((Get-Date).ToUniversalTime() - $ts.UtcDateTime).TotalSeconds)
        return ($age -gt $WorkerStaleSec)
    } catch {
        return $true
    }
}

function Ensure-WorkersForOpenPositions {
    $openSymbols = Get-OpenSymbols
    $selectedSymbols = @(Get-LatestSelectedSymbols)
    $warmTargetLimit = [Math]::Max(0, [int]$WarmWorkerTargetCount)
    $warmCandidates = @()
    if ($warmTargetLimit -gt 0) {
        $warmCandidates = @(
            @($selectedSymbols) |
            Where-Object { $openSymbols -notcontains $_ } |
            Select-Object -First $warmTargetLimit
        )
    }
    $targetSymbolsRaw = @()
    $targetSymbolsRaw += @($openSymbols)
    $targetSymbolsRaw += @($warmCandidates)
    $targetSymbols = @(
        $targetSymbolsRaw |
        ForEach-Object { [string]$_ } |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
        ForEach-Object { $_.ToUpperInvariant() } |
        Select-Object -Unique
    )
    if ($targetSymbols.Count -eq 0) { return }

    $workers = Get-WorkerProcesses
    $stale = WorkerLogStale

    foreach ($worker in $workers) {
        $cmd = [string]$worker.CommandLine
        $match = [regex]::Match($cmd, "--symbol\s+([A-Za-z0-9_]+)")
        if (-not $match.Success) {
            continue
        }
        $workerSymbol = $match.Groups[1].Value.ToUpperInvariant()
        if (($targetSymbols -contains $workerSymbol) -or ($openSymbols -contains $workerSymbol)) {
            continue
        }
        try {
            Stop-Process -Id $worker.ProcessId -Force -ErrorAction Stop
            Log "STOP worker symbol=$workerSymbol reason=not_in_target_set pid=$($worker.ProcessId)"
        } catch {
            Log "STOP worker_failed symbol=$workerSymbol reason=not_in_target_set pid=$($worker.ProcessId) error=$($_.Exception.Message)"
        }
    }
    $workers = Get-WorkerProcesses

    foreach ($sym in $targetSymbols) {
        $exists = $false
        foreach ($w in $workers) {
            if ([string]$w.CommandLine -match ("--symbol\\s+" + [regex]::Escape($sym))) {
                $exists = $true
                if ($stale) {
                    try { Stop-Process -Id $w.ProcessId -Force } catch {}
                    $exists = $false
                    Log "RESTART worker_stale symbol=$sym old_pid=$($w.ProcessId)"
                }
                break
            }
        }
        if (-not $exists) {
            $lockState = Get-SymbolWorkerLockState -symbol $sym
            if ($lockState.exists -and $lockState.alive) {
                $exists = $true
                Log "SKIP worker_start lock_alive symbol=$sym lock_pid=$($lockState.pid)"
            }
        }
        if (-not $exists) {
            $strategySignalPath = Join-Path $workerStrategySignalDir ("{0}_{1}.json" -f $sym.ToUpper(), $workerStrategyUnit)
            Start-Process -FilePath $pythonExe -ArgumentList @(
                $workerScript,
                "--profile","TESTNET_INTRADAY_SCALP",
                "--session-hours","2.0",
                "--max-positions","$workerMaxPositions",
                "--base-qty","0.004",
                "--symbol",$sym,
                "--strategy-unit",$workerStrategyUnit,
                "--strategy-signal-path",$strategySignalPath,
                "--take-profit-pct-override",$workerTakeProfitPct,
                "--stop-loss-pct-override",$workerStopLossPct,
                "--evidence-path",$workerLogPath,
                "--summary-path",$workerSummaryPath
            ) -WorkingDirectory $projectRoot -WindowStyle Hidden | Out-Null
            $workerRole = if ($openSymbols -contains $sym) { "open_position" } else { "warm_selected" }
            Log "START worker symbol=$sym strategy_unit=$workerStrategyUnit role=$workerRole"
        }
    }
}

Log ("PHASE5_AUTOGUARD_START interval_sec={0} observe_minutes={1} stale_sec={2} warm_worker_target_count={3}" -f $IntervalSec, $ObserveMinutes, $WorkerStaleSec, $WarmWorkerTargetCount)

while ((Get-Date) -lt $endAt) {
    Ensure-RuntimeGuard
    Ensure-Engine
    Ensure-Api
    Ensure-Dashboard
    Ensure-DashboardValidationMonitor
    $validation = Run-RuntimeHealthValidation
    Apply-RuntimeHealthPolicy -validation $validation
    Ensure-Phase5Observe
    Ensure-Phase5Milestones
    Ensure-WorkersForOpenPositions
    Start-Sleep -Seconds $IntervalSec
}

Log "PHASE5_AUTOGUARD_END"

