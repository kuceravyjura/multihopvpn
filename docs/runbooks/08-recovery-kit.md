# Runbook 08: the recovery kit on Google Drive

**What it is:** an encrypted, versioned copy of everything needed to rebuild the homelab from a
new PC. **What opens it:** one password, kept in Bitwarden.

## What is in it

| Item | Source on the PC |
|---|---|
| SSH keys, config, known hosts | Windows `%USERPROFILE%\.ssh`, WSL `~/.ssh` |
| Ansible vault password | WSL `~/.ansible/homelab-vault-pass` |
| The whole repository (git bundle) | this repo; survives even losing GitHub |
| Server backups (nightly archives) | `backups/<date>/vps1`, `vps2` |
| WireGuard tunnel `homelab-mgmt` | `backups/recovery/wireguard-tunnels.zip` (exported by hand once) |
| Private access sheet + panel launcher page | `backups/recovery/ACCESS.md`, `panels.html` (`ansible-playbook access.yml`) |

**Not in it:**
- **zapret:** reinstalled out of the box if ever needed.
- **The restic password itself:** that's the point; it lives in Bitwarden.

## How it runs

1. **The Windows scheduled task** "Homelab recovery kit" (`scripts\Install-RecoveryKitTask.ps1`)
   runs 10 minutes after logon and at 13:00 and 21:00. If the PC was off at those times, it runs
   as soon as possible. It calls `scripts\Run-RecoveryKit.ps1`, which:
   1. pulls the newest nightly server archives (`Backup-Vps.ps1 -Latest`);
   2. runs `homelab-kit` in WSL.

   Log: `backups\recovery\kit.log`.
2. **`homelab-kit`** (Ansible role `recovery_kit`):
   - takes a **restic** snapshot, encrypted (AES-256) and deduplicated;
   - uploads it through **rclone** to Google Drive, folder `homelab-recovery-kit-2`, using the
     `drive.file` scope: rclone sees only what it created;
   - restic finds the previous snapshot by host and tag (`--group-by host,tags`), so a run reads
     only changed files.
3. **Sundays** (or `homelab-kit full`): it also prunes old snapshots (keeps 14 daily, 8 weekly,
   12 monthly) and verifies the repository. These steps are weekly to keep Drive API calls low.
4. **Monitoring:** each successful upload is reported to Server 2. Telegram alerts if there has
   been no upload for 3 days (**RecoveryKitStale**).

## Commands (WSL)

```bash
homelab-kit              # backup + upload + report (what the task runs)
homelab-kit full         # + prune and verify the repository
homelab-kit snapshots    # list snapshots
homelab-kit verify       # restore the newest snapshot to a temp dir and prove it is usable
homelab-kit restore DIR  # restore the newest snapshot into DIR
homelab-kit drill-done   # record a completed monthly restore drill (runbook 09)
```

## First-time setup (already done on this PC, 2026-11-22)

1. `ansible-playbook site.yml -l vm-ctl --tags recovery_kit` (as root in WSL). This installs
   restic, rclone and `homelab-kit`.
2. Run `homelab-kit` once. It creates `~/.config/homelab-kit/restic-password` and stops.
3. **Copy that password into Bitwarden** (item "homelab recovery kit (restic)").
4. Authorize Drive: `rclone config create gdrive drive scope=drive.file`. Open the printed link in
   the Windows browser and allow access.
5. Export the WireGuard tunnel: in the WireGuard app, **Export all tunnels to zip**, saved to
   `backups\recovery\wireguard-tunnels.zip`.
6. Run `homelab-kit` again: the first upload.
7. Register the scheduled task: `scripts\Install-RecoveryKitTask.ps1`.

## Keep it current

- **Changed panel ports or paths, the domain, or added services:** run
  `ansible-playbook access.yml`. The next run uploads the new access sheet.
- **New or changed WireGuard tunnel on Windows:** export the zip again.
- **Rotated SSH keys or vault password:** nothing to do; the next run picks them up.

## If Google throttling gets annoying

Already built in: restic waits up to 5 min for rclone (`-o rclone.timeout=5m`), rclone sends at most
4 requests/s, and the repository is created only once (a marker file in `~/.config/homelab-kit/`).
On 2026-11-22 a throttled check made an early version try to create the repository again; that
attempt failed harmlessly, and the marker prevents it now. A run that fails is simply retried at the
next trigger; RecoveryKitStale only fires after 3 days without an upload.

### Personal client ID (done 2026-11-25)

rclone's built-in API key is shared by all rclone users, and it ran out: on 2026-11-25 every
request got `403 RATE_LIMIT_EXCEEDED` and an hour-long run ended in a 500. Since then rclone uses
its own free Google Cloud client (project `homelab-kit`).

1. Google Cloud Console: new project, enable the **Google Drive API**.
2. **Google Auth Platform**: Get started (External). On **Branding** set the home page and
   privacy-policy links (the GitHub repo is fine for both; add `github.com` as an authorised
   domain if asked); no logo, since a logo forces verification. Then **Audience → Publish app**:
   the status must be **In production**. In "Testing" Google expires the login after 7 days and
   the nightly runs start failing.
3. **Clients → Create client**, type Desktop app. Keep the ID and secret (Bitwarden).
4. In WSL, typing the values yourself:
   `rclone config update gdrive client_id=… client_secret=… --drive-scope drive.file`, then
   `rclone config reconnect gdrive:` (refresh: y, auto config: y, shared drive: n). Google warns
   "hasn't verified this app": Advanced → continue.

**A new client cannot see the old folder.** `drive.file` gives a client only the files it created
itself, so a new client ID means a new folder: change `kit_drive_folder`, deploy, delete
`~/.config/homelab-kit/repo-initialized`, and run `homelab-kit` (a new repository with the same
restic password, full upload), then `homelab-kit verify`. Delete the old folder in the Drive web
page after a few good runs. That happened once: `homelab-recovery-kit` → `homelab-recovery-kit-2`.
