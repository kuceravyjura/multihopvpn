# s1-msk · Server 1 · Moscow

Snapshot: 2026-11-21, from the phase-0 backup.

## System

| | |
|---|---|
| OS | Debian 12 (bookworm), kernel 6.1 |
| CPU / RAM | 1 vCPU / 502 MB (201 MB used, 300 MB available) |
| Swap | 1 GB swap file (54 MB used) |
| Disk | 9.8 GB, **72 % used** (2.6 GB free) |
| Virtualisation | KVM (qemu-guest-agent) |
| Firewall | none of our own; `inet zapret` table and Docker's tables; input policy accept; ufw inactive |

## Services

| Service | Notes |
|---|---|
| `x-ui` | 3x-ui panel + Xray core |
| `zapret` | DPI-bypass for direct traffic (nfqws via nfqueue 200), own nft table `inet zapret` |
| `docker`, `containerd` | **running with zero containers**. About 60–100 MB of RAM for nothing |
| `ssh` | key-only, root login |
| `unattended-upgrades`, `qemu-guest-agent`, `cron`, `systemd-timesyncd` | standard |

wg-easy is **not** on this server. Moscow WireGuard users already connect to Xray's own WireGuard inbounds.

## Listening ports

| Port | Proto | Process | Exposure | Purpose |
|---|---|---|---|---|
| 22 | tcp | sshd | public | SSH |
| 6902 | tcp | x-ui | public | 3x-ui panel → **mgmt only** |
| 2096 | tcp | x-ui | public | 3x-ui subscription service, not used by clients → **mgmt only** |
| 8443 | tcp | xray | public | vless + Reality (tcp) |
| 11139 | tcp | xray | public | vless + Reality (xhttp) |
| 62789 | tcp | xray | localhost | Xray API |
| 11111 | tcp | xray | localhost | internal |
| 11757, 22387, 27975, 31667, 32526, 33540, 38897, 44877, 45043, 48034, 53621, 56214, 57265 | udp | xray | public | 13 WireGuard inbounds (one per user/device) |

## Xray routing

Outbounds: `direct` (default), `xhttptest-rurelay` (vless/xhttp/Reality, the hop to Server 2),
`polandrelay` (vless/gRPC/TLS), `blocked`. No `dns` section.

| # | Match | Goes to |
|---|---|---|
| 1 | API inbound | `api` |
| 2 | 36 domains (incl. geosite: telegram, youtube, discord, facebook) | Server 2 |
| 3 | geoip: facebook, telegram | Server 2 |
| 4 | geoip:private | blocked |
| 5 | one protocol (likely bittorrent) | blocked |

Everything else leaves directly from Moscow (through zapret).

`polandrelay` pointed at a third server that has been cancelled. No rule uses it, so it's a dead
entry: delete it in 3x-ui (Xray Configs → Outbounds).

## Cleanup 2026-11-21

| | Before | After |
|---|---|---|
| Disk used | 6.7 GB · 72 % | **3.8 GB · 41 %** |
| RAM used / available | 201 / 300 MB | **185 / 317 MB** |
| Swap used | 54 MB | 38 MB |
| `/var/log` | ~1 GB | ~80 MB (journal capped at 100 MB) |
| Docker | running, 0 containers, 4 unused images (1.68 GB) | **removed** (packages, data, apt source) |

Also found and fixed:

- **Stalled package updates.** A `grub-pc` upgrade had been left half-configured: the provider changed the
  VM's disk identifier, so GRUB's post-install step asked which disk to use and nobody was there to answer.
  While dpkg was in that state, unattended security updates couldn't install (33 packages pending).
  Fixed with `dpkg --configure -a`, GRUB installed to `/dev/sda`; debconf now records the new
  `/dev/disk/by-id/scsi-0QEMU_QEMU_HARDDISK_drive-scsi2-0-0-0`.
- `apt autoremove` removed five orphaned desktop/certificate libraries; x-ui and zapret verified active.
- Docker's in-memory firewall chains and `docker0` interface stay until the next reboot (harmless:
  this host doesn't forward traffic).

## Health check 2026-11-22

Run with `ssh vps1 'bash -s' < scripts/healthcheck.sh` (read-only).

- All updates installed (0 upgradable, dpkg clean). New kernel 6.1.0-56 installed; still running
  6.1.0-49 after 152 days up. **Reboot required.** It also clears the leftover `docker0` interface.
- Disk 36 %, RAM available 313 MB, swap 22 MB used, no failed units. Journal 92 MB (capped).
- SSH: password login off (effective config), root login with key. ~5,500 failed attempts in 24 h.
- `nginx` is installed but stopped and disabled: leftover, can be purged.
- Still public: 6902 (panel), 2096 (subscriptions). Closed by the firewall role.

## TLS certificates (checked 2026-11-22)

acme.sh: short-lived (6-day) Let's Encrypt certificate for the server's IP, standalone on port 80,
used by the 3x-ui panel and subscriptions (6902, 2096). Renewal restarts x-ui (and Xray); cron moved
from 18:42 to **04:29** Moscow time. nginx purged so nothing can take port 80. See
[postmortem](../postmortems/2026-11-22-tls-certificates.md).

## Findings (before cleanup)

1. Panel (6902) is public. Move it to wg-mgmt.
2. Docker is installed and running but unused. Remove it: frees RAM on the smallest server.
3. Disk at 72 % on a host that should need ~2 GB. Find out what's using it (`du -xh / --max-depth=2 | sort -h | tail -20`).
4. 13 WireGuard inbounds on scattered ports make a firewall allow-list hard to maintain. Pick a fixed range for new ones (see ADR 0003, to write).
5. Any host firewall must coexist with zapret's nft table. The `inet homelab` design does (separate table, input hook only).
