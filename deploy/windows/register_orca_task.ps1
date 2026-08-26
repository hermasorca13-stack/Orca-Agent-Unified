param(
    [string]$TaskName = 'ORCA-Max-Mouny',
    [string]$IntervalSeconds = '10'
)
$ErrorActionPreference = 'Stop'
$Root = if ($env:ORCA_ROOT) { $env:ORCA_ROOT } else { Join-Path $HOME 'ORCA-Max-Mouny' }
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$LogDir = Join-Path $Root 'data\orca_max_mouny\logs'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
if (-not (Test-Path $Python)) { throw "ORCA venv not found at $Python." }

$action = New-ScheduledTaskAction -Execute $Python -Argument '-m trading_bot.daemon --symbols BTC/USDT --interval 10' -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Days 365) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType InteractiveToken -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Registered $TaskName for $env:USERNAME. It runs in the user's keyring context and remains in Paper mode by default."
