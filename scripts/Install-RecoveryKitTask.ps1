<#
.SYNOPSIS
  Registers the "Homelab recovery kit" scheduled task for the current user: 10 minutes after
  logon, and at 13:00 and 21:00 (runs later if the PC was off). No admin rights needed.
#>
$script = Join-Path $PSScriptRoot 'Run-RecoveryKit.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Delay = 'PT10M'
$triggers = @($logon, (New-ScheduledTaskTrigger -Daily -At 13:00), (New-ScheduledTaskTrigger -Daily -At 21:00))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'Homelab recovery kit' -Action $action -Trigger $triggers `
    -Settings $settings -Description 'Pull server backups, upload the encrypted kit to Google Drive (Homelab repo, runbook 08)' -Force |
    Select-Object TaskName, State
