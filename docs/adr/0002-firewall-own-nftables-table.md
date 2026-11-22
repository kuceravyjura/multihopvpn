# ADR 0002: firewall in its own nftables table

**Status:** accepted

## Context

Both servers run Docker (for wg-easy), which installs its own rules through iptables-nft. The usual
`/etc/nftables.conf` starts with `flush ruleset`, and Debian's `nftables.service` runs `nft flush ruleset`
when it stops. Either would delete Docker's NAT rules and break wg-easy until Docker restarts.
ufw is another option, but it is harder to template and review than a single nft file.

## Decision

- All host rules live in one table, `inet homelab`, with an input chain and `policy drop`.
- The file replaces only that table (`table inet homelab` / `delete table inet homelab` / define)
  and never flushes the whole ruleset.
- A systemd drop-in changes `nftables.service` so stopping it deletes only `inet homelab`.
- Host services are filtered in an input chain. Docker-published ports are DNATed to containers and
  pass the forward hook instead, so they never reach input. The 2026-11-21 inventory found Portainer,
  homer and the wg-easy UI published this way on Server 2. They are listed in
  `firewall_docker_mgmt_ports` and dropped in a forward chain unless they arrive over wg-mgmt. The rule
  matches only DNATed connections (`ct status dnat`), so VPN users' traffic to the same port numbers
  elsewhere is untouched.
- Other tools' tables are left alone: Server 1 runs zapret (`inet zapret`, nfqueue), Server 2 runs
  fail2ban (`inet f2b-table`). nftables evaluates every table's chains; a packet must be accepted by all.
- Every change is applied behind a rollback timer: if Ansible can't reconnect within 30 s, a systemd
  timer deletes the table after 120 s.

## Consequences

- Host firewall and Docker coexist. When Docker is removed, nothing changes in the firewall.
- `nft list table inet homelab` shows the whole host policy in one place, generated from the port
  lists in `host_vars`.
- No fail2ban on Server 1: with key-only SSH and SSH eventually reachable only over wg-mgmt, it would
  add memory use on the 512 MB server for little gain. The existing fail2ban on Server 2 stays until
  public SSH is closed there, then it can be removed.
