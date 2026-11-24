# Runbook 12: relay by Russia's block list

Why: [ADR 0008](../adr/0008-relay-by-block-list.md). Tools: role `geodata`
(`/usr/local/sbin/homelab-geodata`, timer 04:30) and `scripts/xray-relay-blocklist.py`.

## What is in place (Server 1)

```
rule 5-6  hand-made relay list (36 domains + geoip:facebook, geoip:telegram)   -> relay   (unchanged)
rule 7    Relay: Russia's block list (ext:geosite_RU.dat:ru-blocked)           -> relay   (new)
rule 8-9  geoip:private, bittorrent                                            -> blocked
```

## Look

```bash
ssh vps1 sudo python3 /tmp/xray-relay-blocklist.py show /etc/x-ui/x-ui.db   # copy the script first
ssh vps1 'systemctl list-timers homelab-geodata.timer; journalctl -u homelab-geodata -n 5'
ssh vps1 cat /var/lib/prometheus/node-exporter/homelab_geodata.prom
```

In Telegram: `/check <site>` shows whether a site is on the list and what users get.

## Refresh the list now

```bash
ssh vps1 sudo homelab-geodata            # only if upstream changed; restarts x-ui then
ssh vps1 sudo homelab-geodata --force    # even if unchanged
```

It refuses a file that fails the checksum or `xray -test`, and restores the previous file if Xray
doesn't come back with all its inbound ports.

## A site is blocked but not on the list

Add it to the hand-made relay rule in the panel (Xray Settings → Routing, the first relay rule),
then check: `/check <site>` → "Server 1 users ✅".

## Undo

```bash
scp scripts/xray-relay-blocklist.py vps1:/tmp/
ssh vps1 'sudo python3 /tmp/xray-relay-blocklist.py remove /etc/x-ui/x-ui.db && sudo systemctl restart x-ui'
# the previous list file, if a refresh is the problem:
ssh vps1 'sudo mv /usr/local/x-ui/bin/geosite_RU.dat.prev /usr/local/x-ui/bin/geosite_RU.dat && sudo systemctl restart x-ui'
# stop the nightly refresh: geodata_enabled: false does not uninstall; disable the timer:
ssh vps1 sudo systemctl disable --now homelab-geodata.timer
```

Database copies from before each change: `/etc/x-ui/x-ui.db.bak-blocklist-<time>`.

## Rehearsed on staging

Matching (LinkedIn, X caught; GitHub, Wikipedia not), memory (+8 MB), a forced update with
restart, a corrupt file with a valid checksum (rejected before any restart, `last_check_ok 0`),
and an unchanged run (no restart).
