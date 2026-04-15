$scriptPath = "C:\nt_v1\tools\ops\observe_validation_only.ps1"
Start-Process powershell -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $scriptPath
) -WindowStyle Hidden

