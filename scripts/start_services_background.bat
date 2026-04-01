@echo off
REM NEXT-TRADE 백그라운드 서비스 시작 스크립트
REM 모든 서버를 윈도우 백그라운드에서 실행

title NEXT-TRADE Background Services

echo ====================================
echo NEXT-TRADE Background Services
echo ====================================
echo.

REM 프로젝트 루트로 이동
cd /d "C:\next-trade-ver1.0"

REM 환경 변수 설정
set PYTHONPATH=C:\next-trade-ver1.0\src

echo [1/3] Starting API Server (Port 8100)...
start /MIN "NEXT-TRADE API Server" cmd /c "cd /d C:\next-trade-ver1.0 && set PYTHONPATH=C:\next-trade-ver1.0\src && .venv\Scripts\python.exe -m uvicorn next_trade.api.app:app --host 127.0.0.1 --port 8100"
timeout /t 5 /nobreak >nul

echo [2/3] Starting Dashboard Server (Port 8788)...
start /MIN "NEXT-TRADE Dashboard" cmd /c "cd /d C:\next-trade-ver1.0 && .venv\Scripts\python.exe tools\dashboard\multi5_dashboard_server.py"
timeout /t 5 /nobreak >nul

echo [3/3] Starting Engine Wrapper...
start /MIN "NEXT-TRADE Engine" cmd /c "cd /d C:\next-trade-ver1.0 && .venv\Scripts\python.exe tools\multi5\run_multi5_engine.py --runtime-minutes 1440 --scan-interval-sec 5"
timeout /t 5 /nobreak >nul

echo.
echo ====================================
echo All services started in background!
echo ====================================
echo.
echo Services Status:
echo - API Server: http://127.0.0.1:8100/api/v1/ops/health
echo - Dashboard:  http://127.0.0.1:8788/api/runtime
echo.
echo To check running processes:
echo tasklist | findstr python
echo.
echo To stop all services:
echo taskkill /f /im python.exe
echo.
echo Services will continue running after closing this window.
echo.

REM 최종 상태 확인
echo Checking service status...
timeout /t 10 /nobreak >nul

echo.
echo [API Server Status]
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8100/api/v1/ops/health' -UseBasicParsing -TimeoutSec 5; Write-Host 'Status: OK (StatusCode:' $response.StatusCode ')' } catch { Write-Host 'Status: FAILED -' $_.Exception.Message }"

echo.
echo [Dashboard Server Status]
powershell -Command "try { $response = Invoke-WebRequest -Uri 'http://127.0.0.1:8788/api/runtime' -UseBasicParsing -TimeoutSec 5; Write-Host 'Status: OK (StatusCode:' $response.StatusCode ')' } catch { Write-Host 'Status: FAILED -' $_.Exception.Message }"

echo.
echo [Running Python Processes]
powershell -Command "Get-Process | Where-Object {$_.ProcessName -eq 'python'} | Select-Object ProcessName, Id, StartTime | Format-Table -AutoSize"

echo.
echo ====================================
echo Background services setup complete!
echo ====================================
echo.
pause
