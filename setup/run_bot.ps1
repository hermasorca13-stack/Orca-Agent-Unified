<#
setup/run_bot.ps1 - Run the Orca Agent bot as a long-lived process.

This script is invoked by the OrcaAgent scheduled task. It:
  1. Activates the venv
  2. Loads the .env file
  3. Starts the Telegram bot (or the FastAPI server, or both)
  4. Logs everything to logs\orca.log
  5. Restarts on crash (Task Scheduler handles the auto-restart)

Usage (manually):
    powershell -NoProfile -File setup\run_bot.ps1 -RepoDir "D:\ORCA AGENT\Orca-Agent-Unified"
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$RepoDir
)

$ErrorActionPreference = 'Stop'
Set-Location $RepoDir

# Log rotation: keep last 5 files
$logDir = Join-Path $RepoDir "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "orca.log"
$archiveLog = Join-Path $logDir "orca.{0:yyyy-MM-dd-HH-mm-ss}.log" -f (Get-Date)
if ((Test-Path $logFile) -and ((Get-Item $logFile).Length -gt 5MB)) {
    Move-Item $logFile $archiveLog -Force
    # Keep only 5 archives
    Get-ChildItem (Join-Path $logDir "orca.*.log") |
        Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 5 |
        Remove-Item -Force
}

function Write-Log {
    param($msg, $level = "INFO")
    $line = "{0} {1} {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $level, $msg
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

Write-Log "===== Orca Agent starting ====="
Write-Log "Repo: $RepoDir"
Write-Log "User: $env:USERNAME"
Write-Log "PowerShell: $($PSVersionTable.PSVersion)"

# Load .env into current process
$envFile = Join-Path $RepoDir ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') {
            $name = $matches[1]
            $value = $matches[2].Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
            Write-Log "  env: $name = $($value.Substring(0, [Math]::Min(20, $value.Length)))..."
        }
    }
} else {
    Write-Log ".env not found at $envFile" "WARN"
}

# Load cache env vars (redirects pip/HF/torch caches to D: drive)
$cacheEnvFile = Join-Path $RepoDir "cache\cache_env.ps1"
if (Test-Path $cacheEnvFile) {
    . $cacheEnvFile
    Write-Log "Loaded cache env from $cacheEnvFile"
} else {
    Write-Log "cache_env.ps1 not found at $cacheEnvFile (run setup\cache_setup.ps1)" "WARN"
}

# Check required tokens
if (-not $env:TELEGRAM_BOT_TOKEN) {
    Write-Log "TELEGRAM_BOT_TOKEN is empty. Bot will start but won't connect." "WARN"
}

# Activate venv
$venvActivate = Join-Path $RepoDir ".venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
    Write-Log "Activated venv: $venvActivate"
} else {
    Write-Log "venv not found at $venvActivate. Run setup.ps1 first." "ERROR"
    exit 1
}

# Decide what to run
# Priority: TELEGRAM_BRIDGE_ONLY=1 -> only termux server
#           TERMUX_BRIDGE_ONLY=1 -> only termux server
#           default -> full bot (which lazy-imports the bridge when /termux is called)
$runBridgeOnly = $env:TERMUX_BRIDGE_ONLY -eq '1' -or $env:TELEGRAM_BRIDGE_ONLY -eq '1'

if ($runBridgeOnly) {
    Write-Log "Starting Termux bridge only (TERMUX_BRIDGE_ONLY=1)"
    & python -m tools.termux_server
} else {
    Write-Log "Starting Telegram bot + lazy Termux bridge"
    # The bot is in telegram_bot/bot.py
    $botPath = Join-Path $RepoDir "telegram_bot\bot.py"
    if (Test-Path $botPath) {
        & python $botPath
    } else {
        Write-Log "telegram_bot\bot.py not found" "ERROR"
        exit 1
    }
}

Write-Log "===== Orca Agent exited ====="
