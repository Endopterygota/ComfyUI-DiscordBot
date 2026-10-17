$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtuelle Umgebung fehlt. Bitte zuerst scripts\setup.ps1 ausfuehren."
}

$BuildStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ExecutableName = "ComfyUI-Discord-Bot-$BuildStamp"

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name $ExecutableName `
    --paths "src" `
    --collect-all "discord" `
    "src\comfy_discord\__main__.py"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller ist mit Exit-Code $LASTEXITCODE fehlgeschlagen."
}

Write-Host "EXE erstellt: dist\$ExecutableName.exe" -ForegroundColor Green
Write-Host "config.json, .env und workflows muessen neben dem Arbeitsverzeichnis erreichbar bleiben."

