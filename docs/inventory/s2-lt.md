# s2-lt · Server 2 · Lithuania

Snapshot: 2026-11-21, from the phase-0 backup.

## System

| | |
|---|---|
| OS | Ubuntu 24.04.3 LTS, kernel 6.8 (SSH via `ssh.socket`) |
| CPU / RAM | 1 vCPU / 961 MB (566 MB used, 394 MB available) |
| Swap | 511 MB, **189 MB in use**: memory pressure |
| Disk | 9.8 GB, **86 % used** (1.4 GB free) |
| Virtualisation | KVM (qemu-guest-agent) |
| Firewall | fail2ban (`inet f2b-table`) and Docker's tables; iptables INPUT policy accept; ufw inactive |

## Services

| Service | Notes |
|---|---|
| `x-ui` | 3x-ui panel + Xray core |
| `AdGuardHome` | systemd service; plain DNS refuses outside queries (verified 2026-11-21: timeout from outside) |
| `nginx` | 80 / 443: generated decoy website, so the server looks like an ordinary web host to scanners |
| `tor` | SOCKS on 127.0.0.1:9050 only |
| `fail2ban` | running (SSH jail) |
| `docker`, `containerd` | 5 containers, see below |
| `ModemManager`, `multipathd`, `udisks2`, `upower` | desktop/storage helpers a VPS doesn't need |

## Docker containers

| Container | Image | State | Ports |
|---|---|---|---|
| wg-easy | `weejewel/wg-easy` (old, unmaintained image) | up 5 months | 51820/udp, **51821/tcp web UI public** |
| portainer | `portainer/portainer-ce:latest` | up 5 months | **9443, 8000 public** |
| homer | `b4bz/homer:latest` | up 5 months | 8080 public |
| xray-server2 | `ghcr.io/xtls/xray-core:latest` | **removed 2026-11-21** | host networking, no open connections, logs showed only restarts (last 2026-06-22); multi-file confdir incl. `09_reverse.json`. Config backed up to `xray-server2-config.tgz`; volumes and image kept until 2026-11-28 as a fallback. Users, the S1→S2 hop and DNS checked working after removal |
| mtproto-proxy | `telegrammessenger/proxy` | exited 2 months ago | none |

## Cleanup 2026-11-21

Removed: portainer, homer, mtproto-proxy, xray-server2, their images, `portainer_data`, two
leftover networks (`homer_default`, `amnezia-dns-net`, a trace of an earlier Amnezia VPN install),
and an unused 1.12 GB `jc21/nginx-proxy-manager` image. Journal capped at 100 MB, old kernels and
the apt cache purged, `multipathd` disabled.

| | Before | After |
|---|---|---|
| Public admin ports 8000 / 8080 / 9443 | open | **closed** (verified with `ss`) |
| Disk used | 8.0 GB · 86 % | **5.5 GB · 59 %** |
| RAM available | 341 MB | **399 MB** |
| systemd-journald | 64 MB RSS, journal uncapped | journal 97 MB, capped at 100 MB |
| Docker images | 6 · 1.66 GB | 2 kept (wg-easy, xray-core fallback until 2026-11-28) |
| Containers | 5 | 1 (wg-easy) |

The idle containers used little RAM. The memory came back from the uncapped journal and multipathd.
Remaining large users: x-ui 96 MB, AdGuard 88 MB, Xray 56 MB, Docker + wg-easy ~110 MB (phase 5).

`/var/log/btmp` + `btmp.1` hold 42 MB of failed SSH logins: steady brute-force traffic, harmless
against key-only auth, and gone from the logs once SSH is reachable over wg-mgmt only.

## Health check 2026-11-22

Run with `ssh vps2 'bash -s' < scripts/healthcheck.sh` (read-only).

- **Password login is on.** `50-cloud-init.conf` (from the Ubuntu cloud image) sets
  `PasswordAuthentication yes`. Drop-ins load before `sshd_config`, and the first value wins, so the
  `no` on line 57 of `sshd_config` never applied. Root has a password and `PermitRootLogin yes`.
  Auth logs back to 2026-10-25 show only public-key logins (16); fail2ban has banned 223 addresses;
  ~2,850 failed attempts in 24 h. The hardening role's `10-homelab.conf` loads before `50-cloud-init.conf`
  and fixes this. Keep the root password: the provider's web console needs it.
  **Fixed 2026-11-22:** added `/etc/ssh/sshd_config.d/10-homelab.conf` (`PasswordAuthentication no`,
  `KbdInteractiveAuthentication no`), `sshd -t` passed, reloaded. Verified: effective config says `no`,
  a fresh key login works, and a client without a key gets `Permission denied (publickey)`.
  The Ansible hardening role manages the same file later.
