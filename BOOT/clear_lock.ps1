$lockFiles = @(
    'C:\nt_v1\logs\runtime\watchdog.lock',
    'C:\nt_v1\logs\runtime\engine.pid'
)
foreach ($f in $lockFiles) {
    if (Test-Path $f) { Remove-Item $f -Force }
}

