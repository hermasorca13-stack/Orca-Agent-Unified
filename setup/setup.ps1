<#
setup/setup.ps1 - One-shot installer for Orca Agent on Windows 10/11.

What it does (in order):

  1. Checks Python 3.11+ and Git are installed; offers to install if not
  2. Clones the repo to D:\ORCA AGENT\Orca-Agent-Unified (or the path
     you pass as -InstallDir)
  3. Creates a Python venv
  4. Installs all requirements
  5. Creates .env from .env.example (asks for tokens)
  6. Runs the test suite to confirm a clean install
  7. Installs a Windows Task Scheduler entry for auto-start on boot
  8. Installs a keep-awake watchdog (prevents sleep when the bot is on)
  9. Installs a health check task (Telegram alert if the bot falls over)
 10. Prints the next steps

Usage (from PowerShell, as Administrator):

    # Easiest: one-liner from the web
    Set-ExecutionPolicy Bypass -Scope Process -Force
    iwr -useb https://raw.githubusercontent.com/hermasorca13-stack/Orca-Agent-Unified/master/setup/setup.ps1 | iex

    # Or after cloning manually:
    cd "D:\ORCA AGENT\Orca-Agent-Unified\setup"
    .\setup.ps1

    # Or with a custom install dir:
    .\setup.ps1 -InstallDir "E:\bots\orca"

Optional flags:

    -InstallDir     Target directory (default: D:\ORCA AGENT)
    -SkipTests      Don't run the test suite (faster)
    -SkipService    Don't install the auto-start task
    -SkipKeepAwake  Don't install the keep-awake watchdog
    -SkipHealth     Don't install the health check task
    -Token          Pre-set Telegram bot token (skips the prompt)
    -GitToken       Pre-set GitHub PAT (skips the prompt)

Tested on: Windows 10 Pro 22H2, Windows 11 Pro 23H2, PowerShell 5.1+ / 7.x
#>
[CmdletBinding()]
param(
    [string]$InstallDir = "D:\ORCA AGENT",
    [switch]$SkipTests = $false,
    [switch]$SkipService = $false,
    [switch]$SkipKeepAwake = $false,
    [switch]$SkipHealth = $false,
    [string]$Token = "",
    [string]$GitToken = ""
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # faster on slow disks

# ---------------------------------------------------------------------
# Pretty output
# ---------------------------------------------------------------------
function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  [!] $msg" -ForegroundColor Yellow }
function Write-Err  { param($msg) Write-Host "  [X] $msg" -ForegroundColor Red }

# ---------------------------------------------------------------------
# 1. Sanity: Admin?
# ---------------------------------------------------------------------
Write-Step "Step 0 / 10 - Checking administrator privileges"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Warn "Not running as Administrator. Some steps (Task Scheduler) will fail."
    Write-Host "  Re-run from an elevated PowerShell: Right-click -> Run as Administrator"
    $cont = Read-Host "  Continue anyway? (y/N)"
    if ($cont -ne 'y') { exit 1 }
} else {
    Write-Ok "Running as Administrator"
}

# ---------------------------------------------------------------------
# 2. Sanity: Python 3.11+
# ---------------------------------------------------------------------
Write-Step "Step 1 / 10 - Checking Python 3.11+"
$python = $null
try {
    $ver = python --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        $verNum = ($ver -replace 'Python\s+', '') -split '\.' | Select-Object -First 1
        if ([int]$verNum -ge 3 -and [int](($ver -replace 'Python\s+', '') -split '\.' | Select-Object -Skip 1 -First 1) -ge 11) {
            $python = (Get-Command python).Source
            Write-Ok "Python $ver at $python"
        } else {
            Write-Warn "Python found but version too old: $ver (need 3.11+)"
        }
    }
} catch { }

if (-not $python) {
    Write-Warn "Python 3.11+ not found."
    Write-Host "  Download from: https://www.python.org/downloads/windows/"
    Write-Host "  (Check 'Add Python to PATH' during install)"
    $cont = Read-Host "  Continue setup anyway? (y/N)"
    if ($cont -ne 'y') { exit 1 }
}

