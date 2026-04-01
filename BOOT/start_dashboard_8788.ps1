param(
    [int]$WaitSec = 12,
    [int]$SelfProbeCount = 3,
    [int]$SelfProbeTimeoutSec = 20,
    [int]$SelfProbeSleepMs = 400
)

$ErrorActionPreference = 'Stop'
$projectRoot = 'C:\next-trade-ver1.0'
. (Join-Path $projectRoot 'BOOT\common_process_helpers.ps1')
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    $pythonExe = Join-Path $projectRoot 'venv\Scripts\python.exe'
}
$dashboardScript = Join-Path $projectRoot 'tools\dashboard\multi5_dashboard_server.py'
$workdir = Split-Path $dashboardScript -Parent

function Get-DashboardProcesses {
    @(Get-PythonProcessesByCommandPatterns -Patterns @('*multi5_dashboard_server.py*'))
}

function Get-DashboardRootProcesses {
    @(Get-RootProcessesFromSet -Processes @(Get-DashboardProcesses))
}

function Get-DashboardProcessChains {
    @(Get-ProcessChainGroupsFromSet -Processes @(Get-DashboardProcesses))
}

function Select-PreferredDashboardChain {
    param(
        [array]$Chains,
        [int[]]$ListenerPids
    )

    foreach ($chain in @($Chains)) {
        $chainPids = @($chain.MemberPids)
        if ((@($chainPids | Where-Object { $ListenerPids -contains $_ }).Count) -ge 1) {
            return $chain
        }
    }

    $venvChain = @($Chains | Where-Object { $_.RootProcess.CommandLine -like "*\\.venv\\Scripts\\python.exe*" } | Select-Object -First 1)
    if ($venvChain.Count -ge 1) {
        return $venvChain[0]
    }

    @($Chains | Select-Object -First 1)[0]
}

$before = Get-DashboardProcesses
$beforeRoots = @(Get-DashboardRootProcesses)
$beforeChains = @(Get-DashboardProcessChains)
$listenersBefore = @(Get-ListenerPidsByPort -Port 8788)

if ($beforeChains.Count -gt 1) {
    $keepChain = Select-PreferredDashboardChain -Chains $beforeChains -ListenerPids $listenersBefore
    foreach ($chain in $beforeChains) {
        if ($chain.RootProcessId -ne $keepChain.RootProcessId) {
            foreach ($member in @($chain.Members | Sort-Object ProcessId -Descending)) {
                try {
                    Stop-Process -Id $member.ProcessId -Force -ErrorAction Stop
                } catch {
                }
            }
        }
    }
    Start-Sleep -Seconds 1
    $before = Get-DashboardProcesses
    $beforeRoots = @(Get-DashboardRootProcesses)
    $beforeChains = @(Get-DashboardProcessChains)
    $listenersBefore = @(Get-ListenerPidsByPort -Port 8788)
}

if ($listenersBefore.Count -eq 1 -and $before.Count -ge 1 -and $beforeRoots.Count -eq 1 -and $beforeChains.Count -eq 1) {
    [pscustomobject]@{
        started = $false
        reason = 'already_healthy'
        before_process_count = $before.Count
        before_root_count = $beforeRoots.Count
        before_chain_count = $beforeChains.Count
        listener_count = $listenersBefore.Count
        listener_pid = (@($listenersBefore) -join ',')
    } | ConvertTo-Json -Depth 4
    exit 0
}

Start-Process -FilePath $pythonExe -ArgumentList $dashboardScript -WorkingDirectory $workdir -WindowStyle Hidden | Out-Null
Start-Sleep -Seconds $WaitSec
$after = Get-DashboardProcesses
$afterRoots = @(Get-DashboardRootProcesses)
$afterChains = @(Get-DashboardProcessChains)
$listenersAfter = @(Get-ListenerPidsByPort -Port 8788)
$apiStatus = 'ERROR'
$selfProbeResults = @()
try {
    for ($i = 1; $i -le $SelfProbeCount; $i++) {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $resp = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8788/api/runtime' -TimeoutSec $SelfProbeTimeoutSec
        $sw.Stop()
        $selfProbeResults += [pscustomobject]@{
            run = $i
            status = [int]$resp.StatusCode
            elapsed_ms = $sw.ElapsedMilliseconds
            body_len = ([string]$resp.Content).Length
        }
        Start-Sleep -Milliseconds $SelfProbeSleepMs
    }
    $apiStatus = [string][int]($selfProbeResults[-1].status)
} catch {
    $apiStatus = 'ERROR:' + $_.Exception.Message
}

[pscustomobject]@{
    started = $true
    reason = 'launch_attempted'
    before_process_count = $before.Count
    before_root_count = $beforeRoots.Count
    before_chain_count = $beforeChains.Count
    after_process_count = $after.Count
    after_root_count = $afterRoots.Count
    after_chain_count = $afterChains.Count
    listener_count = $listenersAfter.Count
    listener_pid = (@($listenersAfter) -join ',')
    api_status = $apiStatus
    self_probe_count = $SelfProbeCount
    self_probe_results = $selfProbeResults
} | ConvertTo-Json -Depth 4

