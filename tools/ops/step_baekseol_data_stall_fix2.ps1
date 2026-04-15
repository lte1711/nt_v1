$ErrorActionPreference = "Stop"

$projectRoot = "C:\nt_v1"
$configPath = Join-Path $projectRoot "tools\multi5\multi5_config.py"
$bootPath = Join-Path $projectRoot "BOOT\start_engine.ps1"
$restartScript = Join-Path $projectRoot "BOOT\restart_engine.ps1"
$eventLogPath = Join-Path $projectRoot "logs\runtime\profitmax_v1_events.jsonl"
$reportDir = Join-Path $projectRoot "reports\2026-03-28\codex_execution_reports"
$reportPath = Join-Path $reportDir "STEP_BAEKSEOL_DATA_STALL_FIX_2.txt"
$summaryPath = Join-Path $reportDir "STEP_BAEKSEOL_DATA_STALL_FIX_2.summary.json"

New-Item -ItemType Directory -Path $reportDir -Force | Out-Null

$profiles = @(
    [pscustomobject]@{ name = "PROFILE_A"; universe = 40; active = 12; open = 12; scan = 5 },
    [pscustomobject]@{ name = "PROFILE_B"; universe = 20; active = 8; open = 8; scan = 5 },
    [pscustomobject]@{ name = "PROFILE_C"; universe = 10; active = 5; open = 5; scan = 5 }
)

function Set-ValueLine {
    param(
        [string]$Text,
        [string]$Pattern,
        [string]$Replacement
    )
    return [regex]::Replace($Text, $Pattern, $Replacement, [System.Text.RegularExpressions.RegexOptions]::Multiline)
}

function Apply-Profile {
    param(
        [int]$Universe,
        [int]$Active,
        [int]$Open,
        [int]$Scan
    )

    $configText = Get-Content $configPath -Raw
    $configText = Set-ValueLine $configText '^DYNAMIC_UNIVERSE_LIMIT\s*=\s*\d+' "DYNAMIC_UNIVERSE_LIMIT = $Universe"
    $configText = Set-ValueLine $configText '^SCAN_INTERVAL_SEC\s*=\s*\d+' "SCAN_INTERVAL_SEC = $Scan"
    $configText = Set-ValueLine $configText '^MAX_OPEN_POSITION\s*=\s*\d+' "MAX_OPEN_POSITION = $Open"
    $configText = Set-ValueLine $configText '^MAX_SYMBOL_ACTIVE\s*=\s*\d+' "MAX_SYMBOL_ACTIVE = $Active"
    Set-Content -Path $configPath -Value $configText -Encoding UTF8

    $bootText = Get-Content $bootPath -Raw
    $bootText = Set-ValueLine $bootText '(\$scanIntervalSec\s*=\s*)\d+' "`${1}$Scan"
    $bootText = Set-ValueLine $bootText '(\$maxOpenPositions\s*=\s*)\d+' "`${1}$Open"
    $bootText = Set-ValueLine $bootText '(\$maxSymbolActive\s*=\s*)\d+' "`${1}$Active"
    Set-Content -Path $bootPath -Value $bootText -Encoding UTF8
}

function Restart-EngineSafe {
    powershell -ExecutionPolicy Bypass -File $restartScript | Out-Null
    Start-Sleep -Seconds 12
}

function Get-StatObject {
    param([double[]]$Values)
    if (-not $Values -or $Values.Count -eq 0) {
        return $null
    }
    $sorted = @($Values | Sort-Object)
    $count = $sorted.Count
    $avg = ($sorted | Measure-Object -Average).Average
    $median = if ($count % 2 -eq 1) {
        $sorted[[int]($count / 2)]
    } else {
        ($sorted[$count / 2 - 1] + $sorted[$count / 2]) / 2.0
    }
    return [ordered]@{
        count = $count
        avg = [math]::Round($avg, 3)
        median = [math]::Round($median, 3)
        min = [math]::Round($sorted[0], 3)
        max = [math]::Round($sorted[$count - 1], 3)
    }
}

