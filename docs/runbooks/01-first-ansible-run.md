# Runbook 01: first Ansible run

**Result:** both servers have an admin user, hardened SSH, base settings, the management WireGuard
interface and node exporter. The firewall stays off until its port lists are filled in.

## 1. Install Ansible in WSL

WSL on this PC only has the Docker Desktop distro, which can't run Ansible. Install Ubuntu:

```powershell
wsl --install -d Ubuntu-24.04
```

Then inside Ubuntu:

```bash
sudo apt update && sudo apt install -y pipx wireguard-tools
pipx install --include-deps ansible
pipx install ansible-lint
pipx install yamllint
pipx ensurepath   # then open a new shell
```

**Use the repo in place on the Windows drive.** Windows drives appear world-writable in WSL, and
Ansible refuses to pick up `ansible.cfg` automatically from such a folder. An explicit
`ANSIBLE_CONFIG` path is always honored, so set it once in `~/.bashrc`:

```bash
cat >> ~/.bashrc <<'EOF'

# Homelab
export HOMELAB="/mnt/h/Рабочий стол/test bench/Homelab"
export ANSIBLE_CONFIG="$HOMELAB/ansible/ansible.cfg"
alias hl='cd "$HOMELAB/ansible"'
EOF
exec bash
```

Copy the SSH key and known hosts from Windows (keys must not stay on the world-writable drive mount):

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
WIN_SSH="$(wslpath "$(cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r')")/.ssh"
cp "$WIN_SSH/id_ed25519" "$WIN_SSH/id_ed25519.pub" "$WIN_SSH/known_hosts" "$WIN_SSH/config" ~/.ssh/
chmod 600 ~/.ssh/id_ed25519 ~/.ssh/config
```

Install the collections and check that Ansible uses the repo's config:

```bash
hl
ansible-galaxy collection install -r requirements.yml
ansible --version | grep 'config file'
ansible-inventory --graph
```

## 2. Generate management WireGuard keys

One key pair per host (`s1-msk`, `s2-lt`, `vm-staging`, `vm-ctl`):

```bash
for h in s1-msk s2-lt vm-staging vm-ctl; do
  priv=$(wg genkey); echo "$h  private=$priv  public=$(echo "$priv" | wg pubkey)"
done
```

- Public keys go into `host_vars/<host>.yml` (`wg_mgmt_public_key`).
- Private keys go into the vault (next step). Clear the terminal afterwards.

## 3. Create the vault

```bash
cp vault.example.yml group_vars/all/vault.yml
nano group_vars/all/vault.yml         # real IPs and private keys
ansible-vault encrypt group_vars/all/vault.yml
```

As set up on 2026-11-22: the vault password is a random string in `~/.ansible/homelab-vault-pass`
(WSL, mode 600), and `~/.bashrc` exports `ANSIBLE_VAULT_PASSWORD_FILE` pointing at it, so no
`--ask-vault-pass` is needed. **Keep a copy of that password in a password manager**: without it the
vault can't be opened. The vault was generated in `/dev/shm` and encrypted straight into the repo,
so private keys never touched the disk unencrypted.

Also put your OpenSSH **public** key in `group_vars/all/main.yml` (`admin_ssh_public_keys`).

## 4. Staging first

Create `vm-staging` in Hyper-V with the same OS as the servers and 512 MB RAM, put its address in
`inventory/hosts.yml`, then:

```bash
ansible-playbook site.yml -l vm-staging --ask-vault-pass
```

Run it a second time. It should report `changed=0`; that proves the roles are idempotent.

## 5. Real servers, one at a time

```bash
ansible-playbook site.yml -l s2-lt --check --diff --ask-vault-pass   # dry run, read the diff
ansible-playbook site.yml -l s2-lt --ask-vault-pass
```

Then the same for `s1-msk`.

## 6. Switch to the admin user

1. In a **new** terminal: `ssh ops@<server>` and `sudo -v`. Both must work.
2. In `group_vars/all/main.yml` set `ansible_user: "{{ admin_user }}"`.
3. Set `ssh_permit_root_login: "no"` (in `group_vars/all/main.yml`) and run the `hardening` tag:
   `ansible-playbook site.yml -l s2-lt --tags hardening --ask-vault-pass`.

## 7. Turn on the firewall

See [02-firewall-change.md](02-firewall-change.md).
