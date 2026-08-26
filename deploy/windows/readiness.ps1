param(
    [switch]$CrossSource
)
$ErrorActionPreference = 'Stop'
$Root = if ($env:ORCA_ROOT) { $env:ORCA_ROOT } else { Join-Path $HOME 'ORCA-Max-Mouny' }
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw "ORCA venv not found at $Python. Run install_orca.ps1 first." }
Push-Location $Root
try {
    & $Python -m trading_bot.ops.readiness --json
    if ($CrossSource) { & $Python scripts\orca_cross_source_real.py }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
