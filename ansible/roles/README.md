# Roles

| Role | Status | What it does |
|---|---|---|
| `common` | ready | Base packages, unattended upgrades, journald cap, BBR, optional zram swap |
| `hardening` | ready | Admin user with sudo, key-only SSH, root login control |
| `wg_mgmt` | ready | Management WireGuard (`wg-mgmt`, 10.99.0.0/24), peers built from inventory |
| `firewall` | ready | nftables in its own `inet homelab` table, Docker-safe, auto-rollback |
| `node_exporter` | ready | Prometheus node exporter bound to the mgmt address |
| `xui` | phase 3–5 | Pinned 3x-ui install, restore `x-ui.db` from backup |
| `adguard` | phase 3–4 | AdGuard Home, DoH with ClientIDs, plain DNS on localhost/Docker only |
| `backup` | phase 7 | restic nightly to home + offsite, retention, restore test |

Every role runs on `vm-staging` before it touches `s1-msk` or `s2-lt`.
