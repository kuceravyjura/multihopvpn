#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Creates a Hyper-V VM for the homelab (default: vm-staging, a copy of Server 1).

.DESCRIPTION
  Generation 2 VM with static memory (so it behaves like a small VPS), Secure Boot set up
  for Linux, the Debian installer attached and automatic checkpoints off.
  Refuses to touch a VM that already exists.

  The VM needs an external virtual switch to get an address on the home network (so WSL
  and Ansible can reach it). Pass -CreateSwitch the first time. Creating it moves the PC's
  network onto a virtual adapter: expect the connection to drop for a few seconds.

.EXAMPLE
  # First VM, also creates the switch:
  .\homelab-vms\New-LabVm.ps1 -CreateSwitch

.EXAMPLE
  .\homelab-vms\New-LabVm.ps1 -Name vm-ctl -MemoryMB 2048 -CpuCount 2 -DiskGB 20
#>
param(
    [string]$Name = 'vm-staging',
    [int]$MemoryMB = 512,
    [int]$CpuCount = 1,
    [int]$DiskGB = 10,
    [string]$IsoPath = 'H:\Hyper-V\ISO\debian-12.15.0-amd64-netinst.iso',
    [string]$VmRoot = 'H:\Hyper-V\VMs',
    [string]$SwitchName = 'LabExternal',
    [string]$NetAdapterName = 'Ethernet',
    [switch]$CreateSwitch
)

$ErrorActionPreference = 'Stop'

if (Get-VM -Name $Name -ErrorAction SilentlyContinue) {
    throw "VM '$Name' already exists. Remove it first (Remove-VM) if you want to recreate it."
}
if (-not (Test-Path $IsoPath)) { throw "Installer not found: $IsoPath" }

# --- switch -------------------------------------------------------------------
if (-not (Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) {
    if (-not $CreateSwitch) {
        throw "Switch '$SwitchName' doesn't exist. Run again with -CreateSwitch (network drops for a few seconds)."
    }
    Write-Host "Creating external switch '$SwitchName' on '$NetAdapterName' (network will blink)..." -ForegroundColor Yellow
    New-VMSwitch -Name $SwitchName -NetAdapterName $NetAdapterName -AllowManagementOS $true | Out-Null
    Start-Sleep -Seconds 5
}

# --- VM -----------------------------------------------------------------------
$vhd = Join-Path $VmRoot "$Name\$Name.vhdx"
New-Item -ItemType Directory -Force -Path (Split-Path $vhd) | Out-Null

New-VM -Name $Name -Generation 2 -Path $VmRoot `
       -MemoryStartupBytes ($MemoryMB * 1MB) `
       -NewVHDPath $vhd -NewVHDSizeBytes ($DiskGB * 1GB) `
       -SwitchName $SwitchName | Out-Null

Set-VMMemory    -VMName $Name -DynamicMemoryEnabled $false
Set-VMProcessor -VMName $Name -Count $CpuCount
Set-VM          -Name $Name -AutomaticCheckpointsEnabled $false -AutomaticStopAction ShutDown `
                -Notes 'Homelab VM. Managed by homelab-vms/New-LabVm.ps1'

# Debian's bootloader is signed by the Microsoft UEFI CA, not the Windows CA.
Set-VMFirmware -VMName $Name -EnableSecureBoot On -SecureBootTemplate MicrosoftUEFICertificateAuthority

$dvd = Add-VMDvdDrive -VMName $Name -Path $IsoPath -Passthru
Set-VMFirmware -VMName $Name -FirstBootDevice $dvd

Enable-VMIntegrationService -VMName $Name -Name 'Guest Service Interface'

Write-Host ""
Write-Host "Created $Name : $CpuCount vCPU, $MemoryMB MB, $DiskGB GB disk, switch $SwitchName" -ForegroundColor Green
if ($MemoryMB -lt 1024) {
    Write-Host "Note: the Debian installer needs 1 GB to load the Hyper-V network driver." -ForegroundColor Yellow
    Write-Host "  Install with: Set-VMMemory $Name -StartupBytes 1GB"
    Write-Host "  Afterwards:   Stop-VM $Name; Set-VMMemory $Name -StartupBytes ${MemoryMB}MB"
}
Write-Host "Start it and open the console with:"
Write-Host "  Start-VM $Name; vmconnect.exe localhost $Name"
