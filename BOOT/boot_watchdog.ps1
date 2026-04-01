param(
    [int]$ApiWaitSec = 12,
    [int]$EngineWaitSec = 8,
    [int]$UiWaitSec = 15,
    [int]$DashWaitSec = 12
)

$ErrorActionPreference = "Continue"
. "C:\next-trade-ver1.0\BOOT\report_path_resolver.ps1"

$projectRoot = "C:\next-trade-ver1.0"
$engineRoot = $projectRoot
$bootRoot = Join-Path $projectRoot "BOOT"
$opsUiRoot = Join-Path $projectRoot "evergreen-ops-ui"
$pythonExe = Join-Path $engineRoot ".venv\Scripts\python.exe"
$venvFallback = Join-Path $engineRoot "venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe) -and (Test-Path $venvFallback)) {
    $pythonExe = $venvFallback
}
$dashScript = Join-Path $engineRoot "tools\dashboard\multi5_dashboard_server.py"
$dashStartScript = Join-Path $bootRoot "start_dashboard_8788.ps1"
$logPath = Join-Path $projectRoot "logs\service\boot_watchdog_log.txt"
$completionStatusPath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "auto_boot_completion_status.json" -EnsureParent

New-Item -ItemType Directory -Force -Path (Split-Path $logPath -Parent) | Out-Null

function Log([string]$line) {
    $ts = (Get-Date).ToString("s")
    Add-Content -Path $logPath -Value "$ts $line"
}

function Test-PortListening([int]$port) {
    $hit = netstat -ano | findstr ":$port" | findstr "LISTENING"
    return [bool]$hit
}

function Get-ProcCount([string]$pattern) {
    return @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq "python.exe" -and $_.CommandLine -like "*$pattern*"
        }
    ).Count
}

function Get-EngineProcesses {
    return @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq "python.exe" -and $_.CommandLine -like "*run_multi5_engine.py*"
        }
    )
}

function Get-EngineRootProcesses {
    $engines = Get-EngineProcesses
    $roots = @()
    foreach ($e in $engines) {
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($e.ParentProcessId)" -ErrorAction SilentlyContinue
        if (-not $parent -or [string]$parent.CommandLine -notlike "*run_multi5_engine.py*") {
            $roots += $e
        }
    }
    return @($roots)
}

function Enforce-SingleEngine {
    $rootEngines = Get-EngineRootProcesses
    if ($rootEngines.Count -le 1) {
        return
    }

    $preferred = $rootEngines | Where-Object { $_.CommandLine -like "*\.venv\Scripts\python.exe*" } | Select-Object -First 1
    if (-not $preferred) {
        $preferred = $rootEngines | Select-Object -First 1
    }

    foreach ($p in $rootEngines) {
        if ($p.ProcessId -ne $preferred.ProcessId) {
            try {
                Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
                Log "ENGINE_DUPLICATE_CLEANUP stopped_pid=$($p.ProcessId) keep_pid=$($preferred.ProcessId)"
            } catch {
                Log "ENGINE_DUPLICATE_CLEANUP_FAIL pid=$($p.ProcessId) error=$($_.Exception.Message)"
            }
        }
    }
}

function Get-GuardCount {
    return @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq "powershell.exe" -and
            $_.CommandLine -like "*runtime_guard.ps1*" -and
            $_.CommandLine -notlike "* -Command *"
        }
    ).Count
}

function Get-AutoGuardCount {
    return @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq "powershell.exe" -and
            $_.CommandLine -like "*phase5_autoguard.ps1*" -and
            $_.CommandLine -notlike "* -Command *"
        }
    ).Count
}

function Write-CompletionStatus([bool]$completed, [string]$message) {
    New-Item -ItemType Directory -Force -Path (Split-Path $completionStatusPath -Parent) | Out-Null
    $payload = @{
        ts = (Get-Date).ToString("o")
        completed = $completed
        message = $message
        source = "boot_watchdog.ps1"
    } | ConvertTo-Json -Depth 4 -Compress
    Set-Content -Path $completionStatusPath -Encoding UTF8 -Value $payload
}

