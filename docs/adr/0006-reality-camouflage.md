# ADR 0006: Reality camouflage: borrow a site that matches the address

**Status:** accepted (relay hop switched 2026-11-24)

## Context

A Reality port pretends to be some real HTTPS site (the *target*). Anyone who is not a VPN client,
including a censor's active probe, is passed through to that site and sees its real handshake and
certificate. That only convinces if the borrowed site plausibly lives at that address.

A subnet scan of both servers (RealiTLScanner, run from home, 2026-11-24) and the panel settings
showed:

| Port | Pretended to be | Problem |
|---|---|---|
| Server 2 relay inbound (1111) | `www.ya.ru` | A Yandex name on a Lithuanian VPS. This hop crosses the Russian border and carries all foreign traffic of Server 1's users. Weakest spot. |
| Server 2 user inbound (8443) | `www.microsoft.com` | Foreign site on a foreign address; weak but consistent. |
| Server 1 user inbounds (8443, 11139) | `ya.ru` / `www.microsoft.com` | ya.ru on a Russian address is consistent. |

Server 2's subnet had no genuine neighbor: the candidates were other people's Reality servers
(fake `github.com`, `yahoo.com`, `cloudflare.com` certificates) and decoy pages. Server 1's subnet
has real Russian shop sites.

Options, strongest first:

1. **Own site ("self-steal")**: the target is the server's own nginx with a real certificate for
   its own domain. Name, address and certificate all genuinely belong together.
2. **A real neighbor** in the same subnet, vetted (DNS points to it, TLS 1.3, HTTP/2, X25519, a real
   page, no redirect).
3. **A popular Russian site** (ya.ru, vk, rutube): only on a Russian address.

Changing the name of a user-facing inbound means new configs on every device, which these users
cannot do. The relay hop is server-to-server: only Server 1's outbound changes.

## Decision

- **Relay hop: own site.** Server 2's relay inbound now forwards to its own nginx decoy site
  (`decoy_site` role: a generated small-business page, TLS 1.3, HTTP/2, Let's Encrypt), and Server 1
  sends Server 2's domain as the name.
- **Switch without an outage:** Server 2 first accepts both names, Server 1 then switches, and the
  old name is removed later in a separate step.
- **User-facing inbounds stay as they are.** New inbounds follow the order above; Server 1's own
  domain makes option 1 possible there too.
- **Every target is watched:** a blackbox probe from Moscow (`reality_target`) requires the fake
  site over TLS 1.3 + HTTP/2. A plain TCP check stays green when the target is broken; this one
  does not (tested on staging by stopping nginx).

## Consequences

- An active probe of port 1111 with the relay's name gets an ordinary business site with a valid
  certificate for that name and address.
- Server 2's nginx is now part of the VPN path: if it stops, the relay's camouflage handshake
  fails. The probe alerts on that; nginx is enabled at boot and managed by Ansible.
- The certificate renews through certbot's nginx plugin, unchanged (`certbot renew --dry-run`
  passed with the new site).
- While both names are accepted, a probe using `www.ya.ru` on 1111 still gets Server 2's site, a
  mismatch. Removing the old name ends that; three stale clients on that port (last online
  February-August) would stop working then.
- The two DuckDNS names share a prefix and are free dynamic DNS; a cheap real domain would be
  stronger. The domains stay in the vault.

How to change or undo: [runbook 10](../runbooks/10-reality-camouflage.md).
