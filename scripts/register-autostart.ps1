param(
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"
$TaskName = "ComfyUI Discord Bot"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AutostartScript = Join-Path $PSScriptRoot "start-bot-autostart.ps1"
$PowerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path -LiteralPath $AutostartScript)) {
    throw "Autostart-Skript fehlt: $AutostartScript"
}

$Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$AutostartScript`""
$Action = New-ScheduledTaskAction `
    -Execute $PowerShellExe `
    -Argument $Arguments `
    -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$Principal = New-ScheduledTaskPrincipal `
    -UserId $UserId `
    -LogonType Interactive `
    -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 10 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$Task = New-ScheduledTask `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Startet den lokalen ComfyUI-Discord-Bot nach der Windows-Anmeldung."

Register-ScheduledTask -TaskName $TaskName -InputObject $Task -Force | Out-Null
Write-Host "Autostart-Aufgabe '$TaskName' wurde fuer $UserId registriert." -ForegroundColor Green

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
    Write-Host "Autostart-Aufgabe wurde gestartet." -ForegroundColor Green
}

Write-Host "Logdatei: $(Join-Path $ProjectRoot 'logs\bot-autostart.log')"
