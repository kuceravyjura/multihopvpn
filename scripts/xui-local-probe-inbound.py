#!/usr/bin/env python3
"""Add (or remove) a local-only proxy inbound in a 3x-ui panel, for the reachability agent.

  add    <x-ui.db> [port]   SOCKS/HTTP ("mixed") inbound on 127.0.0.1:<port> (default 10808),
                            no login (only this server can reach 127.0.0.1), sniffing on, so the
                            panel's routing rules apply to it exactly as to a VPN user.
  remove <x-ui.db> [port]
Idempotent. Saves a copy of the database first. Restart x-ui afterwards.
Why: ADR 0007, runbook 11. The remark below is what the panel shows."""
import json, sqlite3, sys, time

REMARK = "reach probe: local only (homelab-reach, ADR 0007)"
if len(sys.argv) < 3 or sys.argv[1] not in ("add", "remove"):
    sys.exit(__doc__)
mode, db = sys.argv[1], sys.argv[2]
port = int(sys.argv[3]) if len(sys.argv) > 3 else 10808
tag = f"inbound-127.0.0.1:{port}"
con = sqlite3.connect(db)
have = con.execute("select id from inbounds where tag=?", (tag,)).fetchone()
busy = con.execute("select tag from inbounds where port=? and tag<>?", (port, tag)).fetchone()

if mode == "add" and have:
    print(f"already there: {tag}"); sys.exit(0)
if mode == "remove" and not have:
    print(f"not there: {tag}"); sys.exit(0)
if mode == "add" and busy:
    sys.exit(f"port {port} is used by {busy[0]}")

dst = f"{db}.bak-reach-{time.strftime('%Y%m%d-%H%M%S')}"
con.execute(f"vacuum into '{dst}'")
print(f"backup: {dst}")
if mode == "add":
    settings = {"auth": "noauth", "accounts": [], "udp": False, "ip": "127.0.0.1"}
    sniffing = {"enabled": True, "destOverride": ["http", "tls", "quic"], "metadataOnly": False, "routeOnly": False}
    con.execute("insert into inbounds (user_id, up, down, total, remark, enable, expiry_time, listen, port, "
                "protocol, settings, stream_settings, tag, sniffing) values (1, 0, 0, 0, ?, 1, 0, '127.0.0.1', ?, "
                "'mixed', ?, '', ?, ?)",
                (REMARK, port, json.dumps(settings), tag, json.dumps(sniffing)))
    print(f"added {tag}: '{REMARK}'")
else:
    con.execute("delete from inbounds where tag=?", (tag,))
    print(f"removed {tag}")
con.commit()
print("now: systemctl restart x-ui")
