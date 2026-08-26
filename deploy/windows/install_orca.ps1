$ErrorActionPreference = 'Stop'
$Root = if ($env:ORCA_ROOT) { $env:ORCA_ROOT } else { Join-Path $HOME 'ORCA-Max-Mouny' }

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python 3.11+ is required and was not found on PATH.'
}
$pythonVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "Using Python $pythonVersion"

New-Item -ItemType Directory -Force -Path $Root | Out-Null
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if ((Resolve-Path $Repo).Path -ne (Resolve-Path $Root -ErrorAction SilentlyContinue).Path) {
    Copy-Item -Path (Join-Path $Repo '*') -Destination $Root -Recurse -Force -Exclude '.git','data'
}

$Venv = Join-Path $Root '.venv'
if (-not (Test-Path (Join-Path $Venv 'Scripts\python.exe'))) {
    python -m venv $Venv
}
& (Join-Path $Venv 'Scripts\python.exe') -m pip install --upgrade pip
& (Join-Path $Venv 'Scripts\python.exe') -m pip install -r (Join-Path $Root 'requirements.txt')
New-Item -ItemType Directory -Force -Path (Join-Path $Root 'data\orca_max_mouny') | Out-Null

$EnvExample = Join-Path $Root '.env.orca.example'
$EnvFile = Join-Path $Root '.env.orca'
if (-not (Test-Path $EnvFile)) { Copy-Item $EnvExample $EnvFile }
Write-Host "Installed ORCA Max Mouny at $Root"
Write-Host "No credentials were copied. Use local_setup.ps1 to place keys in the Windows user keyring."
