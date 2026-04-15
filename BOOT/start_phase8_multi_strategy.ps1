param(
    [string]$Phase7Dir = "C:\nt_v1\reports\phase7_strategy",
    [string]$OutDir = "C:\nt_v1\reports\phase8_multi_strategy",
    [string]$ProjectRoot = "C:\nt_v1"
)

$ErrorActionPreference = "Stop"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$script = "C:\nt_v1\BOOT\phase8_multi_strategy_intelligence.py"

if (-not (Test-Path $python)) { throw "PROJECT_VENV_PYTHON_NOT_FOUND: $python" }
if (-not (Test-Path $script)) { throw "PHASE8_SCRIPT_NOT_FOUND: $script" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

& $python $script --phase7-dir $Phase7Dir --out-dir $OutDir

$summary = Join-Path $OutDir "nt_phase8_honey_summary.txt"
if (Test-Path $summary) {
    Write-Output "PHASE8_SUMMARY_PATH=$summary"
    Get-Content $summary
}