function Open-DashboardCompletionPage {
    $url = "http://127.0.0.1:8788/"
    $sessionName = $env:SESSIONNAME
    $interactive = [Environment]::UserInteractive
    Log "DASHBOARD_OPEN_ATTEMPT url=$url session=$sessionName interactive=$interactive"

    $chromeCandidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LocalAppData\Google\Chrome\Application\chrome.exe",
        "chrome.exe"
    )

    $chromeExe = $null
    foreach ($candidate in $chromeCandidates) {
        if ($candidate -eq "chrome.exe") {
            $cmd = Get-Command "chrome.exe" -ErrorAction SilentlyContinue
            if ($cmd) {
                $chromeExe = $cmd.Source
                break
            }
        } elseif (Test-Path $candidate) {
            $chromeExe = $candidate
            break
        }
    }

    if (-not $chromeExe) {
        Log "DASHBOARD_OPEN_FAIL method=chrome_lookup url=$url error=chrome_not_found"
    }

    function Open-ByCmdStart([string]$targetUrl) {
        try {
            Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "start", "", $targetUrl) -WindowStyle Hidden | Out-Null
            Start-Sleep -Milliseconds 300
            Log "DASHBOARD_OPEN_SUCCESS method=cmd_start url=$targetUrl"
            return $true
        } catch {
            Log "DASHBOARD_OPEN_FAIL method=cmd_start url=$targetUrl error=$($_.Exception.Message)"
            return $false
        }
    }

    if (-not $interactive) {
        $taskName = "NT_OpenDashboardChrome_OneShot"
        $runAt = (Get-Date).AddMinutes(1).ToString("HH:mm")
        $runUser = "INTERACTIVE"
        $taskCmd = "cmd.exe /c start `"`" `"$url`""
        try {
            schtasks /Create /TN $taskName /SC ONCE /ST $runAt /TR $taskCmd /RU $runUser /IT /F /Z | Out-Null
            schtasks /Run /TN $taskName | Out-Null
            Start-Sleep -Milliseconds 800
            Log "DASHBOARD_OPEN_SUCCESS method=cmd_start_schtasks url=$url user=$runUser"
            return
        } catch {
            Log "DASHBOARD_OPEN_FAIL method=cmd_start_schtasks url=$url user=$runUser error=$($_.Exception.Message)"
        }
    }

    if ($chromeExe) {
        try {
            Start-Process -FilePath $chromeExe -ArgumentList @("--new-window", $url) | Out-Null
            Start-Sleep -Milliseconds 300
            Log "DASHBOARD_OPEN_SUCCESS method=chrome url=$url exe=$chromeExe"
            return
        } catch {
            Log "DASHBOARD_OPEN_FAIL method=chrome url=$url exe=$chromeExe error=$($_.Exception.Message)"
        }
    }

    if (Open-ByCmdStart $url) { return }

    try {
        Start-Process -FilePath "explorer.exe" -ArgumentList $url | Out-Null
        Start-Sleep -Milliseconds 300
        Log "DASHBOARD_OPEN_SUCCESS method=explorer url=$url"
        return
    } catch {
        Log "DASHBOARD_OPEN_FAIL method=explorer url=$url error=$($_.Exception.Message)"
    }

    Log "DASHBOARD_OPEN_GIVEUP url=$url"
}

function Resolve-VSCodeExe {
    $candidates = @(
        "C:\Program Files\Microsoft VS Code\Code.exe",
        "C:\Users\Administrator\AppData\Local\Programs\Microsoft VS Code\Code.exe",
        "$env:LocalAppData\Programs\Microsoft VS Code\Code.exe"
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    $cmd = Get-Command "code" -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) {
        return $cmd.Source
    }

    return $null
}

