# ADR 0010: WireGuard users from Telegram

**Status:** accepted (live 2026-11-24)

## Context

New users meant clicking through the panel: an inbound, keys, a free port, sniffing, the firewall,
then exporting a config. The users are not technical; in practice WireGuard (WireSock, the official
app) has proven faster and more stable for them than any VLESS client tried (v2rayN, Hiddify,
Karing and others). WireGuard has no subscription mechanism, so a config, once handed out, must
stay valid.

How users are organised today: one WireGuard inbound per person (remark = the person), one client
per device. In 3x-ui 3.11 WireGuard peers are full clients (name, keys, address).

Tested on staging (3x-ui 3.11.0): an inbound added, changed or deleted through the API is applied
**live**, without restarting Xray; its port is bound within 2 s.

## Decision

- **Telegram buttons** in the existing bot (Server 2): `/menu` → ➕ New user (name, server) →
  the bot creates the person's inbound and sends `Name-dev1.conf` and a QR code. 👥 Users: everyone
  with traffic and devices; per user 📱 add device, 🔁 send config, ⏸/▶️ disable/enable,
  🗑 delete (with confirmation).
- **The panel's own API**, with a token of scope **`node-sync`** per server: it can only list,
  add, update and delete inbounds and clients (and restart Xray), not touch settings or logins.
  Created with `x-ui setting -getApiToken -tokenName homelab-bot -tokenScope node-sync`, kept in
  the vault. Calls go over the management tunnel.
- **Configs in the panel's own shape** (DNS 1.1.1.1, which Server 1 sends to AdGuard; no custom
  MTU), so they behave like the ones users already have.
- **The server's domain as `Endpoint`** in new configs: an IP change (new provider) needs a DNS
  update, not new configs. Existing configs are untouched.
- **One UDP range per server for user inbounds** (`firewall_user_udp_range: 20000-29999`): new
  users need no firewall change. Silent to anyone without a key.
- VLESS with a subscription stays an optional later addition.

## Consequences

- Adding or removing a person takes seconds and interrupts nobody.
- The bot is now powerful: it answers only the owner's chat id; the token cannot change panel
  settings or logins; rotate it with the command above if the bot host is ever compromised.
- A `.conf` (with the device's private key) passes through the owner's Telegram chat; that is how
  it would be handed over anyway.
- Proven on staging: every button; a generated config made a real WireGuard handshake and reached
  the internet. On the servers: the bot reads both panels (13 and 9 users).
- Existing users appear in the list and can be resent or managed; nothing about them changes
  unless a button is pressed.

Operation: [runbook 13](../runbooks/13-users-from-telegram.md).
