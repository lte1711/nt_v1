# NEXT-TRADE 백그라운드 서비스 시작 스크립트
# 모든 서버를 윈도우 백그라운드에서 실행

param(
    [switch]$Stop,
    [switch]$Status
)

# 프로젝트 루트 경로
$PROJECT_ROOT = Split-Path -Parent $PSScriptRoot
$VENV_PYTHON = "$PROJECT_ROOT\.venv\Scripts\python.exe"
$LOG_DIR = "$PROJECT_ROOT\logs\background_services"

# 로그 디렉토리 생성
if (!(Test-Path $LOG_DIR)) {
    New-Item -ItemType Directory -Path $LOG_DIR -Force
}

# 서비스 정의
$SERVICES = @{
    "API_SERVER" = @{
        "Name" = "NEXT-TRADE API Server"
        "Command" = "uvicorn next_trade.api.app:app --host 127.0.0.1 --port 8100"
        "Port" = 8100
        "Log" = "$LOG_DIR\api_server.log"
        "PID" = "$LOG_DIR\api_server.pid"
        "Env" = "PYTHONPATH=$PROJECT_ROOT\src"
    }
    "DASHBOARD_SERVER" = @{
        "Name" = "NEXT-TRADE Dashboard Server"
        "Command" = "tools\dashboard\multi5_dashboard_server.py"
        "Port" = 8788
        "Log" = "$LOG_DIR\dashboard_server.log"
        "PID" = "$LOG_DIR\dashboard_server.pid"
    }
    "ENGINE_WRAPPER" = @{
        "Name" = "NEXT-TRADE Engine Wrapper"
        "Command" = "tools\multi5\run_multi5_engine.py --runtime-minutes 1440 --scan-interval-sec 5"
        "Log" = "$LOG_DIR\engine_wrapper.log"
        "PID" = "$LOG_DIR\engine_wrapper.pid"
    }
}

function Get-ServiceStatus {
    param($ServiceKey)
    
    $service = $SERVICES[$ServiceKey]
    $pidFile = $service["PID"]
    
    if (Test-Path $pidFile) {
        $pid = Get-Content $pidFile
        $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
        
        if ($process) {
            return @{
                "Status" = "RUNNING"
                "PID" = $pid
                "ProcessName" = $process.ProcessName
                "StartTime" = $process.StartTime
            }
        } else {
            # PID 파일은 있지만 프로세스는 없는 경우
            Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
            return @{
                "Status" = "STOPPED"
                "PID" = $null
                "ProcessName" = $null
                "StartTime" = $null
            }
        }
    } else {
        return @{
            "Status" = "STOPPED"
            "PID" = $null
            "ProcessName" = $null
            "StartTime" = $null
        }
    }
}

function Start-BackgroundService {
    param($ServiceKey)
    
    $service = $SERVICES[$ServiceKey]
    $logFile = $service["Log"]
    $pidFile = $service["PID"]
    
    Write-Host "Starting $($service['Name'])..." -ForegroundColor Green
    
    # 이미 실행 중인지 확인
    $status = Get-ServiceStatus $ServiceKey
    if ($status["Status"] -eq "RUNNING") {
        Write-Host "Service is already running (PID: $($status['PID']))" -ForegroundColor Yellow
        return
    }
    
    # 환경 변수 설정
    $envVars = @{}
    if ($service["Env"]) {
        $envPair = $service["Env"].Split('=')
        $envVars[$envPair[0]] = $envPair[1]
    }
    
    # 백그라운드에서 프로세스 시작
    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $VENV_PYTHON
    $startInfo.Arguments = $service["Command"]
    $startInfo.WorkingDirectory = $PROJECT_ROOT
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true
    
    # 환경 변수 설정
    foreach ($key in $envVars.Keys) {
        $startInfo.EnvironmentVariables[$key] = $envVars[$key]
    }
    
    $process = [System.Diagnostics.Process]::Start($startInfo)
    
    # PID 파일 저장
    $process.Id | Out-File -FilePath $pidFile -Encoding UTF8
    
    # 로그 파일에 출력 리디렉션
    Start-Job -ScriptBlock {
        param($ProcessId, $LogFile)
        $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($process) {
            $process.WaitForExit()
            "Process exited with code: $($process.ExitCode)" | Out-File -FilePath $LogFile -Append -Encoding UTF8
        }
    } -ArgumentList $process.Id, $logFile
    
    Write-Host "Service started with PID: $($process.Id)" -ForegroundColor Green
    Write-Host "Log file: $logFile" -ForegroundColor Cyan
    Write-Host "PID file: $pidFile" -ForegroundColor Cyan
}

