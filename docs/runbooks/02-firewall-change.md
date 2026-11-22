# Runbook 02: firewall changes

**How the role protects you:** before loading new rules it starts a systemd timer that deletes the
`inet homelab` table after 120 seconds. Ansible then drops its SSH connection and opens a fresh one.
Only if that succeeds does it cancel the timer. If the new rules lock SSH out, the rules remove
themselves two minutes later.

## Enabling the firewall on a server

1. On the server, list what is actually listening:
   ```bash
   ss -tlnp
   ss -ulnp | grep -v xray
   ```
2. Fill in `host_vars/<host>.yml`:
   - `firewall_public_tcp` / `firewall_public_udp`: Xray inbounds, WireGuard ports, DoH.
   - `firewall_mgmt_tcp`: 3x-ui panel, AdGuard web UI. These become reachable only over wg-mgmt.
   SSH and node exporter are added automatically.
3. Set `firewall_enabled: true`, keep `firewall_ssh_public: true`.
4. Dry run, then apply:
   ```bash
   ansible-playbook site.yml -l s2-lt --tags firewall --check --diff --ask-vault-pass
   ansible-playbook site.yml -l s2-lt --tags firewall --ask-vault-pass
   ```
5. Check from outside (from home, not over the VPN): VPN clients still connect, and
   `nmap -Pn -p- <server>` shows only the planned ports.

**After this the panel is no longer public.** Open it with an SSH tunnel:
`ssh -L 2053:127.0.0.1:<panel port> vps2`, then browse to `http://localhost:2053/<path>`.
Once wg-mgmt works, browse to `http://10.99.0.12:<panel port>/<path>` directly.

## Closing public SSH

Only when `ssh ops@10.99.0.12` over wg-mgmt works from vm-ctl:

1. Set `firewall_ssh_public: false`.
2. Point the inventory at the mgmt address for that host (`ansible_host: 10.99.0.12`).
3. Apply with the provider console open.

## Dead-man switch (second safety net)

The 2-minute rollback only catches one failure: Ansible itself losing SSH. Problems you notice
later (panel sync, VPN users, DNS) need a longer net. After **every** rule change the role arms
`homelab-fw-deadman.timer`:

- **20 minutes** later it removes the `inet homelab` table, disables `nftables.service` (so the rules
  don't come back at boot) and logs `firewall UNLOCKED ...` (`journalctl -t homelab-deadman`).
- The timer is enabled, so **a reboot doesn't defeat it**: it counts 20 minutes from boot.
- To restore after it fired: rerun the playbook. The role notices the missing table, reloads the
  rules, re-enables them at boot and arms a fresh switch.

When everything is verified, **disarm it over the tunnel**. That also proves the tunnel works:

```bash
ssh root@10.99.0.12 homelab-fw-disarm     # Server 2
ssh root@10.99.0.11 homelab-fw-disarm     # Server 1
```

Tested on vm-staging 2026-11-22: fired after 2 min (test fuse) and unlocked; Ansible recovery and
re-arm; disarm over 10.99.0.21; re-armed after reboot. Fuse length: `firewall_deadman_minutes`
(0 = off).

## Rolling back by hand

```bash
nft delete table inet homelab     # removes only our rules; Docker's stay
```
