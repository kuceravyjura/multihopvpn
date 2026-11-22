# Runbook 09: recover from zero, and the monthly drill

**Scenario:** the PC's system disk is gone (or it is a brand-new PC). You have only your Google
account and Bitwarden.

The goal is to get back to working SSH, the management tunnel and Ansible, and then, if needed,
rebuild a server.

Real addresses and panel links are in the private `ACCESS.md` inside the kit. This runbook only
uses placeholders.

## 1. Tools on the new PC

1. Install **WireGuard for Windows**, **Git for Windows** and **Bitwarden**.
2. Install **WSL**: `wsl --install -d Ubuntu-24.04`.
3. In WSL:

   ```bash
   sudo apt update && sudo apt install -y restic rclone pipx git
   pipx install ansible-core && pipx inject ansible-core ansible-lint   # as in runbook 01
   ```

## 2. Open the kit

```bash
rclone config create gdrive drive scope=drive.file     # sign in with the same Google account
mkdir -p ~/.config/homelab-kit && chmod 700 ~/.config/homelab-kit
nano ~/.config/homelab-kit/restic-password            # paste from Bitwarden "homelab recovery kit (restic)"
chmod 600 ~/.config/homelab-kit/restic-password
export RESTIC_REPOSITORY=rclone:gdrive:homelab-recovery-kit RESTIC_PASSWORD_FILE=~/.config/homelab-kit/restic-password
restic snapshots                                        # newest at the bottom
restic restore latest --target ~/kit
```

`~/kit` now mirrors the old paths: `tmp/…/homelab-repo.bundle`, `tmp/…/ansible-vault-password`,
`home/<user>/.ssh`, `mnt/c/Users/<user>/.ssh` and `mnt/h/…/Homelab/backups`.

## 3. Put things back

```bash
# Repository (or clone from GitHub if it is still there)
git clone "$(find ~/kit -name homelab-repo.bundle)" ~/homelab

# SSH (WSL); the keys are the same as on Windows
cp -a "$(dirname "$(find ~/kit -path '*home/*/.ssh/id_ed25519')")"/. ~/.ssh/ && chmod 700 ~/.ssh && chmod 600 ~/.ssh/id_ed25519

# Vault password
mkdir -p ~/.ansible && cp "$(find ~/kit -name ansible-vault-password)" ~/.ansible/homelab-vault-pass && chmod 600 ~/.ansible/homelab-vault-pass

# Server backups back into the repo folder
cp -a "$(find ~/kit -type d -path '*Homelab/backups' | head -1)" ~/homelab/
```

On Windows:
1. Copy the Windows `.ssh` folder from the kit to `%USERPROFILE%\.ssh` (e.g. via `\\wsl$\Ubuntu-24.04\home\<user>\kit\mnt\c\Users\<user>\.ssh`).
2. **WireGuard app:** Import tunnel(s) from file, choose `wireguard-tunnels.zip` from the kit's
   `backups\recovery\`. Activate `homelab-mgmt`.

## 4. Check you are back

```powershell
ping 10.99.0.12        # tunnel to Server 2
ssh vps2 hostname      # SSH over the tunnel as ops
```

```bash
cd ~/homelab/ansible && export ANSIBLE_VAULT_PASSWORD_FILE=~/.ansible/homelab-vault-pass
ansible-playbook site.yml -l s2-lt --check        # vault opens, servers reachable, no surprises
```

Then bring the home pieces back:

```bash
sudo ... ansible-playbook site.yml -l vm-ctl                 # wg-mgmt (WSL), Grafana, recovery kit
ansible-playbook access.yml
homelab-kit                                                  # first upload from the new PC
```

Re-register the scheduled task as well: `scripts\Install-RecoveryKitTask.ps1`.

**If the tunnel is broken too:** use the break-glass routes in `ACCESS.md`. They are the provider
console, the dead-man switch window, and the cross-server panel access.

## 5. A dead server

Rebuild it from Ansible plus its newest backup: see runbook 04. The backup is in the kit's
`backups/<date>/vps1|vps2/`, or in the other copies: the server's own `/var/backups/homelab`
(7 days) and the PC.

## Monthly restore drill

Reliability means the restore has actually been done, not just written down. Once a month (Telegram
reminds you after 35 days, **RestoreDrillOverdue**):

1. `homelab-kit verify`: restores the newest snapshot to a temp dir. It checks that:
   - the vault password opens the vault;
   - the repo bundle is complete;
   - both SSH keys are valid;
   - the WireGuard export and the access sheet are there;
   - the latest server archives are intact.
2. **Server restore on staging** (runbook 04):
   1. reset staging to its checkpoint;
   2. restore Server 2's state from the archive that came **out of the kit**, not from the server;
   3. check the panel, AdGuard (DoH answers, ads blocked) and one VPN connection.
3. `homelab-kit drill-done`. This records the date, so monitoring stops reminding you.
4. Note anything that did not work in `docs/tests/` and fix the runbook.
