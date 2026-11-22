# Homelab

Two small VPS servers and a home Hyper-V host, managed as code.

The VPS servers run a two-hop VPN (Xray / 3x-ui): **Server 1** does split routing and sends selected
traffic over vless to **Server 2**, the exit node, which also runs AdGuard Home with DNS-over-HTTPS.
Everything heavy (Ansible, Git, monitoring, test VMs) runs at home and reaches the servers over a
separate management WireGuard network, so SSH, panels and metrics are never exposed to the internet.

The full plan with diagrams is in [`homelab-plan.html`](homelab-plan.html).

```
            Home lab (Hyper-V)
   vm-ctl · vm-mon · vm-staging   10.99.0.1
                 │  management WireGuard (wg-mgmt, 10.99.0.0/24)
         ┌───────┴─────────┐
   Server 1 (1 vCPU/512 MB) ──vless──▶ Server 2 (1 vCPU/1 GB) ──▶ internet
   10.99.0.11                          10.99.0.12
   Xray split routing                  Xray exit · AdGuard DoH
```

## Repository layout

| Path | Contents |
|---|---|
| `ansible/` | Inventory, variables, playbook and roles |
| `ansible/roles/` | `common`, `hardening`, `wg_mgmt`, `firewall`, `node_exporter` (+ planned `xui`, `adguard`, `backup`) |
| `scripts/` | Phase-0 backup (`Backup-Vps.ps1` + `collect-backup.sh`), read-only `healthcheck.sh`, vault check |
| `homelab-vms/` | Hyper-V VM creation (`New-LabVm.ps1`) |
| `docs/adr/` | Architecture decisions and the reasons behind them |
| `docs/runbooks/` | Step-by-step procedures |
| `docs/postmortems/` | Incident write-ups |
| `.github/workflows/` | Lint pipeline (yamllint, ansible-lint, vault check) |

## Getting started

1. **Back up first.** Follow [docs/runbooks/00-inventory-and-backup.md](docs/runbooks/00-inventory-and-backup.md).
2. **Set up Ansible in WSL.** Follow [docs/runbooks/01-first-ansible-run.md](docs/runbooks/01-first-ansible-run.md).
3. **Run against staging, then Server 2, then Server 1**, one host at a time.

## Safety rules

1. Before any SSH or firewall change: keep a second session open and check the provider's web console works.
2. Every change runs on `vm-staging` first.
3. Commit before applying, so there is always a known-good version.
4. Secrets live only in the encrypted vault. No real IPs, UUIDs, keys, domains or client names anywhere else.

## Status

- [x] Phase 0: backups taken, inventory recorded ([s1-msk](docs/inventory/s1-msk.md), [s2-lt](docs/inventory/s2-lt.md))
- [ ] Phase 1: quick security fixes. Done so far: Portainer and other leftovers removed,
  SSH password login off on both, logs capped, Docker removed from Server 1, all updates
  installed, both servers rebooted on current kernels (2026-11-22). **Firewall stage A live on
  both servers** (2026-11-22): panels, subscriptions and admin UIs reachable only over wg-mgmt
  (plus the other server's IP for panel sync); verified and disarmed over the tunnel.
  **Stage B live** (2026-11-22): SSH reachable only over wg-mgmt; the home PC is an always-on
  peer (`win-home`, WireGuard for Windows). Left: retire fail2ban on Server 2.
- [x] Ansible in WSL (Ubuntu 24.04, ansible-core 2.21) reads the repo config and inventory
- [ ] Phase 2: Hyper-V VMs and management WireGuard. `vm-staging` built (runbook 03); vault and
  WireGuard keys generated; edge roles pass on staging, idempotent and reboot-safe
  ([test log](docs/tests/2026-11-22-first-ansible-runs.md)). **wg-mgmt works end to end**: home
  (WSL as `vm-ctl`) reaches both servers and staging over 10.99.0.x. Left: a dedicated vm-ctl VM (optional).
- [ ] Phase 3: everything in Ansible. Edge roles applied to **both servers** on 2026-11-22
  (idempotent, all VPN services verified). Left: firewall on (= SSH and panels mgmt-only),
  xui/adguard/backup roles.
- [ ] Phase 4: AdGuard for Server 1 users
- [ ] Phase 5: retire wg-easy
- [ ] Phase 6: monitoring and alerts
- [ ] Phase 7: backups and DR drill
- [ ] Phase 8: CI/CD deploys
