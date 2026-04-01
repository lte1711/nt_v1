param(
    [int]$PollSec = 20,
    [int]$TargetClosedTrades = 3
)

$ErrorActionPreference = "Continue"
. "C:\next-trade-ver1.0\BOOT\report_path_resolver.ps1"

$baseDir = "C:\next-trade-ver1.0\reports\phase13_same_window_pf"
$closeoutPath = Join-Path $baseDir "phase13b_same_window_session_closeout.txt"
$candidatePath = Join-Path $baseDir "phase13b_same_window_trade_candidate_report.txt"
$statusPath = Join-Path $baseDir "phase13b_same_window_status.txt"
$alertPath = Join-Path $baseDir "phase13b_goal_reached_alert.txt"
$masterPath = Resolve-NtRoleReportFile -RoleFolder "honey_execution_reports" -FileName "nt_phase13_baekseol_status_report_master.txt" -EnsureParent
$logPath = Join-Path $baseDir "phase13b_goal_notifier.log"

New-Item -ItemType Directory -Force -Path $baseDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $masterPath -Parent) | Out-Null

function Parse-KvFile([string]$path) {
    $map = @{}
    if (-not (Test-Path $path)) { return $map }
    foreach ($line in Get-Content $path) {
        if ($line -match '^(.*?)=(.*)$') {
            $map[$matches[1].Trim()] = $matches[2].Trim()
        }
    }
    return $map
}

function Log([string]$line) {
    Add-Content -Path $logPath -Encoding UTF8 -Value ("{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss K"), $line)
}

function Send-WindowsAlert([string]$title, [string]$message) {
    $sentAny = $false
    try {
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        $escapedTitle = [System.Security.SecurityElement]::Escape($title)
        $escapedMsg = [System.Security.SecurityElement]::Escape($message)
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$escapedTitle</text><text>$escapedMsg</text></binding></visual></toast>")
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("PowerShell")
        $notifier.Show($toast)
        Log "ALERT_CHANNEL=WinRT.Toast"
        $sentAny = $true
    } catch {
        Log ("ALERT_CHANNEL=WinRT_FAILED reason=" + $_.Exception.Message)
    }
    try {
        if (Get-Command New-BurntToastNotification -ErrorAction SilentlyContinue) {
            New-BurntToastNotification -Text $title, $message | Out-Null
            Log "ALERT_CHANNEL=BurntToast"
            $sentAny = $true
        }
    } catch {
        Log ("ALERT_CHANNEL=BurntToast_FAILED reason=" + $_.Exception.Message)
    }
    try {
        $wshell = New-Object -ComObject Wscript.Shell
        # Always show popup as guaranteed foreground fallback.
        [void]$wshell.Popup($message, 25, $title, 0x40)
        Log "ALERT_CHANNEL=Wscript.Popup"
        $sentAny = $true
        try {
            & msg * "$title`n$message" | Out-Null
            Log "ALERT_CHANNEL=MSG.EXE"
            $sentAny = $true
        } catch {
            Log ("ALERT_CHANNEL=MSG_FAILED reason=" + $_.Exception.Message)
        }
    } catch {
        Log ("ALERT_CHANNEL=Popup_FAILED reason=" + $_.Exception.Message)
    }
    if (-not $sentAny) {
        Log "ALERT_CHANNEL=NONE"
    }
}

function Write-MasterReport([hashtable]$close, [hashtable]$cand, [hashtable]$status) {
    $sessionId = $cand["SESSION_ID"]
    if (-not $sessionId) { $sessionId = $status["SESSION_ID"] }
    $block = @()
    $block += ""
    $block += "SESSION_HISTORY_BLOCK"
    $block += ("TS_KST=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss K"))
    $block += ("SESSION_ID=" + $sessionId)
    $block += ("WINDOW_START_UTC=" + $status["OBS_START_UTC"])
    $block += ("WINDOW_END_UTC=" + $status["OBS_END_UTC"])
    $block += ("CLOSED_TRADES=" + $close["CLOSED_TRADES_WITHIN_WINDOW"])
    if ($close.ContainsKey("CLOSED_TRADES_PREV_WINDOW")) {
        $block += ("CLOSED_TRADES_PREV_WINDOW=" + $close["CLOSED_TRADES_PREV_WINDOW"])
    }
    if ($close.ContainsKey("CLOSED_TRADES_TWO_WINDOW_TOTAL")) {
        $block += ("CLOSED_TRADES_TWO_WINDOW_TOTAL=" + $close["CLOSED_TRADES_TWO_WINDOW_TOTAL"])
    }
    $block += ("POSITION_CLOSE_EVENT_DELTA=" + $close["POSITION_CLOSE_EVENT_DELTA"])
    $block += ("SESSION_RESULT=" + $close["SESSION_RESULT"])
    Add-Content -Path $masterPath -Encoding UTF8 -Value $block
}

Log "GOAL_NOTIFIER_START"
$lastSeen = ""

while ($true) {
    if (-not (Test-Path $closeoutPath)) {
        Start-Sleep -Seconds $PollSec
        continue
    }

    $raw = Get-Content $closeoutPath -Raw
    if ($raw -eq $lastSeen) {
        Start-Sleep -Seconds $PollSec
        continue
    }
    $lastSeen = $raw

    $close = Parse-KvFile $closeoutPath
    $cand = Parse-KvFile $candidatePath
    $status = Parse-KvFile $statusPath

    $closed = 0
    try { $closed = [int]$close["CLOSED_TRADES_WITHIN_WINDOW"] } catch { $closed = 0 }
    $result = [string]$close["SESSION_RESULT"]
    $twoWindow = 0
    try { $twoWindow = [int]$close["CLOSED_TRADES_TWO_WINDOW_TOTAL"] } catch { $twoWindow = 0 }
    $sessionId = [string]$cand["SESSION_ID"]
    if (-not $sessionId) { $sessionId = [string]$status["SESSION_ID"] }

    Log ("SEEN_SESSION session_id={0} closed={1} two_window_total={2} result={3}" -f $sessionId, $closed, $twoWindow, $result)
    Write-MasterReport -close $close -cand $cand -status $status

    if ($closed -ge $TargetClosedTrades -or $twoWindow -ge $TargetClosedTrades -or $result -eq "PF_RECALC_ELIGIBLE") {
        $title = "NEXT-TRADE PHASE13B 紐⑺몴 ?ъ꽦"
        $msg = ("SESSION={0}`nCLOSED_TRADES={1}`nTWO_WINDOW_TOTAL={2}`nRESULT={3}`nNEXT=NT-PHASE13D(CANDY)" -f $sessionId, $closed, $twoWindow, $result)
        @(
            "PHASE13B_GOAL_REACHED=YES"
            ("ALERT_TIME_KST=" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss K"))
            ("SESSION_ID=" + $sessionId)
            ("CLOSED_TRADES_WITHIN_WINDOW=" + $closed)
            ("CLOSED_TRADES_TWO_WINDOW_TOTAL=" + $twoWindow)
            ("SESSION_RESULT=" + $result)
            "NEXT_GATE=NT-PHASE13D"
            "NEXT_ROLE=CANDY"
        ) | Set-Content -Path $alertPath -Encoding UTF8
        Send-WindowsAlert -title $title -message $msg
        Log ("GOAL_REACHED session_id={0} closed={1}" -f $sessionId, $closed)
        break
    }

    Start-Sleep -Seconds $PollSec
}

Log "GOAL_NOTIFIER_END"


