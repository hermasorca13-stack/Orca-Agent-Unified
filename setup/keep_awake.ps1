<#
setup/keep_awake.ps1 - Prevent Windows from sleeping while the bot runs.

Strategy: we use the Win32 SetThreadExecutionState API. The bot is
"running" when the scheduled task OrcaAgent has the python process
active. We:
  1. Poll the OrcaAgent task status every 60s
  2. If it's running, call SetThreadExecutionState with ES_SYSTEM_REQUIRED
  3. If it's not running, release the lock so the laptop can sleep

This way, the laptop only stays awake when the bot is actually working.
The watchdog itself runs as a long-lived Task Scheduler entry at logon.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$RepoDir
)

$ErrorActionPreference = 'Continue'

Add-Type -Namespace Win32 -Name Functions -MemberDefinition @'
    [System.Runtime.InteropServices.DllImport("kernel32.dll", CharSet = System.Runtime.InteropServices.CharSet.Auto, SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
'@

$ES_CONTINUOUS      = [uint32]0x80000000
$ES_SYSTEM_REQUIRED  = [uint32]0x00000001
$ES_AWAYMODE_REQUIRED= [uint32]0x00000040
$ES_DISPLAY_REQUIRED = [uint32]0x00000002

function Set-Awake {
    param([bool]$on)
    if ($on) {
        [Win32.Functions]::SetThreadExecutionState(
            $ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_AWAYMODE_REQUIRED
        ) | Out-Null
    } else {
        [Win32.Functions]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
    }
}

$logDir = Join-Path $RepoDir "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "keep_awake.log"

function Write-Log {
    param($msg)
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Write-Log "Orca keep-awake watchdog started (PID=$PID)"

$lastState = $false
try {
    while ($true) {
        # Check if the OrcaAgent task is running
        $running = $false
        try {
            $info = Get-ScheduledTask -TaskName "OrcaAgent" -ErrorAction SilentlyContinue
            if ($info) {
                $running = ($info.State -eq "Running")
            }
        } catch { }

        # Also check the python process directly (in case the task is
        # queued but not actually running yet)
        if (-not $running) {
            $procs = Get-Process python -ErrorAction SilentlyContinue
            if ($procs) { $running = $true }
        }

        if ($running -ne $lastState) {
            Set-Awake -on $running
            $state = if ($running) { "AWAKE" } else { "allow sleep" }
            Write-Log "Bot status changed: $state"
            $lastState = $running
        }

        Start-Sleep -Seconds 60
    }
} finally {
    # Always release the sleep lock on exit
    Set-Awake -on $false
    Write-Log "Keep-awake watchdog exiting - releasing sleep lock"
}
