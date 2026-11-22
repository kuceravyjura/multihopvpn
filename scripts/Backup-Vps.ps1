<#
.SYNOPSIS
  Pulls a fresh state backup from each VPS to backups\<date>\<host>\.

.DESCRIPTION
  Uses the Windows OpenSSH client over the wg-mgmt tunnel. Each name in -Hosts must be a
  Host entry in ~/.ssh/config that logs in as the admin user (root login is off):

    Host vps2
        HostName 10.99.0.12
        User ops
        IdentityFile ~/.ssh/id_ed25519

  Hosts with the backup role run /usr/local/sbin/homelab-backup (the same script as the
  nightly timer) and the new archive is downloaded. Hosts without it fall back to the
  phase-0 collector (scripts/collect-backup.sh).

  The backups folder is git-ignored: it holds client keys and password hashes.

.EXAMPLE
  .\scripts\Backup-Vps.ps1
  .\scripts\Backup-Vps.ps1 -Hosts vps2
  .\scripts\Backup-Vps.ps1 -Latest      # newest nightly archive only (used by the scheduled task)
#>
param(
    [string[]]$Hosts = @('vps1', 'vps2'),
    [string]$Destination = (Join-Path $PSScriptRoot '..\backups'),
    # Download the newest nightly archive instead of making a new one (scheduled runs).
    [switch]$Latest
)

$ErrorActionPreference = 'Stop'
$collector = Join-Path $PSScriptRoot 'collect-backup.sh'
$stamp = Get-Date -Format 'yyyy-MM-dd'

foreach ($h in $Hosts) {
    $dir = Join-Path $Destination (Join-Path $stamp $h)
    New-Item -ItemType Directory -Force -Path $dir | Out-Null

    if ($Latest) {
        $remoteTgz = (ssh $h 'ls -t /var/backups/homelab/*.tar.gz | head -1' | Select-Object -Last 1).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $remoteTgz) { throw "[$h] no nightly archive found" }
        $local = Join-Path $dir (Split-Path $remoteTgz -Leaf)
        if (Test-Path $local) { Write-Host "[$h] newest archive already here: $local"; continue }
        Write-Host "[$h] downloading newest nightly archive $remoteTgz"
        scp -q "${h}:$remoteTgz" $dir
        if ($LASTEXITCODE -ne 0) { throw "[$h] download failed" }
        Write-Host "[$h] saved to $dir" -ForegroundColor Green
        continue
    }

    ssh $h 'test -f /usr/local/sbin/homelab-backup'
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[$h] running homelab-backup"
        $output = ssh $h 'sudo -n /usr/local/sbin/homelab-backup'
        if ($LASTEXITCODE -ne 0) { throw "[$h] homelab-backup failed:`n$output" }
        # Last line: "<path> <size>". The archive is root:ops 0640, so no cleanup is needed:
        # the server keeps its own 7-day rotation.
        $remoteTgz = (($output | Select-Object -Last 1).Trim() -split ' ')[0]
        $cleanup = $false
    }
    else {
        Write-Host "[$h] no backup role yet, using the collector"
        scp -q $collector "${h}:/tmp/collect-backup.sh"
        if ($LASTEXITCODE -ne 0) { throw "[$h] upload failed" }
        $output = ssh $h 'sudo -n bash /tmp/collect-backup.sh; rc=$?; rm -f /tmp/collect-backup.sh; exit $rc'
        if ($LASTEXITCODE -ne 0) { throw "[$h] collector failed:`n$output" }
        $remoteTgz = ($output | Select-Object -Last 1).Trim()
        ssh $h "sudo -n chown `$(id -un) '$remoteTgz'" | Out-Null
        $cleanup = $true
    }

    Write-Host "[$h] downloading $remoteTgz"
    scp -q "${h}:$remoteTgz" $dir
    if ($LASTEXITCODE -ne 0) { throw "[$h] download failed" }
    if ($cleanup) { ssh $h "rm -f '$remoteTgz'" | Out-Null }
    Write-Host "[$h] saved to $dir" -ForegroundColor Green
}
