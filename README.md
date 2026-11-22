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
- [x] Phase 3: everything in Ansible. Edge roles applied to **both servers** on 2026-11-22
  (idempotent, all VPN services verified); firewall on, SSH and panels over wg-mgmt only.
  `xui`, `adguard` and `backup` roles written; **acceptance test passed**: a fresh staging VM became
  a working copy of Server 2 in one run (4.5 min), second run changed=0
  ([ADR 0003](docs/adr/0003-panel-state-and-admin-access.md), [runbook 04](docs/runbooks/04-backup-and-restore.md)).
  Applied to both servers 2026-11-22: root login off (Ansible and people use `ops`), nightly
  backups at 03:40 pulled home with `Backup-Vps.ps1`.
- [x] Phase 4: AdGuard for Server 1 users (2026-11-22). Their DNS goes through the relay to
  Server 2's AdGuard as `srv1-moscow`, with a 1.5 s fallback to 1.1.1.1; canary first, a lab test
  fixed lost NXDOMAIN answers before rollout ([runbook 05](docs/runbooks/05-moscow-dns-via-adguard.md)).
  Optional, only if Russian sites get slower: send Russian domains to a local resolver.
- [ ] Phase 5: retire wg-easy. **Users moved to 3x-ui on 2026-11-22** without touching their devices
  (same server key, port and peer keys; [runbook 06](docs/runbooks/06-wg-easy-to-3x-ui.md)).
  Left after a quiet week (2026-11-29): remove wg-easy and Docker, then the matching Ansible settings.
- [ ] Phase 6: monitoring. **Live 2026-11-22:** Prometheus + Alertmanager on Server 2, probes both
  ways, Telegram alerts (~1.5 min), dead man's switch on Server 1 via ntfy
  ([ADR 0005](docs/adr/0005-monitoring-placement.md), [runbook 07](docs/runbooks/07-monitoring.md)).
  Left: Grafana at home with dashboards as code; Xray per-inbound traffic stats.
- [ ] Phase 7: backups and DR drill
- [ ] Phase 8: CI/CD deploys
