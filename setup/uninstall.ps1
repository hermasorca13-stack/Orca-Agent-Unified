<#
setup/uninstall.ps1 - Clean removal of the Orca Agent setup.

Removes:
  - Scheduled tasks: OrcaAgent, OrcaAgentKeepAwake, OrcaAgentHealthCheck
  - The .venv directory
  - Logs
  - The cloned repo (optional, with -RemoveRepo)

Keeps:
  - .env (your tokens) - re-run setup.ps1 to recover
  - termux_bridge.json (phone config)

Usage:
    powershell -NoProfile -ExecutionPolicy Bypass -File setup\uninstall.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File setup\uninstall.ps1 -RemoveRepo  # also delete the repo
#>
[CmdletBinding()]
param(
    [string]$RepoDir = "D:\ORCA AGENT\Orca-Agent-Unified",
    [switch]$RemoveRepo = $false
)

$ErrorActionPreference = 'Continue'

function Write-Step { param($msg) Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  [!] $msg" -ForegroundColor Yellow }

Write-Step "Uninstalling Orca Agent from $RepoDir"

# 1. Stop and remove scheduled tasks
$taskNames = @("OrcaAgent", "OrcaAgentKeepAwake", "OrcaAgentHealthCheck")
foreach ($n in $taskNames) {
    $t = Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
    if ($t) {
        Stop-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $n -Confirm:$false
        Write-Ok "Removed scheduled task '$n'"
    }
}

# 2. Remove venv
$venv = Join-Path $RepoDir ".venv"
if (Test-Path $venv) {
    Remove-Item $venv -Recurse -Force
    Write-Ok "Removed .venv"
}

# 3. Remove logs (but keep .env + termux_bridge.json)
$logDir = Join-Path $RepoDir "logs"
if (Test-Path $logDir) {
    Remove-Item $logDir -Recurse -Force
    Write-Ok "Removed logs/"
}

# 4. Optional: remove the entire repo
if ($RemoveRepo -and (Test-Path $RepoDir)) {
    $confirm = Read-Host "  Really delete $RepoDir? Type 'yes' to confirm"
    if ($confirm -eq "yes") {
        Remove-Item $RepoDir -Recurse -Force
        Write-Ok "Removed $RepoDir"
    } else {
        Write-Warn "Skipped repo removal"
    }
}

Write-Host ""
Write-Host "Done. To reinstall, re-run setup.ps1" -ForegroundColor Green
