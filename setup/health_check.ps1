<#
setup/health_check.ps1 - Periodic health check + Telegram alert on failure.

Runs every 5 minutes (via Task Scheduler). It:
  1. Checks the OrcaAgent task is in 'Running' state
  2. Pings the Termux bridge at http://localhost:8765/health
  3. If anything is wrong, sends a Telegram message to the admin
     using the bot token from .env

The Telegram admin chat_id is read from .env as ORCA_ADMIN_CHAT_ID.
If unset, the script silently logs the failure (no spam).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$RepoDir
)

$ErrorActionPreference = 'Stop'

# Load .env
$envFile = Join-Path $RepoDir ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') {
            $name = $matches[1]
            $value = $matches[2].Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

$logDir = Join-Path $RepoDir "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "health.log"

function Write-Log {
    param($msg, $level = "INFO")
    $line = "{0} {1} {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $level, $msg
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Send-Telegram {
    param($message)
    if (-not $env:TELEGRAM_BOT_TOKEN -or -not $env:ORCA_ADMIN_CHAT_ID) {
        Write-Log "Telegram alert skipped (TELEGRAM_BOT_TOKEN or ORCA_ADMIN_CHAT_ID not set)" "WARN"
        return
    }
    try {
        $url = "https://api.telegram.org/bot$($env:TELEGRAM_BOT_TOKEN)/sendMessage"
        $body = @{
            chat_id = $env:ORCA_ADMIN_CHAT_ID
            text = $message
            parse_mode = "Markdown"
        } | ConvertTo-Json -Compress
        Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json" -Body $body -TimeoutSec 10 | Out-Null
        Write-Log "Telegram alert sent"
    } catch {
        Write-Log "Telegram alert failed: $_" "WARN"
    }
}

$problems = @()

# 1. Check the OrcaAgent task
$task = Get-ScheduledTask -TaskName "OrcaAgent" -ErrorAction SilentlyContinue
if (-not $task) {
    $problems += "[X] Scheduled task 'OrcaAgent' not found (run setup.ps1)"
} elseif ($task.State -ne "Running") {
    $problems += "[!] Task 'OrcaAgent' state: $($task.State)"
}

# 2. Check Termux bridge
$bridgePort = if ($env:TERMUX_BRIDGE_PORT) { $env:TERMUX_BRIDGE_PORT } else { "8765" }
try {
    $r = Invoke-RestMethod -Uri "http://localhost:$bridgePort/health" -TimeoutSec 3
    if (-not $r.ok) {
        $problems += "[!] Termux bridge returned ok=false"
    }
} catch {
    $problems += "[X] Termux bridge unreachable on :$bridgePort ($($_.Exception.Message))"
}

# 3. Check disk space on D:
$drive = Get-PSDrive -Name "D" -ErrorAction SilentlyContinue
if ($drive -and $drive.Free -lt 1GB) {
    $problems += "[!] D: drive low space: $([math]::Round($drive.Free/1MB,0)) MB free"
}

# 4. Check the most recent orca.log for errors
$orcaLog = Join-Path $logDir "orca.log"
if (Test-Path $orcaLog) {
    $recentErrors = Get-Content $orcaLog -Tail 200 | Select-String -Pattern "ERROR|CRITICAL|Traceback" | Select-Object -Last 3
    if ($recentErrors) {
        $problems += "[!] Recent errors in orca.log:`n$($recentErrors -join "`n")"
    }
}

# Report
if ($problems.Count -gt 0) {
    $msg = "Orca Agent Health Check found $($problems.Count) issue(s):`n`n" + ($problems -join "`n`n")
    Write-Log $msg "WARN"
    Send-Telegram $msg
} else {
    Write-Log "All checks passed (task running, bridge reachable, disk OK)"
}