function Open-VSCodeWorkspace {
    $workspace = $projectRoot
    $sessionName = $env:SESSIONNAME
    $interactive = [Environment]::UserInteractive
    $codeExe = Resolve-VSCodeExe
    Log "VSCODE_OPEN_ATTEMPT workspace=$workspace session=$sessionName interactive=$interactive"

    if (-not $interactive) {
        $taskName = "NT_OpenVSCode_OneShot"
        $runAt = (Get-Date).AddMinutes(1).ToString("HH:mm")
        $runUser = "INTERACTIVE"
        if ($codeExe) {
            $taskCmd = "cmd.exe /c start `"`" `"$codeExe`" `"$workspace`""
        } else {
            $taskCmd = "cmd.exe /c start `"`" code `"$workspace`""
        }

        try {
            schtasks /Create /TN $taskName /SC ONCE /ST $runAt /TR $taskCmd /RU $runUser /IT /F /Z | Out-Null
            schtasks /Run /TN $taskName | Out-Null
            Start-Sleep -Milliseconds 800
            Log "VSCODE_OPEN_SUCCESS method=schtasks workspace=$workspace user=$runUser"
            return
        } catch {
            Log "VSCODE_OPEN_FAIL method=schtasks workspace=$workspace user=$runUser error=$($_.Exception.Message)"
        }
    }

    if ($codeExe) {
        try {
            Start-Process -FilePath $codeExe -ArgumentList @($workspace) | Out-Null
            Start-Sleep -Milliseconds 300
            Log "VSCODE_OPEN_SUCCESS method=code_exe workspace=$workspace exe=$codeExe"
            return
        } catch {
            Log "VSCODE_OPEN_FAIL method=code_exe workspace=$workspace exe=$codeExe error=$($_.Exception.Message)"
        }
    }

    try {
        Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", "start", "", "code", $workspace) -WindowStyle Hidden | Out-Null
        Start-Sleep -Milliseconds 300
        Log "VSCODE_OPEN_SUCCESS method=cmd_code workspace=$workspace"
        return
    } catch {
        Log "VSCODE_OPEN_FAIL method=cmd_code workspace=$workspace error=$($_.Exception.Message)"
    }

    Log "VSCODE_OPEN_GIVEUP workspace=$workspace"
}