function Stop-BackgroundService {
    param($ServiceKey)
    
    $service = $SERVICES[$ServiceKey]
    $pidFile = $service["PID"]
    
    Write-Host "Stopping $($service['Name'])..." -ForegroundColor Red
    
    $status = Get-ServiceStatus $ServiceKey
    if ($status["Status"] -eq "RUNNING") {
        try {
            Stop-Process -Id $status["PID"] -Force -ErrorAction Stop
            Write-Host "Service stopped (PID: $($status['PID']))" -ForegroundColor Green
        } catch {
            Write-Host "Failed to stop service: $($_.Exception.Message)" -ForegroundColor Red
        }
    } else {
        Write-Host "Service is not running" -ForegroundColor Yellow
    }
    
    # PID 파일 삭제
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
}

function Show-ServiceStatus {
    Write-Host "=== NEXT-TRADE Background Services Status ===" -ForegroundColor Cyan
    Write-Host ""
    
    foreach ($key in $SERVICES.Keys) {
        $service = $SERVICES[$key]
        $status = Get-ServiceStatus $key
        
        $statusColor = if ($status["Status"] -eq "RUNNING") { "Green" } else { "Red" }
        Write-Host "$($service['Name']):" -ForegroundColor White -NoNewline
        Write-Host " $($status['Status'])" -ForegroundColor $statusColor
        
        if ($status["Status"] -eq "RUNNING") {
            Write-Host "  PID: $($status['PID'])" -ForegroundColor Gray
            Write-Host "  Started: $($status['StartTime'])" -ForegroundColor Gray
            Write-Host "  Port: $($service['Port'])" -ForegroundColor Gray
        }
        Write-Host ""
    }
    
    # 포트 상태 확인
    Write-Host "=== Port Status ===" -ForegroundColor Cyan
    foreach ($key in $SERVICES.Keys) {
        $service = $SERVICES[$key]
        if ($service["Port"]) {
            try {
                $connection = Test-NetConnection -ComputerName "127.0.0.1" -Port $service["Port"] -WarningAction SilentlyContinue
                $portStatus = if ($connection.TcpTestSucceeded) { "LISTENING" } else { "CLOSED" }
                $portColor = if ($connection.TcpTestSucceeded) { "Green" } else { "Red" }
                Write-Host "Port $($service['Port']): $portStatus" -ForegroundColor $portColor
            } catch {
                Write-Host "Port $($service['Port']): CLOSED" -ForegroundColor Red
            }
        }
    }
}

# 메인 로직
if ($Stop) {
    Write-Host "Stopping all background services..." -ForegroundColor Yellow
    foreach ($key in $SERVICES.Keys) {
        Stop-BackgroundService $key
    }
    Write-Host "All services stopped." -ForegroundColor Green
} elseif ($Status) {
    Show-ServiceStatus
} else {
    Write-Host "Starting all background services..." -ForegroundColor Yellow
    foreach ($key in $SERVICES.Keys) {
        Start-BackgroundService $key
        Start-Sleep -Seconds 2  # 서비스 시작 간격
    }
    Write-Host "All services started." -ForegroundColor Green
    Write-Host ""
    Write-Host "To check status: .\scripts\start_background_services.ps1 -Status" -ForegroundColor Cyan
    Write-Host "To stop all services: .\scripts\start_background_services.ps1 -Stop" -ForegroundColor Cyan
    Write-Host ""
    Show-ServiceStatus
}
