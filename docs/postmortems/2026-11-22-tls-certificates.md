# Postmortem: TLS certificates expiring "sometimes"

**Status:** resolved 2026-11-22 · **Severity:** medium (DNS-over-HTTPS/TLS unusable for ~8 months;
panel/subscriptions intermittently on an expired certificate)

## Summary

"SSL sometimes falls" turned out to be three separate faults across two ACME clients. On Server 2,
AdGuard's DoH/DoT certificate had been expired since 2026-03-06 because its renewal needed port 80,
which nginx took over on 2026-02-28. The 3x-ui panel served an expired certificate after every
certbot renewal until something restarted it. On Server 1 renewals worked, but each one restarted
Xray at 18:42 Moscow time.

## How it was found

Not from the certificate files (those were current), but by asking every TLS port which certificate
it was **actually serving** (`openssl s_client` per port) and comparing serials with the file on disk:

| Port | Service | Served certificate |
|---|---|---|
| 443 | nginx | current (certbot reloads nginx itself) |
| 6903, 2096 | 3x-ui panel / subscriptions | current, but only because the server had rebooted that day |
| 3452, 853 | AdGuard DoH / DoT | **a different, IP-address certificate, expired 2026-03-06** |

## Root causes

1. **Two ACME clients, one port.** The 3x-ui install script set up acme.sh for a short-lived (6-day)
   Let's Encrypt certificate for the server's IP, renewed in *standalone* mode on port 80. AdGuard used
   that file. On 2026-02-28 nginx + certbot were installed for the domain; from then on nginx held
   port 80 and every acme.sh renewal failed silently (`Le_NextRenewTime` stuck at 2026-03-03, no log).
2. **Wrong reload target.** acme.sh's reload command restarted x-ui, not AdGuard, so even successful
   renewals never reached AdGuard.
3. **No certbot hooks.** x-ui reads its certificate only at startup; certbot renewed the domain
   certificate (Apr 22, Jun 22, Aug 21, Sep 25) but never restarted x-ui. The panel served the old
   certificate until a settings change or reboot. That's the "sometimes".
4. **Server 1:** acme.sh renews its IP certificate every few days and restarts x-ui (and with it Xray)
   at 18:42, cutting VPN users off for a few seconds in the evening. nginx was installed but stopped,
   so the Server 2 failure was one `systemctl start nginx` away.

## Fix

| Server | Change |
|---|---|
| 2 | AdGuard switched to certbot's domain certificate; `server_name` = domain (config backed up) |
| 2 | certbot deploy hook `/etc/letsencrypt/renewal-hooks/deploy/50-homelab-reload.sh`: after a successful renewal, schedules `systemctl restart AdGuardHome x-ui` for 04:30 the next night |
| 2 | acme.sh entries for the IP and the never-issued domain removed: one ACME client (certbot) left |
| 1 | acme.sh cron moved from 18:42 to 04:29 Moscow time (crontab backed up) |
| 1 | unused nginx purged, so nothing can take port 80 from acme.sh; `autoremove` also removed 7 orphaned Docker leftovers (git, patch, pigz, slirp4netns, …) |

## Verification

- `certbot renew --dry-run`: all simulated renewals succeeded.
- Hook run once by hand: timer scheduled for 04:30 and logged; test timer cancelled.
- From outside: strict certificate checks on 853 and 3452 return `Verify return code: 0 (ok)`.
- Real DoH query from Server 1 (an allowed client): HTTP 200, `NOERROR`, 2 answers.
  From the home IP: refused, because the AdGuard client allowlist doesn't include it, as intended.

## Follow-ups

- Clients must use the domain (`https://<s2-domain>:3452/dns-query`, DoT host
  `<s2-domain>`), not the IP.
- Monitoring (phase 6): alert on certificate expiry **as served on each port**, not on files.
- ~~`/opt/AdGuardHome` mode 0777 while AdGuard runs as root~~ **Fixed 2026-11-22.** The folder and
  the `AdGuardHome` binary itself were world-writable: any local user could have replaced a program
  that runs as root. Now `chmod 700` on the folder and `go-rwx` on everything inside; AdGuard kept
  serving throughout. The `adguard` role should enforce this.
- Ansible `xui`/`adguard` roles should own the certificate paths and the hook.