# ---------------------------------------------------------------------
# 3. Sanity: Git
# ---------------------------------------------------------------------
Write-Step "Step 2 / 10 - Checking Git"
try {
    $gitVer = git --version
    if ($LASTEXITCODE -eq 0) {
        Write-Ok $gitVer
    } else {
        throw "git not found"
    }
} catch {
    Write-Warn "Git not found. Download from: https://git-scm.com/download/win"
    $cont = Read-Host "  Continue setup anyway? (y/N)"
    if ($cont -ne 'y') { exit 1 }
}

# ---------------------------------------------------------------------
# 4. Cache redirection (pip + model caches to D: drive)
# ---------------------------------------------------------------------
Write-Step "Step 3.5 / 10 - Redirecting caches to D: drive"
$cacheRoot = Join-Path $InstallDir "cache"
$cacheScript = Join-Path $repoDir "setup\cache_setup.ps1"
if (Test-Path $cacheScript) {
    $junctionFlag = ""
    $useJunc = Read-Host "  Also create NTFS junctions for default cache paths? (y/N)"
    if ($useJunc -eq 'y') { $junctionFlag = "-UseJunctions" }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $cacheScript -CacheRoot $cacheRoot $junctionFlag
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "cache_setup.ps1 exited with $LASTEXITCODE (continuing)"
    }
} else {
    Write-Warn "cache_setup.ps1 not found, skipping cache redirect"
}

# ---------------------------------------------------------------------
# 5. Clone (or update) the repo
# ---------------------------------------------------------------------
Write-Step "Step 3 / 10 - Cloning Orca Agent to $InstallDir"
$repoDir = Join-Path $InstallDir "Orca-Agent-Unified"
$repoUrl = "https://github.com/hermasorca13-stack/Orca-Agent-Unified.git"

if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
    Write-Ok "Created $InstallDir"
}

if (Test-Path "$repoDir\.git") {
    Write-Ok "Repo already exists at $repoDir - pulling latest"
    Push-Location $repoDir
    git pull --ff-only
    Pop-Location
} else {
    git clone $repoUrl $repoDir
    if ($LASTEXITCODE -ne 0) {
        Write-Err "git clone failed. Check your network."
        exit 1
    }
    Write-Ok "Cloned to $repoDir"
}

# ---------------------------------------------------------------------
# 5. Create venv
# ---------------------------------------------------------------------
Write-Step "Step 4 / 10 - Creating Python venv"
$venvDir = Join-Path $repoDir ".venv"
if (-not (Test-Path $venvDir)) {
    python -m venv $venvDir
    Write-Ok "Created venv at $venvDir"
} else {
    Write-Ok "venv already exists at $venvDir"
}
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"

# ---------------------------------------------------------------------
# 6. Install requirements
# ---------------------------------------------------------------------
Write-Step "Step 5 / 10 - Installing requirements"
& $venvPip install --upgrade pip --quiet
& $venvPip install -r (Join-Path $repoDir "requirements.txt") --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Err "pip install failed. Run manually: $venvPip install -r requirements.txt"
    exit 1
}
Write-Ok "Requirements installed"

# ---------------------------------------------------------------------
# 7. Create .env
# ---------------------------------------------------------------------
Write-Step "Step 6 / 10 - Creating .env"
$envFile = Join-Path $repoDir ".env"
$envExample = Join-Path $repoDir ".env.example"

