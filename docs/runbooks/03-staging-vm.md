# Runbook 03: staging VM

**Result:** `vm-staging`, a Debian 12 VM shaped like Server 1 (1 vCPU, 512 MB, 10 GB), reachable from
WSL at `192.168.0.70` with root + SSH key, and a "clean-install" checkpoint to roll back to after
every test.

## 1. Installer

`H:\Hyper-V\ISO\debian-12.15.0-amd64-netinst.iso` (710 MB), the latest Debian 12 point release,
from cdimage.debian.org. SHA-512 checked against Debian's `SHA512SUMS`:
`23257fab…ba161e7`.

## 2. Create the VM (administrator PowerShell)

Start → type *PowerShell* → right-click → *Run as administrator*, then:

```powershell
cd "H:\Рабочий стол\test bench\Homelab"
Set-ExecutionPolicy -Scope Process Bypass
.\homelab-vms\New-LabVm.ps1 -CreateSwitch
```

`-CreateSwitch` is only needed the first time. It creates the external switch `LabExternal` on the
Ethernet adapter; the PC's network drops for a few seconds while Windows moves onto it.

With 512 MB the Debian installer drops into **low memory mode**, skips the Hyper-V network driver
(`hv_netvsc`) and reports *No Ethernet card was detected*. Install with 1 GB and go back to 512 MB
afterwards (step 4):

```powershell
Set-VMMemory vm-staging -StartupBytes 1GB
Start-VM vm-staging; vmconnect.exe localhost vm-staging
```

## 3. Install Debian (in the console window)

| Screen | Choose |
|---|---|
| Boot menu | **Install** (text mode; graphical needs more than 512 MB) |
| Language / location / keyboard | English, your country, your layout |
| Network | DHCP is fine for now; fixed address is set in step 4 |
| Hostname | `vm-staging` · domain: leave empty |
| Root password | set one (like the VPS: needed for console login) |
| User | `tester` (Debian requires one; used once to copy the key) |
| Partitioning | Guided, use entire disk → all files in one partition → finish → yes |
| Mirror | your country, `deb.debian.org` |
| Software selection | untick **everything** except **SSH server** and **standard system utilities** |
| GRUB | install to the primary drive |

When it says *Installation complete*, press Continue. The VM reboots from the disk.

Back to Server 1's size (administrator PowerShell):

```powershell
Stop-VM vm-staging; Set-VMMemory vm-staging -StartupBytes 512MB; Start-VM vm-staging
```

## 4. Fixed address

Log in on the console as `root`, then:

```bash
ip -br addr        # the interface is normally eth0
cat > /etc/network/interfaces.d/eth0 <<'EOF'
auto eth0
iface eth0 inet static
    address 192.168.0.70/24
    gateway 192.168.0.1
    dns-nameservers 1.1.1.1 9.9.9.9
EOF
sed -i '/^allow-hotplug eth0/,/^iface eth0 inet dhcp/d' /etc/network/interfaces
reboot      # cleaner than restarting networking: no leftover DHCP address
```

## 5. SSH key for root (from WSL)

Debian refuses root password logins over SSH, the same as the VPS. Copy the key in through `tester`:

```bash
ssh-copy-id tester@192.168.0.70
ssh -t tester@192.168.0.70 'su -c "install -d -m 700 /root/.ssh && cp ~tester/.ssh/authorized_keys /root/.ssh/ && chmod 600 /root/.ssh/authorized_keys"'
ssh root@192.168.0.70 hostname      # must print vm-staging without a password
```

## 6. Checkpoint

Shut the VM down cleanly (`poweroff`), then in the administrator PowerShell:

```powershell
Checkpoint-VM -Name vm-staging -SnapshotName clean-install
Start-VM vm-staging
```

To start every Ansible test from a fresh server:

```powershell
Restore-VMCheckpoint -VMName vm-staging -Name clean-install -Confirm:$false; Start-VM vm-staging
```
