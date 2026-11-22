# Test log: first Ansible runs (vm-staging, then Server 2)

**Date:** 2026-11-22 · **Target:** `vm-staging` (Hyper-V, Debian 12.15, kernel 6.1.0-56, 1 vCPU / 512 MB,
fresh install, "clean-install" checkpoint taken first) · **Roles:** common, hardening, wg_mgmt,
firewall, node_exporter · **Controller:** WSL Ubuntu 24.04, ansible-core 2.21

## Runs

| # | Command | Result |
|---|---|---|
| 1–3 | `--check --diff` | Found two defects in the roles (below); after fixing: `failed=0`, 7 expected check-mode ignores |
| 4 | real run | **failed**: `/etc/sudoers.d does not exist` |
| 5 | real run after fix | `ok=47 changed=20 failed=0` |
| 6, 7 | real run again | `changed=0`: idempotent |
| — | reboot + recheck | everything back after ~15 s, 0 failed units |

## Defects found and fixed

1. **Read-only probes skipped in check mode.** `command` tasks (`modinfo`, `grep Include`, `ip link`,
   `systemctl is-active`) don't run under `--check`, so later decisions used missing data.
   Fix: `check_mode: false` on probes that only read.
2. **Services from packages a dry run never installs.** `zramswap`, `wg-quick@`, node exporter and the
   `ops` user don't exist in `--check`. Fix: `ignore_errors: "{{ ansible_check_mode }}"` on those tasks
   and handlers only, so real runs still fail loudly.
3. **No sudo on Debian.** The Debian installer leaves `sudo` out when a root password is set, so
   `/etc/sudoers.d` was missing. Server 1 was installed the same way. Fix: the hardening role installs
   `sudo` first. Caught on staging, before it could fail halfway through on a production server.

Also tidied for CI: yamllint and ansible-lint (`production` profile) pass; deliberate `systemctl`
uses are marked with `noqa` and a reason; shared variables are exempt from the role-prefix rule.

## First production run: Server 2 (s2-lt, Ubuntu 24.04)

Dry run reviewed change by change (before → after, reason, undo) and approved before applying.
No address or port conflicts (10.99.0.0/24, UDP 51900) checked beforehand.

| # | Run | Result |
|---|---|---|
| 1 | `--check --diff` | `failed=0`, 19 planned changes, 5 expected check-mode ignores |
| 2 | real run | `ok=36 changed=23 failed=0` |
| 3 | real run again | `changed=0` |
| — | `ops` login | **failed**: `User ops not allowed because account is locked` |
| 4 | fix, staging then s2-lt (`--tags hardening`) | `changed=1`, rerun `changed=0`, `ops` login + sudo OK on both |

4. **Locked admin account on Ubuntu.** The `user` module stores `!` (locked) when no password is set.
   Debian's sshd allowed key login to such an account, Ubuntu's refuses it, so staging (Debian) couldn't
   catch it. Fix: `password: "*"`, which means "no password can match" without locking the account.
   Lesson: staging should also cover Ubuntu; candidate for a second staging VM.

After the run, checked from outside: root and `ops` key login work, passwords refused, sshd at
`maxauthtries 3`, `permitrootlogin without-password`, no X11/agent forwarding, TCP forwarding still on
(panel tunnels). x-ui, Xray, AdGuard, nginx, tor, fail2ban, Docker and wg-easy all running; ports 443,
853, 1111, 3452, 8443 still reachable from the internet; 9100 not. wg-mgmt up (10.99.0.12, 3 peers),
node exporter on 10.99.0.12:9100 only, BBR active, ModemManager/udisks2/upower off.
RAM available 471 → 526 MB. 0 failed units.

## Server 1 (s1-msk, Debian 12) and the management tunnel

