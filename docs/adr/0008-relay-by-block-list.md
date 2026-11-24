# ADR 0008: Relay everything on Russia's block list, on top of the hand-made list

**Status:** accepted (live on Server 1 since 2026-11-24)

## Context

Server 1 sends traffic through the relay only for a hand-made list (36 domain entries plus two IP
groups). The reachability checker (ADR 0007) found on its first run that LinkedIn and X were blocked
from Moscow but missing from that list: Server 1's users could not open them.

runetfreedom publishes Russia's block lists as Xray geosite files, rebuilt several times a day:
`ru-blocked` (antifilter community + re:filter, ~73k domains) and `ru-blocked-all` (everything
known, ~700k). 3x-ui had downloaded one copy (`geosite_RU.dat`) once, a month earlier, and never
updated it.

The owner's point: the list can miss sites that don't work in Russia, so the hand-made list must stay.

Measured on staging (392 MB VM, Xray 26.10.21):

| Rule | Xray memory | Peak | Start |
|---|---|---|---|
| none | 31 MB | 40 MB | 2.4 s |
| `ru-blocked` | 39 MB | 43 MB | 5.8 s |
| `ru-blocked-all` | 79 MB | 144 MB | 18 s |

## Decision

- **Add** one rule, `Relay: Russia's block list (runetfreedom ru-blocked, updated nightly)`:
  `ext:geosite_RU.dat:ru-blocked` → relay. It sits right after the hand-made relay rules, which
  stay unchanged and keep priority, and before the block rules.
- **`ru-blocked`, not `ru-blocked-all`**: the full list's startup peak and 18 s restart are too
  much for a 512 MB server, and the curated list covers the services people use.
- **Nightly refresh** (role `geodata`, 04:30 server time): download, checksum, `xray -test` with
  the new file *before* any restart, restart x-ui only when the list changed, then check that every
  inbound port in Xray's config is bound; on any failure the previous file comes back.
  `BlockListStale` alerts when it fails or hasn't run for 2 days.

## Consequences

- LinkedIn and X opened for Server 1's users right after the switch; GitHub and ya.ru still go
  direct. Xray on Server 1: 43 MB after the restart (was 53-66 MB before, 296-318 MB available).
- New blocks are relayed automatically within a day, without editing the panel. Sites missing from
  every list still need the hand-made list; the checker's `SiteBlockedForUsers` points them out.
- Some listed sites still open directly from Moscow (datacenter networks are filtered less); they
  now go through Lithuania for everyone. Slightly more relay traffic, consistent behaviour for
  home and mobile users.
- At most one short x-ui restart per night, only when the list changed (users reconnect by themselves).
- The first DNS query after a restart may fall back to 1.1.1.1 while the relay connection opens;
  that is the designed fallback (runbook 05).

Operation and undo: [runbook 12](../runbooks/12-relay-block-list.md).
