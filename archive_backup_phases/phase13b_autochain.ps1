param(
    [int]$PollSec = 20
)

$ErrorActionPreference = "Continue"

$runnerScript = "C:\next-trade-ver1.0\reports\phase13_same_window_pf\phase13b_capture_runner.ps1"
$chainLog = "C:\next-trade-ver1.0\reports\phase13_same_window_pf\phase13b_autochain.log"
$apiCmd = "C:\next-trade-ver1.0\tools\ops\run_api_8100.cmd"

function Test-ApiHealthy {
    try {
        $code = (Invoke-WebRequest -Uri "http://127.0.0.1:8100/api/v1/ops/health" -UseBasicParsing -TimeoutSec 5).StatusCode
        return ($code -eq 200)
    } catch {
        return $false
    }
}

function Ensure-Api {
    if (Test-ApiHealthy) { return }
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $apiCmd -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 3
}

function Get-RunnerProcs {
    @(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "powershell.exe" -and $_.CommandLine -like "*phase13b_capture_runner.ps1*" })
}

New-Item -ItemType Directory -Force -Path (Split-Path $chainLog) | Out-Null
Add-Content -Path $chainLog -Encoding UTF8 -Value ("AUTOCHAIN_START_KST=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss K"))

while ($true) {
    $runners = Get-RunnerProcs
    if ($runners.Count -eq 0) {
        Ensure-Api
        $p = Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $runnerScript -PassThru -WindowStyle Hidden
        Add-Content -Path $chainLog -Encoding UTF8 -Value ("SESSION_STARTED_KST=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss K") + " PID=" + $p.Id)
    }
    Start-Sleep -Seconds $PollSec
}