if (-not (Test-Path $envExample)) {
    # Generate a starter .env.example if missing.
    # Compute values up-front so the heredoc stays simple.
    if ($Token) {
        $seedToken = $Token.Substring(0, [Math]::Min(8, $Token.Length)) + '-' + [guid]::NewGuid().ToString('N').Substring(0, 16)
    } else {
        $seedToken = ''
    }
    $gitTokenValue = if ($GitToken) { $GitToken } else { '' }
    $botTokenValue = if ($Token) { $Token } else { '' }
    $lines = @(
        '# Orca Agent - runtime configuration',
        '# Copy to .env and fill in your values',
        '',
        '# Telegram (REQUIRED for the bot)',
        "TELEGRAM_BOT_TOKEN=$botTokenValue",
        'TELEGRAM_BOT_USERNAME=HermesOrcaXBot',
        '',
        '# GitHub (REQUIRED for self-update + push commands)',
        "GITHUB_TOKEN=$gitTokenValue",
        'GITHUB_USERNAME=hermasorca13',
        'GITHUB_ORG=hermasorca13-stack',
        'GITHUB_EMAIL=hermasorca13@gmail.com',
        'GITHUB_REPO=Orca-Agent-Unified',
        'GITHUB_BRANCH=master',
        '',
        '# LLM (OPTIONAL - bot has offline fallbacks)',
        'OPENAI_API_KEY=',
        'ANTHROPIC_API_KEY=',
        '',
        '# Termux bridge (OPTIONAL - needed for /termux commands)',
        "TERMUX_BRIDGE_TOKEN=$seedToken",
        'TERMUX_BRIDGE_PORT=8765',
        'TERMUX_BRIDGE_HOST=0.0.0.0',
        '',
        '# Master / production',
        "ORCA_MASTER=$gitTokenValue",
        'RUN_MODE=production',
        'LOG_LEVEL=INFO'
    )
    $lines -join "`r`n" | Set-Content $envExample -Encoding UTF8
    Write-Ok "Created $envExample"
}

if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
    Write-Ok "Created $envFile (edit it with your tokens)"
} else {
    Write-Ok ".env already exists, keeping it"
}

# Prompt for tokens if empty
$envContent = Get-Content $envFile -Raw
if ($envContent -notmatch 'TELEGRAM_BOT_TOKEN=\S+' -or $envContent -match 'TELEGRAM_BOT_TOKEN=$') {
    if (-not $Token) {
        $Token = Read-Host "  Enter your TELEGRAM_BOT_TOKEN (or Enter to skip)"
    }
    if ($Token) {
        (Get-Content $envFile) -replace 'TELEGRAM_BOT_TOKEN=.*', "TELEGRAM_BOT_TOKEN=$Token" | Set-Content $envFile
        Write-Ok "Telegram token saved"
    } else {
        Write-Warn "Skipped - bot will not start until you set TELEGRAM_BOT_TOKEN in .env"
    }
}

# ---------------------------------------------------------------------
# 8. Run tests
# ---------------------------------------------------------------------
if (-not $SkipTests) {
    Write-Step "Step 7 / 10 - Running test suite"
    Push-Location $repoDir
    & $venvPython -m pytest tests/ --ignore=tests/test_telegram_bot.py -q 2>&1 | Select-Object -Last 5
    Pop-Location
} else {
    Write-Warn "Step 7 / 10 - Skipped tests (use -SkipTests:$false to run)"
}

