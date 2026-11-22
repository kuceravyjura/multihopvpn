# ADR 0004: per-user DNS identity through the relay

**Status:** proposed (2026-11-22). Lab-proven on staging; not on the real servers yet.

## Context

Since phase 4, every Server 1 user appears in AdGuard as one client, `srv1-moscow`: Xray's DNS
module on Server 1 asks AdGuard on behalf of everyone and caches the answers. The owner wants to
see each person (one Server 1 WireGuard inbound = one person; several peers = that person's
devices) as a separate AdGuard client, without configuring devices by hand, and to create and
remove users with a tool (PC first, later a Telegram bot).

## Decision

Identity is carried in the **DNS destination address**, from a private range used for nothing
else: `10.53.0.0/24`, one address per device.

- **WireGuard device:** its config gets `DNS = 10.53.0.N`. Server 1 sends 10.53.0.0/24 port 53
  through the existing relay. The address travels unchanged inside the relay.
- **vless user** (apps pick their own DNS): Server 1 matches the user and sends port 53 to a
  small `freedom` outbound with `redirect: 10.53.0.N:53` and `dialerProxy` = the relay.
- **Server 2:** `ip route add local 10.53.0.0/24 dev lo` makes the whole range local. Xray
  delivers 10.53.0.N:53 locally, and the kernel uses 10.53.0.N as the source, so AdGuard sees
  the client as 10.53.0.N. An AdGuard client "Yarik" holds that person's addresses.
- Xray 26's `direct` outbound refuses private addresses (`finalRules: block geoip:private`), so
  Server 2 gets its own outbound `adguard-local` that allows exactly 10.53.0.0/24 port 53 and
  still blocks every other private address. Its rule sits above the WARP and private-IP rules.

Per person: one AdGuard client. Per vless user additionally: one outbound and one rule on
Server 1. Nothing per user on Server 2's Xray, and no firewall change.

## Lab result (staging, 2026-11-22)

A throwaway Xray played Server 1 with Server 1's real relay settings, pointed at staging's Xray
(a copy of Server 2):

| Simulated user | Normal name | Ad domain | Nonexistent | AdGuard client |
|---|---|---|---|---|
| WireGuard-style, DNS = 10.53.0.7 | NOERROR (UDP, TCP) | 0.0.0.0 | NXDOMAIN 50-130 ms | 10.53.0.7 |
| vless-style, asks 1.1.1.1, rewritten | NOERROR | 0.0.0.0 | NXDOMAIN 16-56 ms | 10.53.0.8 |

First query 1.3 s (relay connection setup), then 50-150 ms. Found on the way: `direct`'s
`finalRules` silently dropped the first attempt; hence `adguard-local`.

## Consequences

- These users bypass Server 1's DNS module: no shared cache and no 1.5 s fallback. If Server 2
  or the relay is down, they lose DNS (the `srv1-moscow` path keeps its fallback).
- Users whose configs still use another DNS server keep working, grouped as `srv1-moscow`.
  Migration is one new config per device.
- Server 2's panel holds Server 1's inbounds (node link, sync "all"), so the user tool must
  create inbounds in a way the link doesn't undo. To settle before the tool is built.
- Open: what "relay routing" in the inbound create form stores (not found on inbounds or nodes).