function Measure-Window {
    param([datetimeoffset]$Cutoff)

    $fetchRows = New-Object System.Collections.Generic.List[object]
    $decisionRows = New-Object System.Collections.Generic.List[object]

    Get-Content $eventLogPath | ForEach-Object {
        if (-not $_) { return }
        try { $j = $_ | ConvertFrom-Json } catch { return }
        if (-not $j.ts) { return }
        try { $ts = [datetimeoffset]$j.ts } catch { return }
        if ($ts -lt $Cutoff) { return }

        $event = [string]$j.event_type
        $symbol = [string]$j.symbol
        if (-not $symbol) { return }

        if ($event -eq "DATA_FLOW_TRACE_MARKET") {
            $fetchRows.Add([pscustomobject]@{
                symbol = $symbol
                fetch_delay_ms = [double]$j.payload.fetch_delay_ms
                per_symbol_fetch_ms = [double]$j.payload.per_symbol_fetch_ms
                price_source = [string]$j.payload.price_source
            })
        }
        elseif ($event -eq "DATA_FLOW_TRACE_DECISION") {
            $decisionRows.Add([pscustomobject]@{
                symbol = $symbol
                total_delay_ms = [double]$j.payload.total_delay_ms_to_decision
                per_symbol_total_ms = if ($null -ne $j.payload.per_symbol_total_ms) { [double]$j.payload.per_symbol_total_ms } else { $null }
                loop_total_ms = if ($null -ne $j.payload.loop_total_ms) { [double]$j.payload.loop_total_ms } else { $null }
            })
        }
    }

    $fetchValues = @($fetchRows | ForEach-Object { $_.fetch_delay_ms })
    $decisionValues = @($decisionRows | ForEach-Object { $_.total_delay_ms })
    $localFetchValues = @($fetchRows | ForEach-Object { $_.per_symbol_fetch_ms })
    $localTotalValues = @($decisionRows | Where-Object { $null -ne $_.per_symbol_total_ms } | ForEach-Object { $_.per_symbol_total_ms })
    $loopTotalValues = @($decisionRows | Where-Object { $null -ne $_.loop_total_ms } | ForEach-Object { $_.loop_total_ms })

    $topFetchBySymbol = @(
        $fetchRows |
        Group-Object symbol |
        ForEach-Object {
            $vals = @($_.Group | ForEach-Object { $_.fetch_delay_ms })
            [pscustomobject]@{
                symbol = $_.Name
                avg_fetch_delay_ms = [math]::Round((($vals | Measure-Object -Average).Average), 3)
            }
        } |
        Sort-Object avg_fetch_delay_ms -Descending |
        Select-Object -First 5
    )

    $topLocalTotalBySymbol = @(
        $decisionRows |
        Where-Object { $null -ne $_.per_symbol_total_ms } |
        Group-Object symbol |
        ForEach-Object {
            $vals = @($_.Group | ForEach-Object { $_.per_symbol_total_ms })
            [pscustomobject]@{
                symbol = $_.Name
                avg_per_symbol_total_ms = [math]::Round((($vals | Measure-Object -Average).Average), 3)
            }
        } |
        Sort-Object avg_per_symbol_total_ms -Descending |
        Select-Object -First 5
    )

    return [pscustomobject]@{
        cutoff = $Cutoff.ToString("o")
        fetch = (Get-StatObject $fetchValues)
        total_delay_to_decision = (Get-StatObject $decisionValues)
        per_symbol_fetch = (Get-StatObject $localFetchValues)
        per_symbol_total = (Get-StatObject $localTotalValues)
        loop_total = (Get-StatObject $loopTotalValues)
        fetch_over_1s = @($fetchRows | Where-Object { $_.fetch_delay_ms -gt 1000 }).Count
        fetch_total = $fetchRows.Count
        decision_over_2s = @($decisionRows | Where-Object { $_.total_delay_ms -gt 2000 }).Count
        decision_total_count = $decisionRows.Count
        price_sources = @(
            $fetchRows |
            Group-Object price_source |
            ForEach-Object {
                [pscustomobject]@{ price_source = $_.Name; count = $_.Count }
            }
        )
        top_fetch_by_symbol = $topFetchBySymbol
        top_local_total_by_symbol = $topLocalTotalBySymbol
    }
}

function Run-ProfileMeasure {
    param([pscustomobject]$Profile)

    Apply-Profile -Universe $Profile.universe -Active $Profile.active -Open $Profile.open -Scan $Profile.scan
    Restart-EngineSafe
    $cutoff = [datetimeoffset]::UtcNow
    Start-Sleep -Seconds 80
    $metrics = Measure-Window -Cutoff $cutoff

    return [pscustomobject]@{
        name = $Profile.name
        universe = $Profile.universe
        active = $Profile.active
        open = $Profile.open
        scan = $Profile.scan
        metrics = $metrics
    }
}

$results = New-Object System.Collections.Generic.List[object]
foreach ($profile in $profiles) {
    $results.Add((Run-ProfileMeasure -Profile $profile))
}

$bestProfile = $results |
    Sort-Object @{Expression = { $_.metrics.fetch.avg }}, @{Expression = { $_.metrics.total_delay_to_decision.avg }} |
    Select-Object -First 1

$cadenceYProfile = [pscustomobject]@{
    name = "CADENCE_Y"
    universe = [int]$bestProfile.universe
    active = [int]$bestProfile.active
    open = [int]$bestProfile.open
    scan = 8
}
$cadenceY = Run-ProfileMeasure -Profile $cadenceYProfile

$finalStable = $bestProfile
if (
    $cadenceY.metrics.fetch.avg -lt $bestProfile.metrics.fetch.avg -and
    $cadenceY.metrics.total_delay_to_decision.avg -le $bestProfile.metrics.total_delay_to_decision.avg
) {
    $finalStable = $cadenceY
}

