#!/usr/bin/env python3
"""Change what a Reality inbound or outbound pretends to be. Edits the 3x-ui database directly.

  inbound  <x-ui.db> <port> <target> <name>[,<name>...]
      Every local (non node-copy) Reality inbound on <port>: set the target (where non-VPN
      handshakes are forwarded) and the accepted server names (SNI).
  outbound <x-ui.db> <tag> <serverName>
      The Reality outbound <tag> in the panel's Xray template: set the server name it sends.
  show     <x-ui.db>
      List Reality inbounds and outbounds with their target and names.

Add --dry-run to print the change without writing. A copy of the database is saved next to it
first (x-ui.db.bak-camouflage-<time>). Restart x-ui afterwards so Xray picks it up.
Used for the relay hop (ADR 0006, runbook 10)."""
import json, shutil, sqlite3, sys, time

args = [a for a in sys.argv[1:] if a != "--dry-run"]
dry = "--dry-run" in sys.argv
if len(args) < 2:
    sys.exit(__doc__)
mode, db = args[0], args[1]
con = sqlite3.connect(db)


def reality(ss):
    return ss.get("realitySettings") if ss.get("security") == "reality" else None


def show():
    for id_, port, tag, ss in con.execute("select id, port, tag, stream_settings from inbounds"):
        r = reality(json.loads(ss or "{}"))   # WireGuard inbounds have no stream settings
        if r:
            print(f"inbound  id={id_:<3} port={port:<6} {tag:20} target={r.get('target') or r.get('dest')} "
                  f"names={r.get('serverNames')}")
    tpl = json.loads(con.execute("select value from settings where key='xrayTemplateConfig'").fetchone()[0])
    for o in tpl.get("outbounds", []):
        r = reality(o.get("streamSettings", {}))
        if r:
            print(f"outbound {o['tag']:20} serverName={r.get('serverName')}")


def backup():
    if not dry:
        dst = f"{db}.bak-camouflage-{time.strftime('%Y%m%d-%H%M%S')}"
        con.execute(f"vacuum into '{dst}'")
        print(f"backup: {dst}")


if mode == "show":
    show()
elif mode == "inbound":
    port, target, names = int(args[2]), args[3], args[4].split(",")
    rows = con.execute("select id, tag, stream_settings from inbounds where port=? and "
                       "(node_id is null or node_id='')", (port,)).fetchall()
    rows = [(i, t, json.loads(s)) for i, t, s in rows if reality(json.loads(s or "{}"))]
    if not rows:
        sys.exit(f"no local Reality inbound on port {port}")
    backup()
    for id_, tag, ss in rows:
        r = ss["realitySettings"]
        print(f"inbound {tag}: target {r.get('target') or r.get('dest')} -> {target}; "
              f"names {r.get('serverNames')} -> {names}")
        r["target"] = target
        r.pop("dest", None)
        r["serverNames"] = names
        if not dry:
            con.execute("update inbounds set stream_settings=? where id=?",
                        (json.dumps(ss, ensure_ascii=False, indent=2), id_))
elif mode == "outbound":
    tag, name = args[2], args[3]
    tpl = json.loads(con.execute("select value from settings where key='xrayTemplateConfig'").fetchone()[0])
    o = next((o for o in tpl["outbounds"] if o.get("tag") == tag), None)
    if not o or not reality(o.get("streamSettings", {})):
        sys.exit(f"no Reality outbound {tag}")
    r = o["streamSettings"]["realitySettings"]
    backup()
    print(f"outbound {tag}: serverName {r.get('serverName')} -> {name}")
    r["serverName"] = name
    if not dry:
        con.execute("update settings set value=? where key='xrayTemplateConfig'",
                    (json.dumps(tpl, ensure_ascii=False, indent=2),))
else:
    sys.exit(__doc__)

if mode != "show":
    if not dry:
        con.commit()
    print("dry run: nothing written" if dry else "written; now: systemctl restart x-ui")
