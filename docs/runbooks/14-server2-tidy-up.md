# Runbook 14: Server 2 tidy-up (2026-11-24)

Four small fixes, each proven on staging first, applied to Server 2 the same evening.

**Result on Server 2 (23:07–23:15 MSK):** database matched the live config before the restart; all
11 inbounds back; `wg0` gone, 62 leftover rules removed, no global IPv6; Telegram connects over
IPv4 in 0.08 s; WARP through the live settings: `warp=on`, Cloudflare Vilnius. DoH (plain and
`/srv1-moscow`) 200; `:3452/` = decoy site, `/login.html` 404; UI on the tunnel 200; fail2ban gone;
crontab empty. All probes green, no alerts. (The steady `no known endpoint for peer` errors in the
x-ui log are one user's device, not WARP; they were there before: 1821 since 20:00.)

## 1. WARP inside Xray (no `wg0` interface)

**Problem.** The panel's WARP outbound (all IPv4 traffic of inbound 8443 goes through it) ran as a
kernel interface `wg0` that holds WARP's IPv6 address. The server has no IPv6 of its own, but with
that address programs try IPv6 first and hang: the bot's Telegram replies took 1–2 minutes. Xray
also added a pair of `ip -6 rule` entries on every restart and never removed them (64 by then).

**Fix.** `noKernelTun: true` (userspace WireGuard inside Xray) and `domainStrategy: ForceIPv4`
(WARP's endpoint name also resolves to IPv6, which userspace mode would try and fail).

```bash
sudo python3 scripts/xray-warp-userspace.py show /etc/x-ui/x-ui.db
# before a restart: the database's local inbounds must match the live config (2026-11-22 postmortem)
sudo python3 scripts/xray-warp-userspace.py on /etc/x-ui/x-ui.db     # backs up the DB first
sudo systemctl restart x-ui                                           # a few seconds' break
while sudo ip -6 rule del table 10230 2>/dev/null; do :; done; sudo ip -6 route flush table 10230
```

Check: `ip -br link show wg0` → does not exist; `ip -6 addr show scope global` → empty; every
inbound port bound again. WARP itself: on staging a throwaway Xray with the same outbound returned
`warp=on` from `https://www.cloudflare.com/cdn-cgi/trace`.

Undo: `xray-warp-userspace.py off`, restart x-ui (or restore the `x-ui.db.bak-warp-*` copy).

## 2. AdGuard's admin page off the internet

**Problem.** AdGuard serves its admin UI on its HTTPS port, and that port (3452) is also the public
DNS-over-HTTPS port: the login page was open to anyone.

**Fix.** AdGuard stops serving HTTPS (`port_https: 0`) and accepts plain DoH from nginx
(`allow_unencrypted_doh: true`; no `force_https`). nginx listens on 3452 with the same certificate:
`/dns-query…` goes to AdGuard on `127.0.0.1:3000`, everything else gets the decoy site. DoT (853)
and DoQ (UDP 3452) stay with AdGuard. AdGuard trusts `127.0.0.0/8` as a proxy, so it still sees
each client's real address (allow-list, query log) and the ClientID in the path
(`/dns-query/srv1-moscow`, used by Server 1).

```bash
ansible-playbook site.yml -l s2-lt --tags adguard,decoy_site
```

(`adguard_doh_via_nginx: true`, `decoy_doh_port: 3452` in host_vars.) DoH is down for a few seconds
between the two roles; Server 1 falls back to 1.1.1.1 meanwhile (runbook 05).

Admin UI from now on: `http://10.99.0.12:3000` over the management tunnel (panels page).

Check: `https://<s2-domain>:3452/` shows the decoy site, `/login.html` → 404; the `s2-doh` probe
stays green; AdGuard's query log shows `srv1-moscow` for Server 1's queries.

Undo: `adguard_doh_via_nginx: false`, `decoy_doh_port: 0`; in `AdGuardHome.yaml` (AdGuard stopped)
set `port_https: 3452`; re-run both tags.

## 3. fail2ban removed

It watched SSH (public SSH is off since 2026-11-22: 0 bans possible from outside) and 3x-ui's
per-client IP limit (no client has one). ~30 MB of RAM on a 1 GB server.
`common_remove_packages: [fail2ban]`, `--tags common`. If an IP limit is ever set in the panel,
3x-ui needs fail2ban again.

## 4. Leftover acme.sh cron job

Root's crontab still ran `/root/.acme.sh/acme.sh --cron` daily although acme.sh was removed on
2026-11-22 (certbot does the certificates). Line removed by hand (`crontab -e`), nothing else.
