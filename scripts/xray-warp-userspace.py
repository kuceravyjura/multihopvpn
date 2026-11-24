#!/usr/bin/env python3
"""Run the panel's WARP outbound inside Xray (userspace) instead of as a kernel interface.

  on   <x-ui.db>   noKernelTun: true, domainStrategy: ForceIPv4
  off  <x-ui.db>   back to the kernel interface (noKernelTun: false, no domainStrategy)
  show <x-ui.db>
Idempotent. Saves a copy of the database first. Restart x-ui afterwards, then remove the leftover
routing rules (runbook 14).

Why: in kernel mode Xray creates an interface (wg0) holding WARP's IPv6 address, so the server
looks IPv6-capable without a working IPv6 route: programs that try IPv6 first hang (the bot's
Telegram replies took minutes). Xray also adds a pair of `ip -6 rule` entries on every restart and
never removes them. Userspace mode needs no interface or rules. ForceIPv4: the server has no IPv6,
and WARP's endpoint name also resolves to IPv6, which userspace mode would otherwise try and fail."""
import json
import sqlite3
import sys
import time

if len(sys.argv) != 3 or sys.argv[1] not in ("on", "off", "show"):
    sys.exit(__doc__)
mode, db = sys.argv[1], sys.argv[2]
con = sqlite3.connect(db)
row = con.execute("select value from settings where key='xrayTemplateConfig'").fetchone()
if not row:
    sys.exit("no xrayTemplateConfig in this database")
cfg = json.loads(row[0])
warp = [o for o in cfg.get("outbounds", []) if o.get("protocol") == "wireguard" and o.get("tag") == "warp"]
if not warp:
    sys.exit("no WireGuard outbound tagged 'warp'")
s = warp[0].setdefault("settings", {})
print(f"now: noKernelTun={s.get('noKernelTun')} domainStrategy={s.get('domainStrategy')}")
if mode == "show":
    sys.exit(0)

want = {"noKernelTun": True, "domainStrategy": "ForceIPv4"} if mode == "on" else {"noKernelTun": False}
if all(s.get(k) == v for k, v in want.items()) and (mode == "on" or "domainStrategy" not in s):
    print("nothing to change")
    sys.exit(0)
dst = f"{db}.bak-warp-{time.strftime('%Y%m%d-%H%M%S')}"
con.execute(f"vacuum into '{dst}'")
print(f"backup: {dst}")
s.update(want)
if mode == "off":
    s.pop("domainStrategy", None)
con.execute("update settings set value=? where key='xrayTemplateConfig'", (json.dumps(cfg, indent=2),))
con.commit()
print(f"set: noKernelTun={s.get('noKernelTun')} domainStrategy={s.get('domainStrategy')}. Restart x-ui.")
