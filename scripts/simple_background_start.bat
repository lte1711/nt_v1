@echo off
REM NEXT-TRADE 간단 백그라운드 시작 스크립트
REM 모든 서버를 백그라운드에서 시작

echo Starting NEXT-TRADE Services in Background...
echo.

REM 프로젝트 루트로 이동
cd /d "C:\nt_v1"

REM 환경 변수 설정
set PYTHONPATH=C:\nt_v1\src

echo Starting API Server (Port 8100)...
start /B "" ".venv\Scripts\python.exe" -m uvicorn next_trade.api.app:app --host 127.0.0.1 --port 8100
timeout /t 3 /nobreak >nul

echo Starting Dashboard Server (Port 8788)...
start /B "" ".venv\Scripts\python.exe" "tools\dashboard\multi5_dashboard_server.py"
timeout /t 3 /nobreak >nul

echo Starting Engine Wrapper...
start /B "" ".venv\Scripts\python.exe" "tools\multi5\run_multi5_engine.py" --runtime-minutes 1440 --scan-interval-sec 5
timeout /t 3 /nobreak >nul

echo.
echo All services started in background!
echo.
echo To check status:
echo   - API Server: http://127.0.0.1:8100/api/v1/ops/health
echo   - Dashboard: http://127.0.0.1:8788/api/runtime
echo.
echo To stop all services, run: taskkill /f /im python.exe
echo.

pause

