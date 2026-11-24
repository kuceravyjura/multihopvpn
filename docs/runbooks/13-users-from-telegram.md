# Runbook 13: users from Telegram

Why and how: [ADR 0010](../adr/0010-users-from-telegram.md).

## Everyday

In the bot: `/menu`.

| Button | What happens |
|---|---|
| ➕ New user | name → server → a new WireGuard inbound for that person; you get `Name-dev1.conf` + QR |
| 👥 Users | everyone with traffic and number of devices; tap a person |
| 📱 Add device | one more client in that person's inbound; you get its `.conf` + QR |
| 🔁 Send config | resend a device's config (asks which device if there are several) |
| ⏸ / ▶️ | disable or enable the person (all devices) |
| 🗑 Delete | removes the person's inbound and every device; asks first |

Hand-over: PC users import the `.conf` in WireSock or WireGuard; phones scan the QR in the
WireGuard app (+ → Scan from QR code).

Nothing restarts: 3x-ui applies these changes live. Tested on staging (2026-11-24): adding and
removing a device rewrites only that person's inbound; Xray's process stayed the same throughout.

## Setup (done 2026-11-24)

1. Tokens, one per server, scope `node-sync`, straight into the vault:
   `/usr/local/x-ui/x-ui setting -getApiToken -tokenName homelab-bot -tokenScope node-sync` (on the
   server, as root; the full path: on some installs `x-ui` alone is the menu script) → `vault_xui_token_s1`, `vault_xui_token_s2`. Plus `vault_s1_domain`.
2. `firewall_user_udp_range: "20000-29999"` in both servers' host_vars;
   `ansible-playbook site.yml -l s1-msk --tags firewall`, same for `s2-lt` (disarm after).
3. `ansible-playbook site.yml -l s2-lt --tags reach_bot`: installs `qrencode`, the modules, and
   reads each panel's port and secret path from its database at deploy time.

## Rotate a token

On the server: the same `-getApiToken -tokenName homelab-bot` command prints a new token and
invalidates the old one. Put it in the vault, re-run the `reach_bot` tag.

## Undo

- Remove the panels from the bot: delete `vault_xui_token_s1/_s2`, re-run `--tags reach_bot`.
- Revoke the tokens in each panel (Settings → API tokens) or rotate them.
- `firewall_user_udp_range: ""` and re-run `--tags firewall` (users created in the range would
  stop connecting).
