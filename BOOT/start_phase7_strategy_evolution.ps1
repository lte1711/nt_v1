param(
    [string]$ProjectRoot = "C:\nt_v1",
    [string]$OutDir = "C:\nt_v1\reports\phase7_strategy"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$engine = "C:\nt_v1\BOOT\phase7_strategy_evolution_engine.py"

if (-not (Test-Path $python)) {
    throw "PROJECT_VENV_PYTHON_NOT_FOUND: $python"
}
if (-not (Test-Path $engine)) {
    throw "PHASE7_ENGINE_NOT_FOUND: $engine"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

& $python $engine --runtime-dir (Join-Path $ProjectRoot "logs\runtime") --out-dir $OutDir

$summaryPath = Join-Path $OutDir "nt_phase7_honey_summary.txt"
if (Test-Path $summaryPath) {
    Write-Output "PHASE7_SUMMARY_PATH=$summaryPath"
    Get-Content $summaryPath
}



