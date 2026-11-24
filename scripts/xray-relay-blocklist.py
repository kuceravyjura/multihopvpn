#!/usr/bin/env python3
"""Add (or remove) a routing rule that sends every domain on Russia's block list through the relay.

  add    <x-ui.db> <outbound-tag> [list]   default list: ext:geosite_RU.dat:ru-blocked
  remove <x-ui.db>
  show   <x-ui.db>

The rule goes right after the last existing rule for <outbound-tag> (the hand-made relay list
stays as it is and keeps priority), and before the "block" rules. It has a ruleTag, which is its
description in the panel. geosite_RU.dat is runetfreedom's list, refreshed nightly by the
geodata timer (ADR 0008, runbook 12). Saves a copy of the database first; restart x-ui after."""
import json, sqlite3, sys, time

TAG = "Relay: Russia's block list (runetfreedom ru-blocked, updated nightly)"
if len(sys.argv) < 3 or sys.argv[1] not in ("add", "remove", "show"):
    sys.exit(__doc__)
mode, db = sys.argv[1], sys.argv[2]
con = sqlite3.connect(db)
tpl = json.loads(con.execute("select value from settings where key='xrayTemplateConfig'").fetchone()[0])
rules = tpl["routing"]["rules"]


def show():
    for i, r in enumerate(rules):
        what = r.get("domain") or r.get("ip") or r.get("protocol") or r.get("port") or r.get("inboundTag")
        what = (what[:2] + [f"... {len(what)} total"]) if isinstance(what, list) and len(what) > 3 else what
        print(f"{i:2} -> {r.get('outboundTag', r.get('balancerTag')):18} {r.get('ruleTag', '')[:60]:60} {what}")


if mode == "show":
    show(); sys.exit(0)
have = [i for i, r in enumerate(rules) if r.get("ruleTag") == TAG]
if mode == "add":
    out = sys.argv[3]
    lst = sys.argv[4] if len(sys.argv) > 4 else "ext:geosite_RU.dat:ru-blocked"
    if not any(o.get("tag") == out for o in tpl["outbounds"]):
        sys.exit(f"no outbound {out}")
    if have:
        print("already there"); show(); sys.exit(0)
    # After the last plain rule (no inboundTag, i.e. a user rule) for this outbound.
    pos = max([i for i, r in enumerate(rules) if r.get("outboundTag") == out and "inboundTag" not in r],
              default=len(rules) - 1) + 1
    rules.insert(pos, {"type": "field", "ruleTag": TAG, "domain": [lst], "outboundTag": out})
elif not have:
    print("not there"); sys.exit(0)
else:
    del rules[have[0]]
dst = f"{db}.bak-blocklist-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"
con.execute(f"vacuum into '{dst}'")
con.execute("update settings set value=? where key='xrayTemplateConfig'", (json.dumps(tpl, ensure_ascii=False, indent=2),))
con.commit()
print(f"backup: {dst}")
show()
print("now: systemctl restart x-ui")
