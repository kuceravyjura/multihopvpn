# ADR 0007: Website reachability checker

**Status:** accepted (live 2026-11-24)

## Context

The relay list on Server 1 decides which sites go through Server 2. Nobody noticed when a site
became blocked in Russia but was missing from that list: users just found it "not working". The
owner lives outside Russia, so checking by hand from a Russian connection is not possible.

What can be measured, and from where:

| Question | Where it can be answered |
|---|---|
| Is it blocked in Russia? | Server 1, directly from its Moscow datacenter address |
| What do Server 1's users get? | Server 1, through its own Xray routing (same rules as users) |
| Is the site itself up? | Server 2, directly from Lithuania |
| Is it officially blocked, incl. home and mobile networks? | Russia's block lists: runetfreedom `ru-blocked` (antifilter community + re:filter) and `ru-blocked-all` |

Datacenter networks are not always filtered like home and mobile ones (discord.com opened directly
from the Moscow datacenter on 2026-11-24), so the live test and the lists answer different
questions; both are shown.

## Decision

- **Agent `homelab-reach`** (role `reach`) on both servers: Python + curl, listening on the
  management tunnel only (port 9116). Each check reports the stage it reached: dns, tcp (no
  connection), tls (handshake stalls: typical block by name), http (no answer), or ok.
  `/check?site=` on demand; `/metrics` for a watched list of 15 sites every 10 minutes.
- **The "user" path** goes through a local-only proxy inbound in Server 1's panel
  (`127.0.0.1:10808`, remark "reach probe: local only"), so the test follows the users' routing.
- **Telegram bot** (role `reach_bot`) on Server 2, using the alert bot, answering only the owner:
  `/check <site>` (both agents, the block lists, a verdict) and `/sites`. Long polling, no open port.
  The lists are downloaded every 12 hours.
- **Alerts:** `SiteBlockedForUsers` (users fail, Lithuania works: add to the relay list),
  `SiteNowBlockedInRussia` / `SiteNowOpenInRussia` (change against a day ago, information),
  `ReachAgentDown`. Grafana: a table and a history per site.

## Consequences

- First run found LinkedIn and X blocked from Moscow and missing from the relay list: Server 1's
  users could not open them. That led to the relay rule driven by `ru-blocked` on top of the
  hand-made list ([ADR 0008](0008-relay-by-block-list.md)), after which both opened for users.
- Memory: agent ~12-22 MB, bot ~20 MB (caps 60 MB). Server 1 has 512 MB.
- A single datacenter vantage point in Moscow: home and mobile networks can block more. The block
  lists cover that part.
- The probe inbound is a panel object: it is in the nightly backups and must exist after a restore
  (`scripts/xui-local-probe-inbound.py add`, idempotent).

Operation: [runbook 11](../runbooks/11-reachability.md).