- Running kernel 6.8.0-124 for 152 days; 6.8.0-149 installed, 6.8.0-151 available. Reboot required.
- 114 packages upgradable, incl. systemd. unattended-upgrades installs security updates only.
- Extra apt sources: `ooni.list` (Bintray, dead since 2021, breaks `apt update` with an error),
  `ooniprobe.list` (OONI Probe; `ooniprobe-cli` installed, no service), `tailscale.list` (only the
  keyring package installed; `tailscaled` masked), `docker.list` (needed for wg-easy until phase 5).
- Disk 60 %, RAM available 420 MB, no failed units, dpkg clean.
- ModemManager and udisks2 still running (the `common` role disables them).
- Still public: 3000 (AdGuard UI), 6903 (panel), 2096 (subscriptions), 51821 (wg-easy UI). Closed by the firewall role.

## TLS certificates (fixed 2026-11-22)

One ACME client: **certbot** (nginx authenticator) for `<s2-domain>`, used by nginx (443),
the 3x-ui panel and subscriptions (6903, 2096) and AdGuard DoH/DoT (3452, 853). Deploy hook
`50-homelab-reload.sh` restarts AdGuard and x-ui at 04:30 the night after a renewal. acme.sh is still
installed but manages nothing. See [postmortem](../postmortems/2026-11-22-tls-certificates.md).

## Listening ports (before cleanup)

| Port | Proto | Process | Exposure | Purpose |
|---|---|---|---|---|
| 22 | tcp | sshd | public | SSH |
| 80, 443 | tcp | nginx | public | decoy website |
| 53 | tcp+udp | AdGuard | public socket | plain DNS (refuses outside queries) |
| 853 | tcp | AdGuard | public | DNS-over-TLS (Android "Private DNS") |
| 3452 | tcp+udp | AdGuard | public | DNS-over-HTTPS (+ HTTP/3) |
| 3000 | tcp | AdGuard | public | AdGuard web UI → **mgmt only** |
| 6903 | tcp | x-ui | public | 3x-ui panel → **mgmt only** |
| 2096 | tcp | x-ui | public | 3x-ui subscription service, not used by clients → **mgmt only** |
| 8443 | tcp | xray | public | vless + Reality (tcp) |
| 1111 | tcp | xray | public | vless + Reality (xhttp), likely the hop from Server 1 |
| 62789, 11111 | tcp | xray | localhost | API / internal |
| 9050 | tcp | tor | localhost | SOCKS |
| 51820 | udp | wg-easy | public | WireGuard (to retire) |
| 51821 | tcp | wg-easy | public | wg-easy web UI → **mgmt only** |
| 9443, 8000 | tcp | portainer | public | Docker admin → **mgmt only or remove** |
| 8080 | tcp | homer | public | dashboard → **mgmt only or remove** |
| 12580, 26683, 30547, 31737, 38311, 44841, 56539, 57158 | udp | xray | public | 8 WireGuard inbounds |

## Xray routing

Outbounds: `direct`, `warp` (WireGuard to Cloudflare WARP), `blocked`. 4 routing rules, no `dns` section.

## Findings

1. **Portainer is public on 9443/8000.** Portainer controls Docker, which means root on the host.
   Highest-risk item on either server.
2. Admin UIs public: 3x-ui panel 6903, AdGuard UI 3000, wg-easy UI 51821, homer 8080.
3. Docker-published ports go through DNAT and the forward hook, so an input-chain firewall
   **does not cover them**. The firewall role handles them in a forward chain (`firewall_docker_mgmt_ports`).
4. Memory pressure (189 MB swapped) and disk at 86 %. Candidates: portainer, homer, the stopped
   mtproto container and its image, the unused `xray-server2`, ModemManager/multipathd/udisks2/upower,
   Docker images and logs (`docker system df`).
5. wg-easy uses an old unmaintained image; the server already runs 8 Xray WireGuard inbounds, so the
   migration is partly done.
6. AdGuard still binds `*:53`; outside queries time out. Bind it to localhost + Docker bridge in phase 3.
