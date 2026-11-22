# Runbook 05: DNS for Server 1 (Moscow) users through AdGuard

Live since 2026-11-22 on all Server 1 inbounds (phase 4).

## How it works

```
user device ──WG/vless──► Server 1 Xray
   DNS query to any server, port 53 ──► rule "user DNS (port 53)" ──► dns-out ──► Xray DNS module
      1) https://<s2-domain>:3452/dns-query/srv1-moscow   (1.5 s timeout)
         └─ rule "AdGuard DoH via relay" ──► xhttptest-rurelay ──► Server 2 ──► AdGuard
      2) 1.1.1.1 (only if AdGuard doesn't answer)
         └─ rule "DNS fallback leaves directly" ──► direct
```

- AdGuard sees the queries arriving from Server 2's own address, with ClientID `srv1-moscow`
  (its own entry in Clients and in the query log).
- If Server 2 or the relay is down, Moscow DNS falls back to 1.1.1.1 in ~1.5 s: no ad
  blocking, but the internet keeps working.
- The port-53 rule has no inbound list, so inbounds added later are covered automatically.
- Only plain DNS (port 53) is caught. Apps with their own encrypted DNS (browser "secure DNS",
  DoH/DoT to 443/853) bypass it, as everywhere.

## What users see when Server 2 is down (tested 2026-11-22)

Staging, with Server 1's exact live DNS config and staging's Xray stopped as "Server 2 down":
cached names answer at once; new names go to 1.1.1.1 (12 ms when Server 2 refuses, ~1.5 s when it
is silent); not one lookup failed; ads are not blocked during the outage. When Server 2 is back,
answers come from AdGuard again by themselves. Nothing to do on the devices or the servers.

Per-person AdGuard clients were considered and deferred for this reason (ADR 0004).

## Where it is in the panel (Server 1)

Xray Configs → **DNS** (2 servers), **Hosts** (Server 2's name → IP), **Outbounds** (`dns-out`),
**Routing** (four rules whose `ruleTag` starts with "Phase 4:"). Xray JSON has no comments; the
`ruleTag` is each rule's description.

- The 1.5 s timeout (`timeoutMs`) may not show in the DNS table. After editing that server in the
  panel, check **Advanced** that `"timeoutMs": 1500` is still there.
- A panel tab opened before a scripted change holds the old template: reload before clicking Save.

## AdGuard side (Server 2)

`dns.allowed_clients` includes `srv1-moscow`; Server 2's own IP is in `dns.ratelimit_whitelist`
(all Moscow users share it, the limit is 20 q/s per IP); a persistent client `srv1-moscow`.
Script: `scripts/adguard-allow-srv1.py` (stop AdGuard, run, start).

## Change or re-apply

```bash
# on the PC, from the template saved by the panel (sqlite: settings.xrayTemplateConfig)
python scripts/xray-dns-adguard.py template.json new.json <s2-domain> <s2-ip> ALL
# validate against the full config with Server 1's own binary, then write the template
# back to the panel (or paste it in Xray Configs → Advanced) and restart x-ui
xray run -test -config <full-config-with-changes>.json
```

For a canary, pass one inbound tag (e.g. `inbound-57265`) instead of `ALL`.

## Undo

1. Panel → Xray Configs → Advanced: paste the template saved before phase 4
   (`backups/phase4/s1-xray-template-before.json`, git-ignored) → Save → restart Xray.
   Or restore `/root/x-ui.db.bak-phase4-2026-11-22` on Server 1 (stop x-ui first).
2. AdGuard: `AdGuardHome.yaml.bak-phase4-2026-11-22` on Server 2 (stop, copy back, start).

## Check it works

- AdGuard → Dashboard → top clients: `srv1-moscow` with a steady query count.
- `ss -tn '( sport = :3452 )'` on Server 2: a connection from Server 2's own address = the relay.
- From a client on a Server 1 inbound: `nslookup doubleclick.net 1.1.1.1` → `0.0.0.0`;
  a nonexistent name → NXDOMAIN in under a second.
