# Runbook 07: monitoring and alerts

The design is in [ADR 0005](../adr/0005-monitoring-placement.md). Roles involved: `node_exporter`,
`blackbox_exporter`, `monitoring`, `watcher`.

## What alerts you

| Alert | Fires when | Channel |
|---|---|---|
| HostDown | a server's node_exporter is unreachable over wg-mgmt for 2 min (server or tunnel down) | Telegram |
| ServiceDown | for 1 min, one of these is not active: x-ui, AdGuardHome, nginx, zapret, wg-mgmt, the monitoring services, or the backup/watcher timers | Telegram |
| ProbeFailed | a public port or the DoH lookup fails for 2 min (checked from the other server) | Telegram |
| DiskAlmostFull / MemoryHigh | over 85 % / 90 % for 10 min | Telegram |
| CertExpiringSoon | the domain certificate (DoH, decoy site) expires in under 14 days | Telegram |
| ShortCertExpiringSoon | Server 1's 6-day IP certificate has under 1.5 days left (renewal failing) | Telegram |
| (watcher) | Server 2's Prometheus/Alertmanager is gone for 3 checks in a row | ntfy push |

Telegram messages show [prod] or [staging]. Resolved ones start with "Resolved:".

## Look at it

- **Prometheus:** `http://10.99.0.12:9090` over the homelab-mgmt tunnel. See Alerts, Targets and Graph.
- **The watcher on Server 1:** `journalctl -u homelab-watcher -n 5`.
- **Grafana at home:** to be added.

## Add a probe

1. Add an entry to `monitoring_probes` in `host_vars/s2-lt.yml`:
   `{name, prober: s1-msk|s2-lt, module: tcp_connect|doh|https_reachable, target, cert: normal|shortlived}`.
   Addresses come from the vault.
2. Apply it: `ansible-playbook site.yml -l s2-lt --tags monitoring`.

## Test delivery

**Staging** has Telegram switched off. To test delivery anyway:

```bash
ansible-playbook site.yml -l vm-staging --tags monitoring -e "alertmanager_telegram_bot_token={{ vault_telegram_bot_token }}"
ssh ops@192.168.0.70 sudo systemctl stop x-ui      # a message in ~1.5-2 min
ssh ops@192.168.0.70 sudo systemctl start x-ui     # "Resolved"
ansible-playbook site.yml -l vm-staging --tags monitoring   # Telegram off again
```

**Watcher:**

1. On staging, set `watcher_enabled: true` with a target.
2. Stop staging's Prometheus. A push should arrive in about 3–4 min.
3. Afterwards, turn it off again: `systemctl disable --now homelab-watcher.timer`.

## Known quirks

- **Package default config at install:** installing Prometheus first runs the package's own config,
  which scrapes `localhost:9100`. On 2026-11-22 that produced one false HostDown. HostDown now
  ignores targets without a `host` label.
- **`force_handlers = True`:** Ansible runs with it, so a failed run still applies the restarts it
  had already triggered. Staging once ran on stale configs because those restarts were lost.
