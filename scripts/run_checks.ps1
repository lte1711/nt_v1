$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Virtualenv python not found: $pythonExe"
}

Push-Location $projectRoot
try {
    & $pythonExe -m py_compile `
        src\next_trade\api\app.py `
        src\next_trade\api\routes_v1_ops.py `
        src\next_trade\api\routes_v1_investor.py `
        tools\dashboard\multi5_dashboard_server.py `
        tools\ops\profitmax_v1_runner.py
    if ($LASTEXITCODE -ne 0) {
        throw "py_compile failed"
    }

    & $pythonExe -m unittest discover -s tests -q
    if ($LASTEXITCODE -ne 0) {
        throw "unit tests failed"
    }
}
finally {
    Pop-Location
}

Write-Host "Project checks passed." -ForegroundColor Green
