<#
.SYNOPSIS
  Phase-0 backup: pulls VPN/DNS configs from each VPS to backups\<date>\<host>\.

.DESCRIPTION
  Uses the Windows OpenSSH client (ssh/scp). Each name in -Hosts must be a Host
  entry in ~/.ssh/config, for example:

    Host vps1
        HostName <server 1 IP>
        User root
        IdentityFile ~/.ssh/id_ed25519

  The backups folder is git-ignored: it holds client keys and password hashes.

.EXAMPLE
  .\scripts\Backup-Vps.ps1
  .\scripts\Backup-Vps.ps1 -Hosts vps2
#>
param(
    [string[]]$Hosts = @('vps1', 'vps2'),
    [string]$Destination = (Join-Path $PSScriptRoot '..\backups')
)

$ErrorActionPreference = 'Stop'
$collector = Join-Path $PSScriptRoot 'collect-backup.sh'
$stamp = Get-Date -Format 'yyyy-MM-dd'

foreach ($h in $Hosts) {
    $dir = Join-Path $Destination (Join-Path $stamp $h)
    New-Item -ItemType Directory -Force -Path $dir | Out-Null

    Write-Host "[$h] uploading collector"
    scp -q $collector "${h}:/tmp/collect-backup.sh"
    if ($LASTEXITCODE -ne 0) { throw "[$h] upload failed" }

    Write-Host "[$h] collecting"
    $output = ssh $h "bash /tmp/collect-backup.sh; rc=`$?; rm -f /tmp/collect-backup.sh; exit `$rc"
    if ($LASTEXITCODE -ne 0) { throw "[$h] collector failed:`n$output" }
    $remoteTgz = ($output | Select-Object -Last 1).Trim()

    Write-Host "[$h] downloading $remoteTgz"
    scp -q "${h}:$remoteTgz" $dir
    if ($LASTEXITCODE -ne 0) { throw "[$h] download failed" }

    ssh $h "rm -f '$remoteTgz'" | Out-Null
    Write-Host "[$h] saved to $dir" -ForegroundColor Green
}
