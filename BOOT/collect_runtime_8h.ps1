param(
    [int]$IntervalSec = 60,
    [int]$DurationMinutes = 480
)

$ErrorActionPreference = "Continue"
. "C:\nt_v1\BOOT\report_path_resolver.ps1"

$runtimeLog = "C:\nt_v1\logs\runtime\multi5_runtime_events.jsonl"
$scanLog = "C:\nt_v1\logs\runtime\multi5_symbol_scan.jsonl"
$workerLog = "C:\nt_v1\logs\runtime\profitmax_v1_events.jsonl"
$outDir = Resolve-NtRoleReportDir -RoleFolder "honey_execution_reports" -EnsureExists
$outJsonl = Join-Path $outDir "nt_phase2_8h_live_collection.jsonl"
$outStatus = Join-Path $outDir "nt_phase2_8h_live_collection_status.txt"

New-Item -ItemType Directory -Force -Path $outDir | Out-Null

function Get-LineCount([string]$path) {
    if (-not (Test-Path $path)) { return -1 }
    return (Get-Content $path | Measure-Object -Line).Lines
}

function Get-LastTs([string]$path) {
    if (-not (Test-Path $path)) { return "" }
    $line = Get-Content $path -Tail 1 -ErrorAction SilentlyContinue
    if (-not $line) { return "" }
    try {
        $obj = $line | ConvertFrom-Json
        if ($obj.ts) { return [string]$obj.ts }
        if ($obj.timestamp) { return [string]$obj.timestamp }
        return ""
    } catch {
        return ""
    }
}

$start = Get-Date
$endAt = $start.AddMinutes($DurationMinutes)
$samples = 0

Set-Content -Path $outStatus -Encoding UTF8 -Value @(
    "COLLECTION_STARTED_AT=$($start.ToString('s'))"
    "COLLECTION_DURATION_MIN=$DurationMinutes"
    "COLLECTION_INTERVAL_SEC=$IntervalSec"
    "COLLECTION_STATUS=RUNNING"
)

while ((Get-Date) -lt $endAt) {
    $roots = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*run_multi5_engine.py*"
    })
    $workers = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "python.exe" -and $_.CommandLine -like "*profitmax_v1_runner.py*"
    })
    $guards = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq "powershell.exe" -and $_.CommandLine -like "*runtime_guard.ps1*" -and $_.CommandLine -notlike "* -Command *"
    })

    $apiListen = @(netstat -ano | findstr ":8100" | findstr "LISTENING")
    $apiPid = ""
    if ($apiListen.Count -gt 0) {
        $parts = ($apiListen[0] -split "\s+") | Where-Object { $_ -ne "" }
        if ($parts.Count -ge 5) { $apiPid = $parts[4] }
    }

    $row = [ordered]@{
        ts = (Get-Date).ToString("o")
        engine_root_count = $roots.Count
        engine_root_pids = (($roots | Select-Object -ExpandProperty ProcessId) -join ",")
        worker_count = $workers.Count
        worker_pids = (($workers | Select-Object -ExpandProperty ProcessId) -join ",")
        guard_count = $guards.Count
        guard_pids = (($guards | Select-Object -ExpandProperty ProcessId) -join ",")
        api_8100_listen = [bool]($apiListen.Count -gt 0)
        api_8100_pid = $apiPid
        runtime_lines = (Get-LineCount $runtimeLog)
        scan_lines = (Get-LineCount $scanLog)
        worker_lines = (Get-LineCount $workerLog)
        runtime_last_ts = (Get-LastTs $runtimeLog)
        scan_last_ts = (Get-LastTs $scanLog)
        worker_last_ts = (Get-LastTs $workerLog)
    }

    Add-Content -Path $outJsonl -Encoding UTF8 -Value ($row | ConvertTo-Json -Compress)
    $samples += 1
    Start-Sleep -Seconds $IntervalSec
}

Set-Content -Path $outStatus -Encoding UTF8 -Value @(
    "COLLECTION_STARTED_AT=$($start.ToString('s'))"
    "COLLECTION_ENDED_AT=$((Get-Date).ToString('s'))"
    "COLLECTION_DURATION_MIN=$DurationMinutes"
    "COLLECTION_INTERVAL_SEC=$IntervalSec"
    "COLLECTION_SAMPLES=$samples"
    "COLLECTION_OUTPUT=$outJsonl"
    "COLLECTION_STATUS=COMPLETED"
)


