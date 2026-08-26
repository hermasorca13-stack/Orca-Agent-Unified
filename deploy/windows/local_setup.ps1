param(
    [Parameter(Mandatory=$true)] [ValidateSet('set','list','delete')] [string]$Action,
    [string]$Exchange = 'binance',
    [switch]$Sandbox
)
$ErrorActionPreference = 'Stop'
$Root = if ($env:ORCA_ROOT) { $env:ORCA_ROOT } else { Join-Path $HOME 'ORCA-Max-Mouny' }
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw "ORCA venv not found at $Python. Run install_orca.ps1 first." }

if ($Action -eq 'list') {
    & $Python -m trading_bot.cli.local_setup list
    exit $LASTEXITCODE
}
if ($Action -eq 'delete') {
    & $Python -m trading_bot.cli.local_setup delete $Exchange
    exit $LASTEXITCODE
}

$arguments = @('-m', 'trading_bot.cli.local_setup', 'set', $Exchange)
if ($Sandbox) { $arguments += '--sandbox' }
Write-Host "The next prompts are hidden and are not written to the project."
& $Python @arguments
exit $LASTEXITCODE
