<#
.SYNOPSIS
  On-demand start of the home part: wakes WSL (Grafana starts with it), keeps it awake for a
  few hours, waits until Grafana answers, then opens the panels page in the default browser.

.DESCRIPTION
  WSL does not start with Windows and shuts itself down when nothing uses it. This script starts
  a hidden keep-alive process (shown in WSL as "homelab-keepalive") that ends by itself after
  -Hours. The desktop shortcut from Install-HomelabShortcut.ps1 runs this script.

.EXAMPLE
  .\Open-Homelab.ps1            # start (or reuse) the keep-alive, open the page
  .\Open-Homelab.ps1 -Hours 2   # keep WSL awake for 2 hours instead of 8
  .\Open-Homelab.ps1 -Stop      # end the keep-alive now; WSL then sleeps when idle
#>
param([int]$Hours = 8, [switch]$Stop)

$distro = 'Ubuntu-24.04'
$root = Split-Path $PSScriptRoot -Parent
$page = Join-Path $root 'backups\recovery\panels.html'
$shell = New-Object -ComObject WScript.Shell
function Show-Note($text, $icon = 64) { $shell.Popup($text, 15, 'Homelab', $icon) | Out-Null }

if ($Stop) {
    wsl.exe -d $distro --exec pkill -f homelab-keepalive | Out-Null
    Show-Note 'Keep-alive stopped. WSL (and Grafana) will shut down when idle.'
    exit 0
}

# Start the keep-alive unless one is already running. `exec -a` names the process for pkill.
wsl.exe -d $distro --exec pgrep -f homelab-keepalive | Out-Null
if ($LASTEXITCODE -ne 0) {
    # One argument string: Windows PowerShell 5.1 does not quote array elements that contain spaces.
    Start-Process wsl.exe -WindowStyle Hidden `
        -ArgumentList "-d $distro --exec bash -c `"exec -a homelab-keepalive sleep ${Hours}h`""
}

# Grafana needs a few seconds after WSL wakes up.
$up = $false
foreach ($i in 1..30) {
    try {
        Invoke-WebRequest 'http://127.0.0.1:3000/api/health' -UseBasicParsing -TimeoutSec 2 | Out-Null
        $up = $true; break
    } catch { Start-Sleep -Seconds 2 }
}

if (-not (Test-Path $page)) {
    Show-Note "Panels page not found. Generate it in WSL:`n  cd ansible && ansible-playbook access.yml" 48
    exit 1
}
Start-Process $page
if (-not $up) { Show-Note 'Grafana did not answer within a minute. Check in WSL: systemctl status grafana-server' 48 }
