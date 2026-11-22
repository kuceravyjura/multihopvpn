<#
.SYNOPSIS
  Puts a "Homelab" shortcut on the desktop. Clicking it runs Open-Homelab.ps1: wakes WSL and
  Grafana for 8 hours and opens the panels page. No admin rights needed.
#>
$script = Join-Path $PSScriptRoot 'Open-Homelab.ps1'
$link = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Homelab.lnk'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($link)
$s.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$s.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$s.WorkingDirectory = $PSScriptRoot
$s.IconLocation = "$env:SystemRoot\System32\shell32.dll,14"
$s.Description = 'Wake Grafana (WSL) and open the homelab panels page'
$s.Save()
"Shortcut created: $link"
