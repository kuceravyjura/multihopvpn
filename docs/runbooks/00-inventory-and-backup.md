# Runbook 00: inventory and backup

**When:** before changing anything, and again before every risky change.
**Result:** a copy of every VPN client, routing rule and DNS setting on your PC, plus a snapshot of each server's state.

## 1. Prepare SSH on Windows

The script uses the Windows OpenSSH client (`ssh`, `scp`) and the host aliases in
`C:\Users\<you>\.ssh\config` (already set up on this PC):

```
Host vps1        # Server 1 · Moscow
    HostName <server 1 IP>
    User root
    IdentityFile ~/.ssh/id_ed25519

Host vps2        # Server 2 · Lithuania
    HostName <server 2 IP>
    User root
    IdentityFile ~/.ssh/id_ed25519
```

Test: `ssh vps1 hostname` and `ssh vps2 hostname`. The real IPs stay in this local file, never in the repo.

## 2. Check the break-glass path

Log in to each provider's control panel and open the web/VNC console. Make sure you can log in there
(root password or rescue mode). This is how you get back in if SSH or the firewall goes wrong.
Take a provider snapshot if the plan includes one.

## 3. Run the backup

From the repo root in PowerShell:

```powershell
.\scripts\Backup-Vps.ps1
```

Files land in `backups\<date>\vps1\` and `backups\<date>\vps2\`. Each tarball contains:

| File | What it is |
|---|---|
| `x-ui.db` | 3x-ui database: inbounds, clients, routing. Restoring this restores the panel. |
| `xray-config.json` | The Xray config 3x-ui generated from the database |
| `AdGuardHome.yaml` | AdGuard settings (Server 2) |
| `wg-easy-*/` | wg-easy data: peers and keys |
| `inventory.txt` | OS, memory, disk, listening ports, services |
| `firewall.txt` | Current nftables / iptables / ufw state |

`backups/` is git-ignored. Keep a second copy somewhere off your PC.

## 4. Record the inventory

Copy the useful parts of `inventory.txt` (OS version, memory, listening ports) into
`docs/inventory/<host>.md`. **Replace public IPs** with `<s1-ip>` / `<s2-ip>` first.

## 5. Test port 53 from outside

```powershell
Resolve-DnsName example.com -Server <server 2 IP> -DnsOnly
```

A timeout or refusal is good. An answer means plain DNS is still open to the internet.
