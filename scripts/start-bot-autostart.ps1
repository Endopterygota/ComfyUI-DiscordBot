$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LogDirectory = Join-Path $ProjectRoot "logs"
$LogFile = Join-Path $LogDirectory "bot-autostart.log"
$StartScript = Join-Path $PSScriptRoot "start-bot.ps1"

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null

try {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Autostart beginnt." | Out-File -LiteralPath $LogFile -Encoding Unicode
    & $StartScript *>> $LogFile
    $ExitCode = $LASTEXITCODE
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Bot beendet (Exit-Code $ExitCode)." | Add-Content -LiteralPath $LogFile -Encoding Unicode
    exit $ExitCode
}
catch {
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Autostart-Fehler: $($_.Exception.Message)" | Add-Content -LiteralPath $LogFile -Encoding Unicode
    throw
}
