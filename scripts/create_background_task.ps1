# NEXT-TRADE 백그라운드 태스크 생성 스크립트
# Windows 태스크 스케줄러에 등록하여 부팅 시 자동 실행

param(
    [switch]$Create,
    [switch]$Delete,
    [switch]$List
)

# 변수 설정
$TASK_NAME = "NEXT-TRADE_Background_Services"
$TASK_DESCRIPTION = "NEXT-TRADE Trading System Background Services"
$SCRIPT_PATH = "C:\next-trade-ver1.0\scripts\start_services_background.bat"
$PROJECT_ROOT = "C:\next-trade-ver1.0"

function Create-BackgroundTask {
    Write-Host "Creating Windows Task Scheduler entry for NEXT-TRADE..." -ForegroundColor Green
    
    # 기존 태스크 삭제
    try {
        Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host "Removed existing task: $TASK_NAME" -ForegroundColor Yellow
    } catch {
        # 태스크가 없는 경우 무시
    }
    
    # 태스크 액션 생성
    $action = New-ScheduledTaskAction -Execute $SCRIPT_PATH -WorkingDirectory $PROJECT_ROOT
    
    # 트리거 설정 (시스템 시작 시)
    $trigger = New-ScheduledTaskTrigger -AtStartup
    
    # 설정
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Days 1)
    
    # 보안 설정 (최고 권한으로 실행)
    $principal = New-ScheduledTaskPrincipal -UserId "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest
    
    # 태스크 등록
    try {
        Register-ScheduledTask -TaskName $TASK_NAME -Description $TASK_DESCRIPTION -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force
        Write-Host "Task created successfully: $TASK_NAME" -ForegroundColor Green
        Write-Host "The services will start automatically on Windows startup." -ForegroundColor Cyan
    } catch {
        Write-Host "Failed to create task: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
    
    return $true
}

function Delete-BackgroundTask {
    Write-Host "Deleting Windows Task Scheduler entry for NEXT-TRADE..." -ForegroundColor Red
    
    try {
        Unregister-ScheduledTask -TaskName $TASK_NAME -Confirm:$false
        Write-Host "Task deleted successfully: $TASK_NAME" -ForegroundColor Green
    } catch {
        Write-Host "Task not found or failed to delete: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}

function List-BackgroundTasks {
    Write-Host "=== Scheduled Tasks for NEXT-TRADE ===" -ForegroundColor Cyan
    Write-Host ""
    
    try {
        $task = Get-ScheduledTask -TaskName $TASK_NAME -ErrorAction SilentlyContinue
        if ($task) {
            Write-Host "Task Name: $($task.TaskName)" -ForegroundColor Green
            Write-Host "Description: $($task.Description)" -ForegroundColor Gray
            Write-Host "Status: $($task.State)" -ForegroundColor White
            Write-Host "Action: $($task.Actions.Execute)" -ForegroundColor Gray
            Write-Host "Trigger: $($task.Triggers)" -ForegroundColor Gray
            Write-Host "Last Run Time: $($task.LastRunTime)" -ForegroundColor Gray
            Write-Host "Next Run Time: $($task.NextRunTime)" -ForegroundColor Gray
        } else {
            Write-Host "No scheduled task found for NEXT-TRADE" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Error listing tasks: $($_.Exception.Message)" -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "=== Current Running Services ===" -ForegroundColor Cyan
    Write-Host ""
    
    try {
        $processes = Get-Process | Where-Object {$_.ProcessName -eq "python"}
        if ($processes) {
            $processes | Select-Object ProcessName, Id, StartTime | Format-Table -AutoSize
        } else {
            Write-Host "No Python processes running" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Error checking processes: $($_.Exception.Message)" -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "=== Port Status ===" -ForegroundColor Cyan
    Write-Host ""
    
    $ports = @(8100, 8788)
    foreach ($port in $ports) {
        try {
            $connection = Test-NetConnection -ComputerName "127.0.0.1" -Port $port -WarningAction SilentlyContinue
            $portStatus = if ($connection.TcpTestSucceeded) { "LISTENING" } else { "CLOSED" }
            $portColor = if ($connection.TcpTestSucceeded) { "Green" } else { "Red" }
            Write-Host "Port $port`: $portStatus" -ForegroundColor $portColor
        } catch {
            Write-Host "Port $port`: CLOSED" -ForegroundColor Red
        }
    }
}

# 메인 로직
if ($Create) {
    if (Create-BackgroundTask) {
        Write-Host ""
        Write-Host "To manually start services now:" -ForegroundColor Cyan
        Write-Host "  .\scripts\start_services_background.bat" -ForegroundColor Gray
        Write-Host ""
        Write-Host "To check task status:" -ForegroundColor Cyan
        Write-Host "  .\scripts\create_background_task.ps1 -List" -ForegroundColor Gray
    }
} elseif ($Delete) {
    Delete-BackgroundTask
} elseif ($List) {
    List-BackgroundTasks
} else {
    Write-Host "Usage:" -ForegroundColor Cyan
    Write-Host "  Create task:     .\create_background_task.ps1 -Create" -ForegroundColor Gray
    Write-Host "  Delete task:     .\create_background_task.ps1 -Delete" -ForegroundColor Gray
    Write-Host "  List tasks:      .\create_background_task.ps1 -List" -ForegroundColor Gray
    Write-Host ""
    Write-Host "This script creates a Windows Task Scheduler entry that:" -ForegroundColor Yellow
    Write-Host "- Runs on Windows startup" -ForegroundColor Gray
    Write-Host "- Starts all NEXT-TRADE services in background" -ForegroundColor Gray
    Write-Host "- Continues running even after user logout" -ForegroundColor Gray
    Write-Host "- Runs with SYSTEM privileges for maximum stability" -ForegroundColor Gray
}
