# ADR 0005: monitoring on Server 2, a watcher on Server 1, Grafana at home

**Status:** accepted (2026-11-22)

## Context

The plan put Prometheus, Grafana and Alertmanager on a home VM. Four facts found while building it:

- **The home PC is off every night** (about 00:00–07:00 GMT+1). Home-based alerting would sleep
  exactly when nobody watches.
- **Server 2** (Lithuania, 1 GB) is always on and reaches Telegram's API (HTTP 302 in 0.3 s).
- **Server 1** (Moscow, 512 MB) cannot even open a TCP connection to Telegram's API. That is an
  IP-level block, which zapret cannot work around.
- **healthchecks.io**, the plan's external dead man's switch, never delivered its sign-up email.

## Decision

- **Prometheus + Alertmanager + blackbox exporter on Server 2**, from Ubuntu packages:
  - systemd memory caps of 300 / 64 / 64 MB;
  - 15 days or 1 GB of history;
  - Prometheus listens on wg-mgmt only; Alertmanager on localhost only, with its gossip port off.
- **Alerts go to Telegram** from Server 2. The bot token and chat id are in the vault.
- **Probes in both directions:**
  - Server 1's blackbox exporter checks Server 2's public services from Moscow: vless, the relay,
    DoT, a real DoH lookup, the decoy site, certificates.
  - Server 2's checks Server 1's from Lithuania.
- **Dead man's switch on Server 1:**
  - a one-minute timer checks three things: Server 2's Prometheus answers, it evaluates rules (the
    always-firing Watchdog alert), and it has an Alertmanager;
  - after 3 failures it pushes to **ntfy.sh**, which Server 1 can reach directly, and once more on
    recovery;
  - the secret topic is in the vault.
- **Grafana at home** reads Server 2's Prometheus over wg-mgmt. It is for viewing only, and the
  history is complete even after a night with the PC off.

## Consequences

- **Cost on Server 2:** monitoring uses about 30–80 MB in practice. Measured right after start:
  16 / 13 / 2 MB.
- **Gap:** if both servers go down at once, no alert is sent. That is accepted: nothing would work
  for anyone, so it would be noticed directly.
- **The watcher is monitored too:** its timer is in node_exporter's unit list, so Server 2 alerts on
  Telegram if Server 1's watcher stops.
- **Tested end to end on staging:**
  - Telegram about 1.5 min after x-ui stopped (the plan asks for under 2);
  - ntfy about 4 min after Prometheus stopped.
