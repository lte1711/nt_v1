param(
    [int]$DurationMinutes = 65,
    [int]$IntervalMinutes = 30
)

$ErrorActionPreference = "Stop"

function Get-KstNow {
    $utc = (Get-Date).ToUniversalTime()
    return [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId($utc, "Korea Standard Time")
}

function Get-ReportDir {
    $root = "C:\nt_v1\reports"
    $dateFolder = (Get-KstNow).ToString("yyyy-MM-dd")
    $dir = Join-Path $root "$dateFolder\honey_execution_reports"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-PythonSnapshot {
    $rows = Get-Process python -ErrorAction SilentlyContinue |
        Select-Object ProcessName, Id, CPU, WS, PM, StartTime |
        Sort-Object Id

    $totalWs = 0L
    $totalPm = 0L
    foreach ($row in $rows) {
        $totalWs += [int64]$row.WS
        $totalPm += [int64]$row.PM
    }

    return [pscustomobject]@{
        ts = (Get-Date).ToUniversalTime().ToString("o")
        python_process_count = @($rows).Count
        total_ws = $totalWs
        total_pm = $totalPm
        top_rows = @($rows | Sort-Object WS -Descending | Select-Object -First 12)
        all_rows = @($rows)
    }
}

$reportDir = Get-ReportDir
$historyPath = Join-Path $reportDir "step65_memory_profile_history.jsonl"
$latestPath = Join-Path $reportDir "step65_memory_profile_latest.json"

$startedAt = Get-Date
$deadline = $startedAt.AddMinutes($DurationMinutes)
$sampleIndex = 0

while ((Get-Date) -le $deadline) {
    $sample = Get-PythonSnapshot
    $sampleIndex += 1
    $payload = [ordered]@{
        ts = $sample.ts
        sample_index = $sampleIndex
        duration_minutes = $DurationMinutes
        interval_minutes = $IntervalMinutes
        python_process_count = $sample.python_process_count
        total_ws = $sample.total_ws
        total_pm = $sample.total_pm
        top_rows = $sample.top_rows
        all_rows = $sample.all_rows
    }
    $json = $payload | ConvertTo-Json -Depth 6 -Compress
    Add-Content -Path $historyPath -Value $json -Encoding UTF8
    Set-Content -Path $latestPath -Value ($payload | ConvertTo-Json -Depth 6) -Encoding UTF8

    if ((Get-Date).AddMinutes($IntervalMinutes) -gt $deadline) {
        break
    }
    Start-Sleep -Seconds ($IntervalMinutes * 60)
}