Apply-Profile -Universe $finalStable.universe -Active $finalStable.active -Open $finalStable.open -Scan $finalStable.scan
Restart-EngineSafe

$profileA = $results | Where-Object { $_.name -eq "PROFILE_A" } | Select-Object -First 1
$profileB = $results | Where-Object { $_.name -eq "PROFILE_B" } | Select-Object -First 1
$profileC = $results | Where-Object { $_.name -eq "PROFILE_C" } | Select-Object -First 1

$rootCause = "UNDECIDED"
$action = "REMEASURE_REQUIRED"
if ($profileC.metrics.fetch.avg -le ($profileA.metrics.fetch.avg * 0.85)) {
    $rootCause = "LOCAL_PRESSURE_DOMINANT"
    $action = "PROFILE_DOWNSIZE"
}
elseif ($profileC.metrics.fetch.avg -ge ($profileA.metrics.fetch.avg * 0.95)) {
    $rootCause = "TESTNET_FRESHNESS_CEILING_DOMINANT"
    $action = "ACCEPT_RUNTIME_LIMIT_OR_ENVIRONMENT_REDESIGN"
}

$summary = [ordered]@{
    profile_results = $results
    cadence_y = $cadenceY
    final_stable = $finalStable
    root_cause = $rootCause
    action = $action
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $summaryPath -Encoding UTF8

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("[FACT]")
foreach ($item in $results) {
    $lines.Add("- $($item.name): universe=$($item.universe), active=$($item.active), open=$($item.open), scan=$($item.scan)")
    $lines.Add("  - FETCH_DELAY avg/median/min/max = $($item.metrics.fetch.avg) / $($item.metrics.fetch.median) / $($item.metrics.fetch.min) / $($item.metrics.fetch.max) ms")
    $lines.Add("  - TOTAL_DELAY_TO_DECISION avg/median/min/max = $($item.metrics.total_delay_to_decision.avg) / $($item.metrics.total_delay_to_decision.median) / $($item.metrics.total_delay_to_decision.min) / $($item.metrics.total_delay_to_decision.max) ms")
    $lines.Add("  - per_symbol_fetch_ms avg = $($item.metrics.per_symbol_fetch.avg) ms")
    $lines.Add("  - per_symbol_total_ms avg = $($item.metrics.per_symbol_total.avg) ms")
}
$lines.Add("- CADENCE_Y: universe=$($cadenceY.universe), active=$($cadenceY.active), open=$($cadenceY.open), scan=$($cadenceY.scan)")
$lines.Add("  - FETCH_DELAY avg/median/min/max = $($cadenceY.metrics.fetch.avg) / $($cadenceY.metrics.fetch.median) / $($cadenceY.metrics.fetch.min) / $($cadenceY.metrics.fetch.max) ms")
$lines.Add("  - TOTAL_DELAY_TO_DECISION avg/median/min/max = $($cadenceY.metrics.total_delay_to_decision.avg) / $($cadenceY.metrics.total_delay_to_decision.median) / $($cadenceY.metrics.total_delay_to_decision.min) / $($cadenceY.metrics.total_delay_to_decision.max) ms")
$lines.Add("  - per_symbol_fetch_ms avg = $($cadenceY.metrics.per_symbol_fetch.avg) ms")
$lines.Add("  - per_symbol_total_ms avg = $($cadenceY.metrics.per_symbol_total.avg) ms")
$lines.Add("- Top local per-symbol total candidates from final stable window:")
foreach ($row in $finalStable.metrics.top_local_total_by_symbol) {
    $lines.Add("  - $($row.symbol) = $($row.avg_per_symbol_total_ms) ms")
}
$lines.Add("")
$lines.Add("[CRITICAL_FINDINGS]")
$lines.Add("- root-cause classification = $rootCause")
$lines.Add("- suggested action = $action")
$lines.Add("- final stable runtime profile = universe=$($finalStable.universe), active=$($finalStable.active), open=$($finalStable.open), scan=$($finalStable.scan)")
$lines.Add("")
$lines.Add("[INFERENCE]")
$lines.Add("- Remaining stall classification was decided from profile-downsize and cadence comparison, plus local per-symbol timing.")
$lines.Add("")
$lines.Add("[FINAL_JUDGMENT]")
$lines.Add("- NEXT_STABLE_RUNTIME_PROFILE = universe=$($finalStable.universe), active=$($finalStable.active), open=$($finalStable.open), scan=$($finalStable.scan)")
$lines.Add("- ROOT_CAUSE = $rootCause")
$lines.Add("- ACTION = $action")

Set-Content -Path $reportPath -Value $lines -Encoding UTF8
Write-Output "REPORT_PATH=$reportPath"
Write-Output "SUMMARY_PATH=$summaryPath"

