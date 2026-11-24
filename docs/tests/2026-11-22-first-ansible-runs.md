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

## Firewall stage B: SSH over wg-mgmt only

Prerequisite: an always-on home peer. The Windows PC joined wg-mgmt as `win-home` (10.99.0.2,
WireGuard for Windows, key generated in the app; only the public key is in the repo). From
Windows: ping both servers (56-72 ms), SSH and panel ports reachable, 10.99.0.x routed via the tunnel.

Change: `firewall_ssh_public: false` on both servers; the inventory and the `vps1`/`vps2` SSH
aliases now use 10.99.0.11/.12 (host keys compared with the public-IP keys before trusting them).
Dry run showed exactly one diff per server: the public `tcp dport 22 accept` line.

Server 2 first, then Server 1, each with the dead-man switch armed:

| Check | Server 2 | Server 1 |
|---|---|---|
| Public 22 | filtered | filtered |
| SSH over the tunnel | ✓ | ✓ |
| Public services | 443, 3452, 8443 open | 8443, 11139 open (80 passed, nothing listening) |
| Services | x-ui, AdGuardHome, nginx, docker active | x-ui, zapret active; panel sync connected |
| Owner test (VPN, panel, SSH) | ✓ | ✓ |
| Dead-man switch | disarmed over 10.99.0.12 | disarmed over 10.99.0.11 |

Break-glass if the tunnel ever fails: the provider's web console, or wait for an armed dead-man
switch to unload the firewall (`vps1-pub` / `vps2-pub` SSH aliases).

## Phase 3: xui, adguard and backup roles; rebuild from a fresh VM

Roles: `xui` (3x-ui 3.11.0), `adguard` (v0.107.71): pinned releases, sha256 from GitHub's release
API, state restored from a backup only when the host has none (ADR 0003). `backup`: nightly
`homelab-backup.timer`. Ansible now logs in as `ops`; root login off.

**Test 1, restore onto the existing staging VM.** Fresh read-only backup of Server 2, extracted to
`backups/restore/s2-lt/`. Found before restoring: the panel copy held an active node link to Server 1
(with its API token, inbound sync on). Server 1's firewall would refuse staging, but the role now
switches node links off after any restore. Telegram bot was already off in the copy.

