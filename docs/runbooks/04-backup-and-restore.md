# Runbook 04: backups, restore and rebuilding a server

## Nightly backups (automatic)

The `backup` role installs `homelab-backup.timer` on every edge host: 03:40 server time (+ up to
10 min), kept 7 days, in `/var/backups/homelab/<host>-<date>.tar.gz` (`root:ops`, `0640`).

Contents, when present: `x-ui.db` (SQLite online backup, integrity-checked), `AdGuardHome.yaml`,
`/etc/letsencrypt`, `/root/.acme.sh`, `/etc/nginx`, `/etc/wireguard`, x-ui and AdGuard units,
nftables files, wg-easy data.

Check: `ssh vps2 systemctl list-timers homelab-backup.timer` and `ls -la /var/backups/homelab`.

## Pull a copy home (before every change)

```powershell
.\scripts\Backup-Vps.ps1            # both servers
.\scripts\Backup-Vps.ps1 -Hosts vps2
```

It runs the same script on the server and saves the archive to `backups\<date>\<host>\`.
`backups/` is git-ignored: the archives hold client keys and password hashes.

## Restore onto staging (rehearsal) or a new server

1. Extract the two state files into `backups/restore/<host>/`:

   ```bash
   mkdir -p backups/restore/s2-lt
   tar xzf backups/<date>/vps2/<archive>.tar.gz -C backups/restore/s2-lt --strip-components=1 \
       --wildcards '*/x-ui.db' '*/opt/AdGuardHome/AdGuardHome.yaml'
   mv backups/restore/s2-lt/opt/AdGuardHome/AdGuardHome.yaml backups/restore/s2-lt/
   ```

2. Point the host at them (`xui_restore_db`, `adguard_restore_config`; see `host_vars/vm-staging.yml`).
   They are used only when the host has no database/config yet.
3. A brand-new host only has root. First run:

   ```bash
   ansible-playbook site.yml -l vm-staging -e ansible_user=root -e ssh_permit_root_login=prohibit-password
   ansible-playbook site.yml -l vm-staging     # as ops: turns root login off
   ansible-playbook site.yml -l vm-staging     # must report changed=0
   ```

4. Disarm the firewall dead-man switch over the tunnel: `ssh ops@<wg ip> sudo homelab-fw-disarm`.

Staging differences: Server 2's certificates are not copied; `xui_selfsigned_if_missing` and
`adguard_selfsigned_if_missing` create stand-ins at the same paths. Node links to other panels are
switched off after every restore (`xui_restore_disable_nodes`, default true).

For a real rebuild of Server 2 also restore `/etc/letsencrypt` (or let certbot issue new
certificates), the nginx site and the wg-easy data from the same archive, and set
`xui_restore_disable_nodes: false` so the panel link to Server 1 keeps working.

## Reset staging to a fresh install

Admin PowerShell (Hyper-V needs it):

```powershell
Get-VMCheckpoint -VMName vm-staging | Restore-VMCheckpoint -Confirm:$false; Start-VM vm-staging
```

The checkpoint (22/11/2026 02:25 MSK) was taken two minutes before Ansible's first change, so it
is a clean Debian install: static IP .70 and root's SSH key, nothing else.
