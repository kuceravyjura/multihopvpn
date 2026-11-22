<#
.SYNOPSIS
  Scheduled recovery-kit run: pull the newest nightly server backups, then upload the encrypted
  kit to Google Drive (homelab-kit in WSL). Logs to backups\recovery\kit.log.
#>
$ErrorActionPreference = 'Continue'
$root = Split-Path $PSScriptRoot -Parent
$log = Join-Path $root 'backups\recovery\kit.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Write-Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Tee-Object -FilePath $log -Append }

Write-Log '--- start'
try { & (Join-Path $PSScriptRoot 'Backup-Vps.ps1') -Latest *>&1 | ForEach-Object { Write-Log $_ } }
catch { Write-Log "server backup pull failed: $_ (continuing with what is here)" }

wsl.exe -d Ubuntu-24.04 -- homelab-kit *>&1 | ForEach-Object { Write-Log $_ }
Write-Log "--- end (homelab-kit exit code $LASTEXITCODE)"
exit $LASTEXITCODE
