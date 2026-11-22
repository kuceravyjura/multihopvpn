# ADR 0001: separate management WireGuard network

**Status:** accepted

## Context

Both VPS servers expose their 3x-ui panels on public ports, protected only by an unusual port number
and a random URL path. SSH is public too. Monitoring and automation will need to reach the servers
from home, which sits behind NAT. The servers have 512 MB and 1 GB of RAM.

## Decision

Run a dedicated kernel WireGuard interface, `wg-mgmt`, on every host, using `10.99.0.0/24`.
The home control node dials out to both servers and keeps the tunnels alive. SSH, panels, node
exporter and Ansible use only this network. User VPN traffic never touches it.

## Consequences

- Admin surfaces disappear from the internet. The only public ports are VPN inbounds, DoH and the
  wg-mgmt UDP port, which ignores packets without a valid key.
- Kernel WireGuard costs almost no memory, which matters on the 512 MB server.
- Home being offline does not affect users; only management access pauses.
- If wg-mgmt breaks, access falls back to the provider's web console. Public SSH stays open until
  wg-mgmt access has been proven (`firewall_ssh_public`).
- For now the home peer is the WSL Ubuntu on the PC, where Ansible runs. WSL stops when idle, so the
  tunnel exists while WSL runs; `PersistentKeepalive = 25` brings it up within seconds of starting WSL.
  Verified 2026-11-22: home → both servers and staging, and Server 1 → Server 2 (through zapret's queue).
- wg-easy is not reused for this, because it is being removed (phase 5) and mixes management with users.
