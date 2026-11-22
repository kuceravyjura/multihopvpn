# ADR 0003: 3x-ui state as a database backup; admin access as `ops`

**Status:** accepted (2026-11-22)

## Context

Phase 3 asks for "everything in Ansible". Two parts don't fit that literally:

1. **3x-ui.** Inbounds, clients, Reality keys, routing and the link between the two panels live in
   `/etc/x-ui/x-ui.db` (SQLite, 48 inbounds on Server 2). They are edited in the panel, often from a
   phone. Templating them in Ansible would mean copying every UUID and key into the vault and
   fighting the panel, which rewrites its own config whenever someone clicks Save.
2. **SSH.** The plan said "PermitRootLogin no, SSH listening on the mgmt IP only".

## Decision

- **Ansible owns the software, backups own the state.** The `xui` and `adguard` roles install a pinned
  release (sha256 checked) and restore `x-ui.db` / `AdGuardHome.yaml` from a backup **only when the
  host has none**. They never overwrite a live database or config. A different installed version is
  reported, not changed, unless `-e xui_upgrade=true` / `-e adguard_upgrade=true`.
- The `backup` role takes a consistent SQLite online backup plus configs and certificates every
  night; `Backup-Vps.ps1` pulls a fresh one home over the tunnel. A restore onto any other host
  switches off the panel's node links (they hold API tokens for the real servers), so a copy can
  never push config to production.
- **Root login is off; Ansible and people log in as `ops`** with key-only, passwordless sudo.
- **sshd keeps listening on all addresses.** The firewall already limits port 22 to wg-mgmt
  (stage B). Binding sshd to 10.99.0.x would add nothing while the firewall is up, and would take
  SSH away completely when it matters most: if wg-mgmt fails at boot, and while the dead-man
  switch has unloaded the firewall for break-glass access.

## Consequences

- Secrets (client UUIDs, Reality keys, AdGuard password hash) stay out of git, even encrypted;
  `backups/` is git-ignored and lives on the home PC.
- Losing the backups means losing the panel state. Mitigation: 7 nightly copies per server plus
  manual pulls home before every change (runbook 04).
- Proof: on 2026-11-22 a staging VM restored from a pre-Ansible checkpoint became a working copy of
  Server 2 in one run (4.5 min), see the test log.
