# Register (or replace) the temporary 6-hourly scrape task.
# Runs in the current user's context, so it fires while you are logged on.
# Remove it with:
#   Unregister-ScheduledTask -TaskName "PriceIntelScrape" -Confirm:$false

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $root "scripts\run_scrape.ps1"
$taskName = "PriceIntelScrape"

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Hours 6) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -WakeToRun `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 60)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Temporary price scrape every 6h (Docker/Celery Beat replacement)." `
    -Force | Out-Null

Write-Output "Registered '$taskName' - every 6 hours, starting in 1 minute."
Write-Output "Check: Get-ScheduledTaskInfo -TaskName $taskName"
Write-Output "Remove: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"