function Ensure-Api {
    $ok = $false
    try {
        $status = (Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:8100/api/v1/ops/health" -TimeoutSec 5).StatusCode
        $ok = ($status -eq 200)
    } catch { $ok = $false }

    if (-not $ok) {
        Log "API_8100_START_ATTEMPT async start_api_8100_safe.ps1"
        try {
            Start-Process -FilePath "powershell.exe" -ArgumentList @(
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", (Join-Path $bootRoot "start_api_8100_safe.ps1")
            ) -WindowStyle Hidden | Out-Null
        } catch {
            Log "API_8100_START_ERROR error=$($_.Exception.Message)"
        }
        Start-Sleep -Seconds $ApiWaitSec
    }
}

function Ensure-EngineAndGuard {
    Log "ENGINE_CHAIN_START via start_engine.ps1"
    try {
        & (Join-Path $bootRoot "start_engine.ps1") | Out-Null
    } catch {
        Log "ENGINE_CHAIN_ERROR error=$($_.Exception.Message)"
    }
    Start-Sleep -Seconds $EngineWaitSec

    if ((Get-GuardCount) -eq 0) {
        Log "RUNTIME_GUARD_START_ATTEMPT direct"
        try {
            & (Join-Path $bootRoot "start_runtime_guard.ps1") | Out-Null
        } catch {
            Log "RUNTIME_GUARD_START_ERROR error=$($_.Exception.Message)"
        }
        Start-Sleep -Seconds 2
    }
}

function Ensure-Dashboard {
    $autoGuardCount = Get-AutoGuardCount
    if ($autoGuardCount -ge 1) {
        Log "DASH_8788_DEFER_TO_AUTOGUARD autoguard_count=$autoGuardCount"
        return
    }
    $listenerPids = @(
        Get-NetTCPConnection -State Listen -LocalPort 8788 -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    )
    $dashProc = @(
        Get-CimInstance Win32_Process | Where-Object {
            $_.Name -eq "python.exe" -and $_.CommandLine -like "*multi5_dashboard_server.py*"
        }
    )
    if ($listenerPids.Count -eq 1 -and $dashProc.Count -ge 1) {
        return
    }
    if ($dashProc.Count -gt 1) {
        $preferred = $dashProc | Where-Object { $_.CommandLine -like "*\.venv\Scripts\python.exe*" } | Select-Object -First 1
        if (-not $preferred) {
            $preferred = $dashProc | Select-Object -First 1
        }
        foreach ($dup in $dashProc) {
            if ($dup.ProcessId -ne $preferred.ProcessId) {
                try {
                    Stop-Process -Id $dup.ProcessId -Force -ErrorAction Stop
                    Log "DASHBOARD_DUPLICATE_CLEANUP stopped_pid=$($dup.ProcessId) keep_pid=$($preferred.ProcessId)"
                } catch {
                    Log "DASHBOARD_DUPLICATE_CLEANUP_FAIL pid=$($dup.ProcessId) error=$($_.Exception.Message)"
                }
            }
        }
        Start-Sleep -Seconds 1
        $dashProc = @(
            Get-CimInstance Win32_Process | Where-Object {
                $_.Name -eq "python.exe" -and $_.CommandLine -like "*multi5_dashboard_server.py*"
            }
        )
    }
    if ((Test-PortListening 8788) -and $dashProc.Count -ge 1) {
        return
    }
    if ($dashProc.Count -eq 0) {
        Log "DASH_8788_START_ATTEMPT script=multi5_dashboard_server.py"
        try {
            & $dashStartScript | Out-Null
        } catch {
            Log "DASH_8788_START_ERROR error=$($_.Exception.Message)"
        }
        Start-Sleep -Seconds $DashWaitSec
    }
}

function Ensure-OpsUi {
    if (Test-PortListening 3001) {
        return
    }
    Log "OPS_UI_3001_START_ATTEMPT cmd=npm run dev -- --port 3001"
    try {
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c","npm run dev -- --port 3001" -WorkingDirectory $opsUiRoot -WindowStyle Hidden | Out-Null
    } catch {
        Log "OPS_UI_3001_START_ERROR error=$($_.Exception.Message)"
    }
    Start-Sleep -Seconds $UiWaitSec
}

Log "BOOT_WATCHDOG_START"
Ensure-Api
Ensure-EngineAndGuard
Ensure-Dashboard
Ensure-OpsUi
Enforce-SingleEngine

$api = Test-PortListening 8100
$ui = Test-PortListening 3001
$dash = Test-PortListening 8788
$engineCount = @(Get-EngineRootProcesses).Count
$guardCount = Get-GuardCount
$autoGuardCount = Get-AutoGuardCount
$autoReady = $api -and $ui -and $dash -and ($engineCount -ge 1) -and ($guardCount -ge 1) -and ($autoGuardCount -ge 1)

if ($autoReady) {
    $doneMsg = "AUTO_EXECUTION_COMPLETE: API_8100/OPS_UI_3001/DASH_8788/ENGINE/RUNTIME_GUARD/PHASE5_AUTOGUARD OK"
    Write-CompletionStatus -completed $true -message $doneMsg
    Log "AUTO_BOOT_COMPLETE message=$doneMsg"
} else {
    $failMsg = "AUTO_EXECUTION_INCOMPLETE: API_8100=$api OPS_UI_3001=$ui DASH_8788=$dash ENGINE_COUNT=$engineCount RUNTIME_GUARD_COUNT=$guardCount PHASE5_AUTOGUARD_COUNT=$autoGuardCount"
    Write-CompletionStatus -completed $false -message $failMsg
    Log "AUTO_BOOT_INCOMPLETE message=$failMsg"
}

Log "BOOT_WATCHDOG_STATUS API_8100=$api OPS_UI_3001=$ui DASH_8788=$dash ENGINE_COUNT=$engineCount RUNTIME_GUARD_COUNT=$guardCount PHASE5_AUTOGUARD_COUNT=$autoGuardCount AUTO_READY=$autoReady"
Log "BOOT_WATCHDOG_END"
