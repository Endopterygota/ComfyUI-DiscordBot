$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$Executable = Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "dist") -Filter "ComfyUI-Discord-Bot*.exe" -File -ErrorAction SilentlyContinue |
    Sort-Object -Property LastWriteTime -Descending |
    Select-Object -First 1
if ($null -ne $Executable) {
    Write-Host "Starte $($Executable.Name)"
    & $Executable.FullName
    exit $LASTEXITCODE
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtuelle Umgebung fehlt. Bitte zuerst scripts\setup.ps1 ausfuehren."
}
& $Python -m comfy_discord

