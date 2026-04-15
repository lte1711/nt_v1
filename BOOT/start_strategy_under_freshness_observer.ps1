$scriptPath = "C:\nt_v1\tools\ops\observe_strategy_under_freshness_constraint.ps1"
Start-Process powershell -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $scriptPath
) -WindowStyle Hidden