**Test 2, the phase 3 acceptance test.** Staging reset to its checkpoint (taken two minutes before
Ansible's first change: no `ops`, no WireGuard, no firewall), then:

| Run | User | Result |
|---|---|---|
| 1 (bootstrap) | root, `-e ssh_permit_root_login=prohibit-password` | 4.5 min, changed=59, failed=0 |
| 2 | ops | changed=2: `PermitRootLogin no` and its sshd reload |
| 3 | ops | changed=0 |

Verified on the rebuilt VM (not from Ansible's report):

| Check | Result |
|---|---|
| Root SSH | `Permission denied (publickey)` |
| 3x-ui | 3.11.0 active; Server 2's inbounds listening (1111, 8443), panel 6903, subscriptions 2096; node links 0 enabled |
| AdGuard | v0.107.71 active on 53, 853 (DoT), 3452 (DoH + DoQ), UI 3000 |
| DoH lookup via staging | `example.com` answered; `doubleclick.net` → 0.0.0.0 (blocked) |
| Panel / AdGuard UI | over wg-mgmt: 404 at `/` (secret base path, as on Server 2) / 302 to login; from the LAN: filtered |
| Backup | 48 KB archive, `root:ops 0640`, keys inside still 0600; timer scheduled; runbook 04 extract command tested |
| Memory | 204 MB used of 392 MB |

Defects found and fixed on staging:

6. `cp -a --parents` failed on `/opt/AdGuardHome` inside the backup script. Replaced with a tar pipe.
7. `${#REL[@]}` in the script template opened a Jinja comment (`{#`). Rewritten without it.
8. Server 2 dry run: udisks2 and upower were disabled but running again (D-Bus activation), so the
   common role "changed" them on every run. They are now masked.

**Applied to the servers** (Server 2, then Server 1): only the dry-run changes (root login off,
backup timer, masked services on Server 2). Root SSH refused, all VPN/DNS services active, public
ports unchanged, first backups 556 KB / 524 KB. Defect 9: `Backup-Vps.ps1` tested
`test -x` as `ops` on a root-only script and fell back to the old collector; now `test -f`.

## Phase 4: Moscow DNS through AdGuard (canary, lab test, rollout)

1. **AdGuard prepared**, rehearsed on staging first: ClientID `srv1-moscow` allowed and named,
   Server 2's own IP exempt from the 20 q/s limit. A DoH query to `/dns-query/srv1-moscow` on
   staging was answered and logged with that ClientID. Applied on Server 2 (config backed up,
   restart, 0 errors, DoT/DoH still public).
2. **Canary**: Server 1's template changed (DNS module, `dns-out`, routing), validated with
   Server 1's own `xray run -test`, then the port-53 rule enabled for one inbound (57265, the
   owner's PC). Through it: `doubleclick.net` → 0.0.0.0, real names resolve, AdGuard listed
   `srv1-moscow` as top client (121 queries, 12 blocked), the DoH connection came from Server 2's
   own address (= through the relay). Note: WireSock's per-app split sends the Windows DNS
   service (`svchost`) outside the tunnel, so `nslookup.exe` was added to the app list for the test.
3. **Defect 10, caught by the canary**: a nonexistent name got no reply (client waited 10 s).
   Lab on staging, a throwaway Xray 26.10.21 with seven DNS variants:

| Variant | Real name | Nonexistent name | Server 2 down |
|---|---|---|---|
| AdGuard + `localhost` (first canary) | ok | **no reply** | no reply |
| AdGuard only | ok | NXDOMAIN 100 ms | no reply |
| AdGuard + 1.1.1.1 | ok | NXDOMAIN 216 ms | no reply within 4 s |
| **AdGuard (timeoutMs 1500) + 1.1.1.1** | ok, 300 ms | NXDOMAIN 148 ms | **ok in ~1.5 s** (no ad blocking) |

   The last one was applied, with only the AdGuard connection routed through the relay (a
   fallback through the relay would fail together with it). Re-test on the canary: nonexistent
   names ~0.5 s, ads blocked, real names 250-300 ms.
4. **Rollout** to all 15 inbounds (port-53 rule without an inbound list, so new inbounds are
   covered). Each added rule has a `ruleTag` describing it in the panel. x-ui active, 0 Xray DNS
   errors, 0 AdGuard refusals or rate-limit hits, DoH connection from the relay stays up.

## Per-user DNS identity: lab proof (staging)

Design and results in [ADR 0004](../adr/0004-per-user-dns-identity.md). Source-address check:
with `ip route add local 10.53.0.0/24 dev lo`, a local connection to 10.53.0.7 uses 10.53.0.7 as
its source (a `src` hint on the route is rejected; a dummy interface also works but needs one
address per user). AdGuard then logged the client as 10.53.0.7. End to end through a real relay
hop (fake Server 1 on staging): WireGuard-style and vless-style users logged as 10.53.0.7 and
10.53.0.8, ads blocked, NXDOMAIN intact. Defect 11: Xray 26's `direct` outbound drops private
destinations (`finalRules`), fixed with a dedicated `adguard-local` outbound. Staging keeps the
route (until reboot) and the rule for further work.

## Server 2 outage with the live phase 4 config (staging)

A fake Server 1 built from Server 1's live Xray DNS and routing sections, relay pointed at
staging; staging's Xray stopped to play "Server 2 down":

| Stage | Real name | Ad domain | Nonexistent | Note |
|---|---|---|---|---|
| Normal | ok | 0.0.0.0 | answered | first lookup ~1 s (relay setup) |
| Down, at once | ok, 0 ms | 0.0.0.0 | ok | Xray DNS cache |
| Down, 10 s later | ok, 12 ms | real address (1.1.1.1) | ok | fallback, no ad blocking |
| Back | ok | 0.0.0.0 | ok | AdGuard again, automatically |

Per-person DNS identity (ADR 0004) was load-tested (under 1% CPU, +16-36 MB during a 1,500-lookup
burst) and then deferred: it would take this fallback away. Its route was removed from Server 2.

## Phase 5: wg-easy users moved to 3x-ui (Server 2)

Runbook 06. The staging rehearsal used one idle peer's real keys from WSL: handshake with preshared
key, UDP DNS ~10 ms, HTTPS 200, ~90 Mbit/s download. A first UDP failure turned out to be a
malformed query in my own test script; tcpdump showed it.

On the real server the import also created a node copy. Deleting it set off the node-sync storm
(postmortem 2026-11-22). After both panels were restored and the links switched off, the cutover ran
at 18:08:58:
- wg-easy stopped and set not to restart; the inbound switched on in the panel (live, no Xray
  restart);
- `wge-shizpc_lithua` came online within seconds with its unchanged config;
- Xray 54 MB RAM, ~0% CPU; RAM available 505 → 519 MB.

## Phase 6: monitoring (ADR 0005, runbook 07)

Staging first:
- **x-ui stopped:** ServiceDown fired at 81-91 s; the Telegram message arrived ~1.5 min after the
  stop, "resolved" after the start. The plan asks for under 2 min.
- **Prometheus stopped:** the watcher pushed to ntfy after 3 failed checks (~4 min) and again on
  recovery. The pushes were verified on the topic; the first ones arrived before the phone
  subscribed, and a later test push reached the phone.

Defects found:
12. **Lost restarts:** a failed first run dropped pending restarts, so the exporters ran on stale
    settings. They listened on all addresses, exported every systemd unit, and used the package's
    default blackbox modules. Fixed for good with `force_handlers = True`.
13. **YAML null:** `receiver: null` without quotes is YAML null, so Alertmanager rejected the config.
14. **No external dead man's switch:** healthchecks.io's sign-up email never arrived, and Server 1
    cannot reach Telegram (IP block: plain TCP fails, so zapret cannot help). The dead man's switch
    is therefore a watcher on Server 1 that pushes to ntfy.sh.
15. **False HostDown at install:** on Server 2 the package's default config scraped
    `localhost:9100` before ours was loaded. The alert cleared after 5 min; the rule now requires a
    `host` label.

Production (Server 2, then Server 1), failed=0 on both:
- all 12 targets up; 8 probes green in both directions;
- certificates: domain 31.7 days, Server 1 IP certificate 3.6 days (a 6-day certificate, normal);
- memory right after start: Prometheus 16, Alertmanager 13, blackbox 2 MB;
- the watcher on Server 1 reports OK; no user service was touched.

## Phase 7: first monthly restore drill (runbook 09)

Server 2 rebuilt on staging using only what the Google Drive kit holds. The live server and the PC
copies were not used.

1. `homelab-kit restore`: 4 snapshots in the kit; the newest one restored.
2. Server 2's newest nightly archive came out of it: gzip intact, panel DB `integrity_check` ok,
   50 inbounds, 0 enabled node links. Its `x-ui.db` and `AdGuardHome.yaml` went into
   `backups/restore/s2-lt/`; the previous files were moved to `s2-lt.pre-drill/`.
3. Staging reset to its clean checkpoint (plain Debian 12, no `ops`, no 3x-ui), then
   `site.yml -l vm-staging` with the root bootstrap: **ok=123 changed=81 failed=0**.

| Check | Result |
|---|---|
| x-ui 3.11.0, AdGuard v0.107.71, backup timer | active |
| Inbounds / client records / enabled node links | 50 / 22 / 0 |
| VLESS Reality on 8443, real client built from the restored DB | HTTP 200 through the tunnel (Cloudflare, example.com), ~0.8 s |
| DoH 3452: example.com, wikipedia.org | answered |
| DoH 3452: doubleclick.net | blocked (0.0.0.0) |
| Panel on its secret path over wg-mgmt | HTTP 200; from the LAN: blocked |
| AdGuard UI over wg-mgmt | HTTP 302 (login) |
| Dead-man switch | access proved, disarmed |

`homelab-kit drill-done` recorded the drill, so RestoreDrillOverdue is quiet for 35 days.

**Time:** about 15 minutes from the Drive snapshot to a working VPN on staging.
**Findings:** none blocking. Two small notes:
- The step that extracts the restore files from the archive is still typed by hand; runbook 09
  now shows the command.
- The restored DB still carries the old node-copy duplicates (open decision: clean them on
  Server 1 and Server 2).

## Relay camouflage switched to Server 2's own site (2026-11-24, ADR 0006)

Rehearsed on staging first (both names, then new name only, then the old name refused).

| Step | Check | Result |
|---|---|---|
| 1. `decoy_site` on Server 2 | public 443 | HTTP/2, TLS 1.3 + X25519, valid certificate, fake business page; port 80 redirects |
| | `certbot renew --dry-run` | all simulated renewals succeeded |
| 2. Relay inbound, both names | database vs running config before and after | 11 = 11 inbounds; all public TCP and WireGuard UDP ports listening |
| | relay client with old and new name, public address | both HTTP 200 |
| | probe of 1111 with the domain name | the fake site, HTTP/2, valid certificate |
| 3. Server 1 outbound, new name | database vs running config | 15 = 15; all ports listening |
| | Telegram, YouTube, Discord via a Server 1 inbound | HTTP 200 (relay); ya.ru direct |
| | `rurelay` on Server 2 | online after the switch |
| | `doubleclick.net` via a Server 1 inbound (port 53) | `0.0.0.0` in 93 ms: AdGuard via the relay |
| | monitoring | 8/8 probes green, no alerts besides Watchdog |
| Probe rolled out | `s2-relay-camouflage` from Moscow | green: HTTP 200, HTTP/2, TLS 1.3, 0.18 s; 9/9 probes green |

New probe `reality_target` (staging): green normally; **red with nginx stopped while the TCP probe
stayed green**, green again after nginx started.

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
