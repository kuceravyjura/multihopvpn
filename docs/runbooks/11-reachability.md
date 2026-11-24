# Runbook 11: website reachability checker

Why and how it works: [ADR 0007](../adr/0007-reachability-checker.md).

## Use it

In Telegram (the alert bot, owner's chat only):

```
/check discord.com     test now: Moscow direct, Server 1's users, Lithuania; block lists; verdict
/sites                 the watched list (Moscow · users · Lithuania)
```

Over the management tunnel:

```bash
curl -G http://10.99.0.11:9116/check --data-urlencode site=discord.com   # Server 1: direct + user
curl -G http://10.99.0.12:9116/check --data-urlencode site=discord.com   # Server 2: direct
curl http://10.99.0.11:9116/metrics                                       # the watched list
```

Grafana, "Websites" row: the current table and each site's history for Server 1's users.

## Read the results

| Stage | Meaning |
|---|---|
| ok | an HTTP answer arrived |
| refused | the site answered 403/451: it turns this address away (OpenAI refuses Russian addresses). Not usable. |
| dns | the name did not resolve (every failure is retried once after 2 s first) |
| tcp | no connection: address blocked, or the site is down |
| tls | connected, but the TLS handshake stalled: the typical block by name (SNI) |
| http | TLS done, no answer in time: throttled or stalled |

| Moscow | Users | Lithuania | What to do |
|---|---|---|---|
| ❌ | ✅ | ✅ | nothing: the relay works for it |
| ❌ | ❌ | ✅ | add it to Server 1's relay rules (`SiteBlockedForUsers` alerts after 25 min) |
| ✅ | ❌ | ✅ | Server 1's routing is wrong for it (or the relay is down) |
| any | ❌ | ❌ | the site is down or blocks these servers |

## How often

| Path | Schedule |
|---|---|
| Server 1, through its routing (users) | every 10 min |
| Server 1, direct from Moscow | about weekly, random time and order (`reach_direct_interval`); `/check` on demand |
| Server 2, direct | every 10 min |

The Moscow column in Grafana shows the last weekly round. To change the rhythm, set
`reach_direct_interval` (seconds) in `host_vars/s1-msk.yml`.

## Change the watched list

`reach_sites` in `ansible/roles/reach/defaults/main.yml` (or per host), then
`ansible-playbook site.yml -l s1-msk --tags reach` and the same for `s2-lt`.

## After restoring Server 1's panel

The probe inbound lives in the panel database. If it is missing, the user path fails:

```bash
scp scripts/xui-local-probe-inbound.py vps1:/tmp/
ssh vps1 'sudo python3 /tmp/xui-local-probe-inbound.py add /etc/x-ui/x-ui.db && sudo systemctl restart x-ui'
```

## Remove it

`reach_enabled: false` / `reach_bot_enabled: false` in host_vars does not uninstall. To remove:
stop and disable `homelab-reach` (both) and `homelab-reach-bot` (Server 2), delete
`/usr/local/sbin/homelab-reach*`, `/etc/homelab-reach*`, the unit files; remove the probe inbound
(`xui-local-probe-inbound.py remove`, restart x-ui); drop `reach` from `monitoring_reach_targets`.