**Server 1:** dry run matched the change list approved for Server 2 (plus `htop`/`rsync`, no services
to disable, no IP forwarding). zapret checked first: its UDP 50000–65535 profile (which covers
wg-mgmt's 51900) only desyncs hosts on its Discord hostlist, and WireGuard carries no hostname.
Real run `failed=0`, rerun `changed=0`. Verified: root and `ops` key login, passwords refused,
x-ui/Xray/zapret running, 8443 and 11139 open, 9100 closed to the internet, 337 MB RAM available.

**Home peer:** `vm-ctl` (10.99.0.1) is, for now, the WSL Ubuntu on the home PC (kernel 6.18 with
WireGuard, systemd running), configured with `wsl -u root` and `--tags wg_mgmt`; rerun `changed=0`.

| From → to (over 10.99.0.x only) | Ping | SSH root / ops+sudo | node exporter | Admin ports |
|---|---|---|---|---|
| home → s1-msk | 68 ms | ✓ / ✓ | 958 lines | panel 6902 open |
| home → s2-lt | 52 ms | ✓ / ✓ | 1,602 lines | panel 6903, AdGuard UI 3000, wg-easy UI 51821 open |
| home → vm-staging | 0.4 ms | ✓ / ✓ | 1,016 lines | — |
| s1-msk → s2-lt | 30 ms | — | 1,602 lines | — |

The s1 → s2 path goes through zapret's queue and handshakes normally, confirming the analysis above.
Everything is still reachable the old way too: the firewall is off, so nothing is mgmt-only yet.

## Firewall stage A on Server 2

Applied with the 2-minute rollback and the 20-minute dead-man switch armed. Checked before disarming:
public ports 22/80/443/853/1111/3452/8443 open; 53/2096/3000/6903/9100/51821 closed from the
internet; wg-easy and Xray WireGuard clients handshaking (UDP inbounds pass); Xray vless connections;
DNS for wg-easy clients via the Docker bridge; panel sync **online in both directions** (the source-IP
exception works); relay hop Server 1 → 2; DoH from Server 1; tunnel access to SSH, panel, AdGuard UI,
subscriptions, metrics; panel via `ssh -L` from Windows.

5. **Docker admin port blocked for the tunnel too.** The forward-chain rule for Docker-published
   admin ports (`ct status dnat … iifname != wg-mgmt drop`) also matched the container's **reply**,
   which re-enters forward from the Docker bridge, so the wg-easy UI was unreachable even over
   wg-mgmt. Fix: `ct direction original`. Caught by testing the tunnel path, not just "closed from
   outside". A first wrong guess (input path) was reverted.

## Firewall stage A on Server 1

Applied the same way. Public: 22, 8443, 11139 open; 80 answers "refused" (firewall passes it for
acme.sh renewal, nothing listens between renewals); 2096, 6902, 9100 filtered. zapret (incl. nfqws)
running and direct traffic works through it; Xray WireGuard clients active; relay hop to Server 2;
panel sync online both ways; tunnel access to SSH/panel/subscriptions/metrics; panel via `ssh -L`.
Panel and VPN confirmed in the browser by the owner; dead-man switch disarmed over 10.99.0.11.

## Verified from outside on staging (not from Ansible's own report)

| Check | Result |
|---|---|
| `ops` user, key login, passwordless sudo | ✓ |
| Password login offered | no: `Permission denied (publickey)` |
| sshd effective config | `passwordauthentication no`, `maxauthtries 3`, root by key only |
| Firewall | `inet homelab` loaded, `policy drop`; 22 open, 9100 and 2053 filtered from the LAN |
| Rollback timer | armed, rules loaded, fresh SSH connection proved, timer cancelled (gone) |
| wg-mgmt | up on 10.99.0.21/24, port 51900, peers s1-msk, s2-lt, vm-ctl |
| node exporter | listens only on 10.99.0.21:9100, ~1,000 metric lines |
| zram / BBR / auto-updates | zram0 256 MB (priority 100), `bbr` + `fq`, unattended-upgrades enabled |
| After reboot | firewall, wg-mgmt, node exporter, zram, BBR all back; 0 failed units |
