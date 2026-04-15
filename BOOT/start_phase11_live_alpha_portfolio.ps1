param(
    [string]$ProjectRoot = "C:\nt_v1",
    [string]$Phase10Dir = "C:\nt_v1\reports\phase10_live_alpha_selection",
    [string]$OutDir = "C:\nt_v1\reports\phase11_live_alpha_portfolio"
)

$ErrorActionPreference = "Stop"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$engine = "C:\nt_v1\BOOT\phase11_live_alpha_portfolio_engine.py"

if (-not (Test-Path $python)) { throw "PROJECT_VENV_PYTHON_NOT_FOUND: $python" }
if (-not (Test-Path $engine)) { throw "PHASE11_ENGINE_NOT_FOUND: $engine" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
& $python $engine --phase10-scoreboard (Join-Path $Phase10Dir "phase10_live_alpha_scoreboard.json") --out-dir $OutDir

$summaryPath = Join-Path $OutDir "nt_phase11_honey_summary.txt"
if (Test-Path $summaryPath) {
    Write-Output "PHASE11_SUMMARY_PATH=$summaryPath"
    Get-Content $summaryPath
}




