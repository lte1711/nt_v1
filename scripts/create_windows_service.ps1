# NEXT-TRADE Windows 서비스 생성 스크립트
# 모든 서버를 Windows 서비스로 등록

param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status
)

# 관리자 권한 확인
function Test-Administrator {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (!(Test-Administrator)) {
    Write-Host "This script requires administrator privileges." -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator." -ForegroundColor Red
    exit 1
}

# 변수 설정
$PROJECT_ROOT = "C:\nt_v1"
$VENV_PYTHON = "$PROJECT_ROOT\.venv\Scripts\python.exe"
$SERVICE_DIR = "$PROJECT_ROOT\services"

# 서비스 디렉토리 생성
if (!(Test-Path $SERVICE_DIR)) {
    New-Item -ItemType Directory -Path $SERVICE_DIR -Force
}

# 서비스 정의
$SERVICES = @{
    "NextTradeAPI" = @{
        "DisplayName" = "NEXT-TRADE API Server"
        "Description" = "NEXT-TRADE API Server for trading operations"
        "Executable" = $VENV_PYTHON
        "Arguments" = "-m uvicorn next_trade.api.app:app --host 127.0.0.1 --port 8100"
        "WorkingDirectory" = $PROJECT_ROOT
        "Environment" = "PYTHONPATH=$PROJECT_ROOT\src"
        "Dependencies" = @()
    }
    "NextTradeDashboard" = @{
        "DisplayName" = "NEXT-TRADE Dashboard Server"
        "Description" = "NEXT-TRADE Dashboard Server for monitoring"
        "Executable" = $VENV_PYTHON
        "Arguments" = "tools\dashboard\multi5_dashboard_server.py"
        "WorkingDirectory" = $PROJECT_ROOT
        "Environment" = ""
        "Dependencies" = @("NextTradeAPI")
    }
    "NextTradeEngine" = @{
        "DisplayName" = "NEXT-TRADE Engine Wrapper"
        "Description" = "NEXT-TRADE Engine Wrapper for trading execution"
        "Executable" = $VENV_PYTHON
        "Arguments" = "tools\multi5\run_multi5_engine.py --runtime-minutes 1440 --scan-interval-sec 5"
        "WorkingDirectory" = $PROJECT_ROOT
        "Environment" = ""
        "Dependencies" = @("NextTradeAPI", "NextTradeDashboard")
    }
}

function New-ServiceWrapper {
    param(
        [string]$ServiceName,
        [string]$DisplayName,
        [string]$Description,
        [string]$Executable,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$Environment,
        [array]$Dependencies
    )
    
    $wrapperScript = @"
# NEXT-TRADE Service Wrapper for $ServiceName
# Generated automatically by create_windows_service.ps1

`$PROJECT_ROOT = "$PROJECT_ROOT"
`$VENV_PYTHON = "$VENV_PYTHON"
`$SERVICE_NAME = "$ServiceName"
`$LOG_DIR = "$PROJECT_ROOT\logs\services"

# 로그 디렉토리 생성
if (!(Test-Path `$LOG_DIR)) {
    New-Item -ItemType Directory -Path `$LOG_DIR -Force
}

`$logFile = "`$LOG_DIR\`$SERVICE_NAME.log"

function Write-ServiceLog {
    param(`$message)
    `$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "`$timestamp [`$SERVICE_NAME] `$message" | Out-File -FilePath `$logFile -Append -Encoding UTF8
}

try {
    Write-ServiceLog "Service starting..."
    Write-ServiceLog "Executable: `$VENV_PYTHON"
    Write-ServiceLog "Arguments: $Arguments"
    Write-ServiceLog "Working Directory: `$PROJECT_ROOT"
    
    # 환경 변수 설정
    if ("$Environment") {
        `$envPair = "$Environment".Split('=')
        [System.Environment]::SetEnvironmentVariable(`$envPair[0], `$envPair[1])
        Write-ServiceLog "Environment variable set: `$(`$envPair[0])=`$(`$envPair[1])"
    }
    
    # 프로세스 시작
    `$startInfo = New-Object System.Diagnostics.ProcessStartInfo
    `$startInfo.FileName = `$VENV_PYTHON
    `$startInfo.Arguments = "$Arguments"
    `$startInfo.WorkingDirectory = `$PROJECT_ROOT
    `$startInfo.UseShellExecute = `$false
    `$startInfo.RedirectStandardOutput = `$true
    `$startInfo.RedirectStandardError = `$true
    `$startInfo.CreateNoWindow = `$true
    
    `$process = [System.Diagnostics.Process]::Start(`$startInfo)
    
    Write-ServiceLog "Process started with PID: `$(`$process.Id)"
    
    # 프로세스가 종료될 때까지 대기
    `$process.WaitForExit()
    
    Write-ServiceLog "Process exited with code: `$(`$process.ExitCode)"
    
} catch {
    Write-ServiceLog "Error: `$(`$_.Exception.Message)"
    Write-ServiceLog "Stack Trace: `$(`$_.Exception.StackTrace)"
    exit 1
}
"@
    
    $wrapperPath = "$SERVICE_DIR\$ServiceName.ps1"
    $wrapperScript | Out-File -FilePath $wrapperPath -Encoding UTF8
    
    return $wrapperPath
}

function Install-Service {
    param($ServiceKey, $ServiceConfig)
    
    $serviceName = $ServiceKey
    $wrapperPath = New-ServiceWrapper @ServiceConfig
    
    Write-Host "Installing service: $serviceName" -ForegroundColor Green
    
    try {
        # 기존 서비스가 있으면 삭제
        $existingService = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($existingService) {
            Write-Host "Removing existing service: $serviceName" -ForegroundColor Yellow
            Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
            Remove-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
        
        # 새 서비스 생성
        $serviceArgs = @{
            Name = $serviceName
            DisplayName = $ServiceConfig["DisplayName"]
            Description = $ServiceConfig["Description"]
            BinaryPathName = "powershell.exe -ExecutionPolicy Bypass -File `"$wrapperPath`""
            StartupType = "Automatic"
            DependsOn = $ServiceConfig["Dependencies"]
        }
        
        New-Service @serviceArgs
        
        Write-Host "Service installed successfully: $serviceName" -ForegroundColor Green
        Write-Host "Wrapper script: $wrapperPath" -ForegroundColor Cyan
        
    } catch {
        Write-Host "Failed to install service $serviceName`: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Uninstall-Service {
    param($ServiceKey)
    
    $serviceName = $ServiceKey
    
    Write-Host "Uninstalling service: $serviceName" -ForegroundColor Yellow
    
    try {
        $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
        if ($service) {
            Stop-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
            Remove-Service -Name $serviceName -Force -ErrorAction SilentlyContinue
            Write-Host "Service uninstalled successfully: $serviceName" -ForegroundColor Green
        } else {
            Write-Host "Service not found: $serviceName" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Failed to uninstall service $serviceName`: $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Show-ServiceStatus {
    Write-Host "=== NEXT-TRADE Windows Services Status ===" -ForegroundColor Cyan
    Write-Host ""
    
    foreach ($key in $SERVICES.Keys) {
        $serviceConfig = $SERVICES[$key]
        $serviceName = $key
        
        try {
            $service = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
            if ($service) {
                $statusColor = switch ($service.Status) {
                    "Running" { "Green" }
                    "Stopped" { "Red" }
                    "Paused" { "Yellow" }
                    default { "Gray" }
                }
                Write-Host "$($serviceConfig['DisplayName']):" -ForegroundColor White -NoNewline
                Write-Host " $($service.Status)" -ForegroundColor $statusColor
                Write-Host "  Service Name: $serviceName" -ForegroundColor Gray
                Write-Host "  Display Name: $($serviceConfig['DisplayName'])" -ForegroundColor Gray
            } else {
                Write-Host "$($serviceConfig['DisplayName']):" -ForegroundColor White -NoNewline
                Write-Host " NOT INSTALLED" -ForegroundColor Red
            }
        } catch {
            Write-Host "$($serviceConfig['DisplayName']):" -ForegroundColor White -NoNewline
            Write-Host " ERROR" -ForegroundColor Red
            Write-Host "  Error: $($_.Exception.Message)" -ForegroundColor Red
        }
        Write-Host ""
    }
}

# 메인 로직
if ($Install) {
    Write-Host "Installing NEXT-TRADE Windows Services..." -ForegroundColor Yellow
    Write-Host ""
    
    foreach ($key in $SERVICES.Keys) {
        Install-Service $key $SERVICES[$key]
        Start-Sleep -Seconds 1
    }
    
    Write-Host ""
    Write-Host "All services installed." -ForegroundColor Green
    Write-Host ""
    Write-Host "To start services:" -ForegroundColor Cyan
    Write-Host "  Start-Service NextTradeAPI" -ForegroundColor Gray
    Write-Host "  Start-Service NextTradeDashboard" -ForegroundColor Gray
    Write-Host "  Start-Service NextTradeEngine" -ForegroundColor Gray
    Write-Host ""
    Write-Host "To check status:" -ForegroundColor Cyan
    Write-Host "  Get-Service NextTrade*" -ForegroundColor Gray
    
} elseif ($Uninstall) {
    Write-Host "Uninstalling NEXT-TRADE Windows Services..." -ForegroundColor Yellow
    Write-Host ""
    
    # 의존성 순서대로 삭제 (Engine -> Dashboard -> API)
    $uninstallOrder = @("NextTradeEngine", "NextTradeDashboard", "NextTradeAPI")
    foreach ($serviceName in $uninstallOrder) {
        if ($SERVICES.ContainsKey($serviceName)) {
            Uninstall-Service $serviceName
            Start-Sleep -Seconds 1
        }
    }
    
    Write-Host ""
    Write-Host "All services uninstalled." -ForegroundColor Green
    
} elseif ($Status) {
    Show-ServiceStatus
    
} else {
    Write-Host "Usage:" -ForegroundColor Cyan
    Write-Host "  Install services:   .\create_windows_service.ps1 -Install" -ForegroundColor Gray
    Write-Host "  Uninstall services: .\create_windows_service.ps1 -Uninstall" -ForegroundColor Gray
    Write-Host "  Check status:      .\create_windows_service.ps1 -Status" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Note: This script requires administrator privileges." -ForegroundColor Yellow
}

