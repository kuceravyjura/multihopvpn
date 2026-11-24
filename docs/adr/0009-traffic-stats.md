# ADR 0009: Traffic per user from the 3x-ui databases

**Status:** accepted (staging 2026-11-24; servers pending approval)

## Context

Phase 6 left one gap: who uses how much, and how busy the relay hop is. Xray has a statistics API
(127.0.0.1:62789), but 3x-ui reads it itself and **resets** the counters every few seconds, adding
them to running totals in `x-ui.db`. A second reader would either steal those numbers (reset) or
see almost nothing (no reset).

What `x-ui.db` holds:

- per inbound: running up/down totals. Most users have one WireGuard inbound each, with the
  person's name as the remark, so per inbound is per person;
- per VLESS client: up/down and "last online";
- rows that belong to node-sync copies (`node_id` set) carry garbage from the 2026-11-22 incident
  (e.g. 60 PB); they are not this server's traffic;
- outbound statistics (relay vs direct) are off in the template.

## Decision

- **`homelab-xui-exporter`** (role `xui_exporter`) on both servers reads `x-ui.db` **read-only**
  on each scrape and serves Prometheus metrics on the management tunnel (port 9117). Only the
  server's own inbounds and their clients are exported.
- **Relay traffic without new settings:** Server 1's relay outbound is the client `rurelay` of
  Server 2's relay inbound, so its counters on Server 2 are the relay hop.
- **Grafana "Traffic" row:** throughput per user now, totals for 24 h and 7 days per user and per
  server, the relay hop, and VLESS clients' last seen.
- No panel change, no restart. Turning on outbound statistics stays an option.

## Consequences

- Runs as root (the database is root-only: it holds every client key) with a locked-down unit;
  about 10 MB.
- Counters reset when a user's traffic is reset in the panel; Grafana uses rate/increase, which
  handle resets.
- Inbound remarks (people's names) end up in Prometheus and Grafana: both private (Server 2 over
  the tunnel, the PC). Not in the repository.
- Found on the way: Python's `http.server` looks up the reverse DNS name of its own address at
  start, which took 30-60 s on the tunnel address; both agents now skip it (start in < 1 s).
