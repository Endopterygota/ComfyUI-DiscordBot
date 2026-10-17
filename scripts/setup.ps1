$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if (-not (Test-Path -LiteralPath ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -e ".[build,test]"

if (-not (Test-Path -LiteralPath ".env")) {
    Copy-Item -LiteralPath ".env.example" -Destination ".env"
    Write-Host "Die Datei .env wurde angelegt. Trage dort DISCORD_TOKEN und optional DISCORD_GUILD_ID ein." -ForegroundColor Yellow
}

& ".venv\Scripts\python.exe" -m comfy_discord --check
Write-Host "Setup abgeschlossen." -ForegroundColor Green

