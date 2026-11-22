# Runbook 06: move wg-easy users to 3x-ui without touching their devices

Done on Server 2 on 2026-11-22 (phase 5). The users kept their configs; one reconnected within
seconds of the switch.

## Idea

A WireGuard client only checks "is the server at this address and port, with this key". A 3x-ui
WireGuard inbound with wg-easy's **server key**, **port** and every peer's **public key, preshared
key and address** looks exactly like wg-easy to the devices.

## Steps

1. **Read wg-easy** (`/root/.wg-easy/wg0.json`, `wg show`): clients, addresses, preshared keys,
   MTU, DNS, who is active. Server 2: 8 clients, all with preshared keys, 10.8.0.x, MTU 1420,
   DNS 1.1.1.1, full tunnel.
2. **Build the 3x-ui import file** on the server from `wg0.json` (keys never printed). Copy it into
   the git-ignored `backups/phase5/`:
   - port 51820, wg-easy's server key, MTU 1420, sniffing on, **disabled**;
   - client names `wge-<name>` (names are unique panel-wide), original name in the client comment.
3. **Rehearse on staging:**
   - import the file in staging's panel and enable it;
   - from WSL, connect with one idle peer's real keys (temporary interface, only test IPs routed);
   - check the handshake, UDP DNS, HTTPS and a download.
4. **Import on the real panel, as a local inbound only.**
   - **Not a node.** On 2026-11-22 the import also created a node copy that synced to Server 1, and
     deleting it set off a sync storm (see the postmortem).
   - Afterwards check that exactly one inbound exists on the port, with `node_id` null.
5. **Before stopping wg-easy:**
   - pull a fresh backup;
   - confirm that the enabled local inbounds in the panel database match the live `config.json`.
6. **Switch:**
   - stop the container and keep it from starting at boot:
     `docker update --restart=no wg-easy && docker stop wg-easy`;
   - switch the inbound on in the panel right away. 3x-ui adds it live, without restarting Xray.
7. **Verify:** Xray listens on the port, the active peers show Online in the panel, traffic flows,
   no errors in the log.

## Rollback

Switch the inbound off in the panel, then `docker start wg-easy`. Both take seconds.

## Later (after a quiet week: 2026-11-29)

- Remove the wg-easy container and image, and the `/root/.wg-easy` data. Keep a copy in a backup first.
- Remove Docker from Server 2 if nothing else uses it.
- In Ansible: drop `firewall_docker_mgmt_ports` (51821) and the Docker-bridge DNS rules, and set
  `common_ip_forward: false`.
- Delete the leftover `xray-core` image and volumes (planned for 2026-11-28 anyway).
