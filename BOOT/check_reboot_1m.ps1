$ErrorActionPreference = "SilentlyContinue"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

$outDir = Resolve-NtRoleReportDir -RoleFolder "honey_execution_reports" -EnsureExists
$outFile = Join-Path $outDir "nt_phase5_reboot_1m_check_report.txt"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Flag([bool]$v) { if ($v) { "YES" } else { "NO" } }

$apiListen = [bool](netstat -ano | findstr ":8100" | findstr "LISTENING")
$dashListen = [bool](netstat -ano | findstr ":8788" | findstr "LISTENING")

$engine = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "python.exe" -and $_.CommandLine -like "*run_multi5_engine.py*"
})
$engineAlive = $engine.Count -gt 0
$enginePids = ($engine | Select-Object -ExpandProperty ProcessId) -join ","

$autoguard = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq "powershell.exe" -and
    $_.CommandLine -like "*phase5_autoguard.ps1*" -and
    $_.CommandLine -notlike "* -Command *"
})
$autoguardAlive = $autoguard.Count -gt 0
$autoguardPids = ($autoguard | Select-Object -ExpandProperty ProcessId) -join ","

$runtimeApiOk = $false
$runtimeAlive = $false
$scanCount = 0
$scanTargetMet = $false
$pnlRealtime = $false
try {
    $rt = Invoke-RestMethod -Uri "http://127.0.0.1:8788/api/runtime" -TimeoutSec 12
    $runtimeApiOk = $true
    $runtimeAlive = [bool]$rt.runtime_alive
    try { $scanCount = [int]$rt.scan_symbol_count } catch { $scanCount = 0 }
    $scanTargetMet = [bool]$rt.scan_target_met
    $pnlRealtime = [bool]$rt.pnl_realtime
} catch {}

$lines = @(
    "CHECK_TS_KST=$((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))"
    "CHECK_SCOPE=REBOOT_PLUS_1M"
    "API_8100_LISTEN=" + (Flag $apiListen)
    "DASHBOARD_8788_LISTEN=" + (Flag $dashListen)
    "ENGINE_RUNNING=" + (Flag $engineAlive)
    "ENGINE_PID_LIST=$enginePids"
    "PHASE5_AUTOGUARD_RUNNING=" + (Flag $autoguardAlive)
    "PHASE5_AUTOGUARD_PID_LIST=$autoguardPids"
    "RUNTIME_API_OK=" + (Flag $runtimeApiOk)
    "RUNTIME_ALIVE=" + (Flag $runtimeAlive)
    "SCAN_SYMBOL_COUNT=$scanCount"
    "SCAN_TARGET_MET=" + (Flag $scanTargetMet)
    "PNL_REALTIME=" + (Flag $pnlRealtime)
)

$pass = $apiListen -and $dashListen -and $engineAlive -and $autoguardAlive -and $runtimeApiOk -and $runtimeAlive
if ($pass) {
    $lines += "NT_PHASE5_REBOOT_1M_CHECK_STATUS=PASS"
} else {
    $lines += "NT_PHASE5_REBOOT_1M_CHECK_STATUS=FAIL"
}

$lines | Set-Content -Encoding UTF8 $outFile
$lines | Write-Output

