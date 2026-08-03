<#
setup/termux_setup.ps1 - Generate the phone-side Termux config.

Reads the .env file, extracts TERMUX_BRIDGE_TOKEN + the local IP,
and writes a ready-to-paste termux_bridge.json that the phone's
Termux daemon needs.

Output: setup/termux_bridge.json (and prints the contents to the
console for easy copy-paste).
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$RepoDir
)

$ErrorActionPreference = 'Stop'

# Load .env
$envFile = Join-Path $RepoDir ".env"
if (-not (Test-Path $envFile)) {
    Write-Error ".env not found at $envFile - run setup.ps1 first"
}

Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2].Trim('"').Trim("'"), "Process")
    }
}

if (-not $env:TERMUX_BRIDGE_TOKEN) {
    Write-Host "TERMUX_BRIDGE_TOKEN not set in .env. Generating one..." -ForegroundColor Yellow
    $newToken = [guid]::NewGuid().ToString('N') + [guid]::NewGuid().ToString('N').Substring(0,8)
    (Get-Content $envFile) -replace 'TERMUX_BRIDGE_TOKEN=.*', "TERMUX_BRIDGE_TOKEN=$newToken" | Set-Content $envFile
    [Environment]::SetEnvironmentVariable("TERMUX_BRIDGE_TOKEN", $newToken, "Process")
}

# Find a sensible IP for the laptop (try Ethernet, then WiFi)
$lanIp = $null
$adapters = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notmatch '^127\.' -and $_.IPAddress -notmatch '^169\.254\.' -and $_.PrefixOrigin -ne "WellKnown" }
foreach ($a in $adapters) {
    if ($a.InterfaceAlias -match "Wi-Fi|Wireless|Ethernet|LAN") {
        $lanIp = $a.IPAddress
        break
    }
}
if (-not $lanIp -and $adapters) { $lanIp = $adapters[0].IPAddress }
if (-not $lanIp) { $lanIp = "YOUR-LAPTOP-IP" }

$port = if ($env:TERMUX_BRIDGE_PORT) { $env:TERMUX_BRIDGE_PORT } else { "8765" }

$config = @{
    server_url = "http://${lanIp}:${port}"
    auth_token = $env:TERMUX_BRIDGE_TOKEN
    device_name = $env:COMPUTERNAME
    poll_interval = 3.0
    event_interval = 300.0
    allowed_commands = @(
        "battery", "wifi", "location", "run", "notify", "vibrate",
        "toast", "clipboard", "speak", "torch", "share", "uptime",
        "storage", "wake", "ping"
    )
} | ConvertTo-Json -Depth 5

$outPath = Join-Path $RepoDir "setup\termux_bridge.json"
$config | Set-Content $outPath -Encoding UTF8

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Termux Bridge - Phone Configuration Generated" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Server URL:  http://${lanIp}:${port}" -ForegroundColor Green
Write-Host "Auth Token:  $($env:TERMUX_BRIDGE_TOKEN)" -ForegroundColor Green
Write-Host "Config file: $outPath" -ForegroundColor Green
Write-Host ""
Write-Host "----- termux_bridge.json -----" -ForegroundColor Yellow
Write-Host $config
Write-Host "-----------------------------" -ForegroundColor Yellow
Write-Host ""
Write-Host "On your phone (Termux), run:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  pkg install python termux-api" -ForegroundColor White
Write-Host "  mkdir -p ~/orca_bridge ; cd ~/orca_bridge" -ForegroundColor White
Write-Host ""
Write-Host "  # Download the daemon:" -ForegroundColor White
Write-Host "  curl -O https://raw.githubusercontent.com/hermasorca13-stack/" -ForegroundColor White
Write-Host "       Orca-Agent-Unified/main/tools/termux_bridge.py" -ForegroundColor White
Write-Host ""
Write-Host "  # Create the config (paste the JSON above):" -ForegroundColor White
Write-Host "  nano termux_bridge.json" -ForegroundColor White
Write-Host ""
Write-Host "  # Sanity check:" -ForegroundColor White
Write-Host "  python termux_bridge.py doctor" -ForegroundColor White
Write-Host ""
Write-Host "  # Start the daemon (detached):" -ForegroundColor White
Write-Host "  nohup python termux_bridge.py >~/orca_bridge/bridge.log 2>&1 &" -ForegroundColor White
Write-Host ""
Write-Host "Then back in Telegram, try:" -ForegroundColor Cyan
Write-Host "  /termux ping" -ForegroundColor Green
Write-Host "  /termux battery" -ForegroundColor Green
Write-Host ""
