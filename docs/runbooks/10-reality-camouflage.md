# Runbook 10: change what a Reality port pretends to be

Why and which option: [ADR 0006](../adr/0006-reality-camouflage.md). Tool:
`scripts/xray-reality-camouflage.py` (edits the 3x-ui database; saves a copy first).

## Current state (2026-11-24)

| Where | Setting |
|---|---|
| Server 2 relay inbound, port 1111 | target `127.0.0.1:443` (own decoy site); names: `www.ya.ru` **and** `<s2-domain>` |
| Server 1 outbound `xhttptest-rurelay` | name `<s2-domain>` |
| Server 2 nginx | `decoy_site` role, TLS 1.3 + HTTP/2, Let's Encrypt via certbot |

Left: remove `www.ya.ru` from the relay inbound (step 4 below) and decide about the three stale
clients on that port.

## Look

```bash
scp scripts/xray-reality-camouflage.py vps2:/tmp/
ssh vps2 sudo python3 /tmp/xray-reality-camouflage.py show /etc/x-ui/x-ui.db
```

## Switch the relay hop to the own site (how it was done)

Staging first (it is a copy of Server 2: `ansible-playbook site.yml -l vm-staging --tags decoy_site`).

1. **Fake site:** `ansible-playbook site.yml -l s2-lt --tags decoy_site --check --diff`, then
   without `--check`. Check from outside: `curl -s --tlsv1.3 https://<s2-domain>/` gives HTTP/2 and
   the site's title; `sudo certbot renew --dry-run` succeeds.
2. **Server 2 accepts both names.** Before the restart, compare the database with the running
   config (same inbound count, see the postmortem of 2026-11-22):
   ```bash
   sudo python3 /tmp/xray-reality-camouflage.py inbound /etc/x-ui/x-ui.db 1111 127.0.0.1:443 www.ya.ru,<s2-domain>
   sudo systemctl restart x-ui
   ```
3. **Server 1 sends the new name:**
   ```bash
   sudo python3 /tmp/xray-reality-camouflage.py outbound /etc/x-ui/x-ui.db xhttptest-rurelay <s2-domain>
   sudo systemctl restart x-ui
   ```
   Check:
   - on Server 2, `rurelay` is online (Clients list, or `client_traffics.last_online`);
   - relay-listed sites (Telegram, YouTube) open through a Server 1 inbound;
   - `doubleclick.net` asked through a Server 1 inbound answers `0.0.0.0` (AdGuard via the relay);
   - all probes are green.
4. **Later: drop the old name** on Server 2:
   ```bash
   sudo python3 /tmp/xray-reality-camouflage.py inbound /etc/x-ui/x-ui.db 1111 127.0.0.1:443 <s2-domain>
   sudo systemctl restart x-ui
   ```

Each restart reconnects that server's users within seconds; their apps do it on their own.

## Undo

Put the old values back (keeps the traffic counters):

```bash
# Server 1
sudo python3 /tmp/xray-reality-camouflage.py outbound /etc/x-ui/x-ui.db xhttptest-rurelay www.ya.ru && sudo systemctl restart x-ui
# Server 2
sudo python3 /tmp/xray-reality-camouflage.py inbound /etc/x-ui/x-ui.db 1111 www.ya.ru:443 www.ya.ru && sudo systemctl restart x-ui
```

Full copies from before each change: `/etc/x-ui/x-ui.db.bak-camouflage-<time>` on each server
(stop x-ui, copy over `x-ui.db`, start). The old nginx site: `/etc/nginx/sites-available/default.pre-decoy`.

## Watch

Probe `s2-relay-camouflage` (from Moscow, module `reality_target`): the fake site must answer on
1111 with the relay's name over TLS 1.3 and HTTP/2. `ProbeFailed` alerts in Telegram if not, for
example when nginx is down or the certificate is broken.

## Choosing a target for a new inbound

1. The server's own domain plus `decoy_site` (Server 1 has its own domain too, in the vault).
2. Else a neighbor: run RealiTLScanner **from home**, not from the VPS (its README warns a cloud scan
   can get the server flagged):
   ```bash
   ./RealiTLScanner -addr <server-ip>/24 -port 443 -thread 16 -timeout 5 -out s.csv
   ```
   Keep only names whose DNS points to that same neighbor, that serve a real page over TLS 1.3 +
   HTTP/2 with X25519 (`curl --tlsv1.3 --curves X25519 --http2 --resolve name:443:ip`), and don't
   redirect elsewhere. Skip big brand names on small hosting addresses: those are other VPNs.
3. Else, on a Russian address only, a popular Russian site.
