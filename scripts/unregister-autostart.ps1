$ErrorActionPreference = "Stop"
$TaskName = "ComfyUI Discord Bot"
$Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($null -eq $Task) {
    Write-Host "Die Autostart-Aufgabe '$TaskName' ist nicht registriert."
    exit 0
}

if ($Task.State -eq "Running") {
    Stop-ScheduledTask -TaskName $TaskName
}
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "Autostart-Aufgabe '$TaskName' wurde entfernt." -ForegroundColor Green