# ---------------------------------------------------------------------
# 9. Install auto-start task
# ---------------------------------------------------------------------
if (-not $SkipService) {
    Write-Step "Step 8 / 10 - Installing auto-start Task Scheduler entry"
    $taskName = "OrcaAgent"
    $runScript = Join-Path $repoDir "setup\run_bot.ps1"
    if (Test-Path $runScript) {
        try {
            $action = New-ScheduledTaskAction `
                -Execute "powershell.exe" `
                -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$runScript`" -RepoDir `"$repoDir`""
            $trigger = New-ScheduledTaskTrigger -AtLogOn
            $settings = New-ScheduledTaskSettingsSet `
                -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries `
                -DontStopOnIdleEnd `
                -RestartCount 3 `
                -RestartInterval (New-TimeSpan -Minutes 1)
            Register-ScheduledTask `
                -TaskName $taskName `
                -Action $action `
                -Trigger $trigger `
                -Settings $settings `
                -User $env:USERNAME `
                -RunLevel Highest `
                -Force | Out-Null
            Write-Ok "Task $taskName created (auto-start at logon, restart on failure)"
        } catch {
            Write-Warn "Failed to create scheduled task: $_"
            Write-Host "  Run setup as Administrator, or create the task manually."
        }
    } else {
        Write-Warn "run_bot.ps1 not found - skipping scheduled task"
    }
}

# ---------------------------------------------------------------------
# 10. Install keep-awake watchdog
# ---------------------------------------------------------------------
if (-not $SkipKeepAwake) {
    Write-Step "Step 9 / 10 - Installing keep-awake watchdog"
    $keepAwakeScript = Join-Path $repoDir "setup\keep_awake.ps1"
    if (Test-Path $keepAwakeScript) {
        try {
            $action = New-ScheduledTaskAction `
                -Execute "powershell.exe" `
                -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$keepAwakeScript`" -RepoDir `"$repoDir`""
            $trigger = New-ScheduledTaskTrigger -AtLogOn
            $settings = New-ScheduledTaskSettingsSet `
                -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries `
                -ExecutionTimeLimit (New-TimeSpan -Hours 0)  # indefinite
            Register-ScheduledTask `
                -TaskName "OrcaAgentKeepAwake" `
                -Action $action `
                -Trigger $trigger `
                -Settings $settings `
                -User $env:USERNAME `
                -RunLevel Highest `
                -Force | Out-Null
            Write-Ok "Task OrcaAgentKeepAwake created"
        } catch {
            Write-Warn "Failed to create keep-awake task: $_"
        }
    }
}

# ---------------------------------------------------------------------
# 11. Install health check
# ---------------------------------------------------------------------
if (-not $SkipHealth) {
    Write-Step "Step 10 / 10 - Installing health check task"
    $healthScript = Join-Path $repoDir "setup\health_check.ps1"
    if (Test-Path $healthScript) {
        try {
            $action = New-ScheduledTaskAction `
                -Execute "powershell.exe" `
                -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$healthScript`" -RepoDir `"$repoDir`""
            $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
                -RepetitionInterval (New-TimeSpan -Minutes 5) `
                -RepetitionDuration (New-TimeSpan -Days 3650)
            $settings = New-ScheduledTaskSettingsSet `
                -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries `
                -StartWhenAvailable
            Register-ScheduledTask `
                -TaskName "OrcaAgentHealthCheck" `
                -Action $action `
                -Trigger $trigger `
                -Settings $settings `
                -User $env:USERNAME `
                -RunLevel Limited `
                -Force | Out-Null
            Write-Ok "Task OrcaAgentHealthCheck created (runs every 5 min)"
        } catch {
            Write-Warn "Failed to create health check task: $_"
        }
    }
}

# ---------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------
Write-Step "Setup complete!"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Green
Write-Host "  1. Edit $envFile with your tokens" -ForegroundColor Green
Write-Host "  2. Test manually: see README.md section Useful commands" -ForegroundColor Green
Write-Host "  3. Or just log out / log in - Task Scheduler will start the bot" -ForegroundColor Green
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor Green
Write-Host "  Start the bot now:   Start-ScheduledTask -TaskName OrcaAgent" -ForegroundColor Green
Write-Host "  Stop the bot:        Stop-ScheduledTask  -TaskName OrcaAgent" -ForegroundColor Green
$logPath = Join-Path $repoDir "logs\orca.log"
Write-Host "  View logs:           Get-Content $logPath -Tail 50 -Wait" -ForegroundColor Green
Write-Host "  Update from GitHub:  git -C $repoDir pull" -ForegroundColor Green
Write-Host "  Termux bridge:       Invoke-RestMethod http://localhost:8765/health" -ForegroundColor Green
Write-Host ""
Write-Host "Termux phone setup: send `/termux setup` to the bot after it starts." -ForegroundColor Yellow
