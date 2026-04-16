@echo off
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"
set "PYTHONPATH=%PROJECT_ROOT%\src"
set "API_PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if exist "%PROJECT_ROOT%\.venv\pyvenv.cfg" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%PROJECT_ROOT%\.venv\pyvenv.cfg") do (
    if /I "%%~A"=="home " set "VENV_HOME=%%~B"
    if /I "%%~A"=="home" set "VENV_HOME=%%~B"
  )
)
if defined VENV_HOME (
  set "VENV_HOME=%VENV_HOME: =%"
  if exist "%VENV_HOME%\python.exe" set "API_PYTHON=%VENV_HOME%\python.exe"
)
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
  if not "%%~A"=="" if not "%%~A:~0,1%%"=="#" set "%%~A=%%~B"
)
"%API_PYTHON%" "%PROJECT_ROOT%\tools\ops\run_api_8100.py"
