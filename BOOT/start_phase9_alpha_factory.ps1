param(
    [string]$ProjectRoot = "C:\nt_v1",
    [string]$RuntimeDir = "C:\nt_v1\logs\runtime",
    [string]$Phase7Dir = "C:\nt_v1\reports\phase7_strategy",
    [string]$OutDir = "C:\nt_v1\reports\phase9_alpha_factory"
)

$ErrorActionPreference = "Stop"

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$pipeline = "C:\nt_v1\BOOT\phase9_alpha_factory_pipeline.py"

if (-not (Test-Path $python)) { throw "PROJECT_VENV_PYTHON_NOT_FOUND: $python" }
if (-not (Test-Path $pipeline)) { throw "PHASE9_PIPELINE_NOT_FOUND: $pipeline" }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

& $python $pipeline --runtime-dir $RuntimeDir --phase7-dir $Phase7Dir --out-dir $OutDir

$summaryPath = Join-Path $OutDir "nt_phase9_honey_summary.txt"
if (Test-Path $summaryPath) {
    Write-Output "PHASE9_SUMMARY_PATH=$summaryPath"
    Get-Content $summaryPath
}




