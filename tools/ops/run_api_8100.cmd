@echo off
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
set "PYTHONPATH=%PROJECT_ROOT%\src"
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
  if not "%%~A"=="" if not "%%~A:~0,1%%"=="#" set "%%~A=%%~B"
)
"%PROJECT_ROOT%\.venv\Scripts\python.exe" -m uvicorn next_trade.api.app:app --host 127.0.0.1 --port 8100
