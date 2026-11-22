#!/usr/bin/env python3
"""Phase 4: let Server 1's Xray (ClientID srv1-moscow) use AdGuard. Idempotent.
Adds the ClientID to allowed_clients, a named persistent client, and exempts one IP
(Server 2's own: relayed queries arrive from it) from the per-IP rate limit.
Stop AdGuard Home before running it and start it after (it rewrites its own file).
usage: adguard-allow-srv1.py <AdGuardHome.yaml> <ip-to-exempt-from-ratelimit>"""
import sys, uuid, copy, yaml
path, wl_ip = sys.argv[1], sys.argv[2]
CID = "srv1-moscow"
c = yaml.safe_load(open(path))
d = c["dns"]
changed = []
if d.get("allowed_clients") and CID not in d["allowed_clients"]:
    d["allowed_clients"].append(CID); changed.append("allowed_clients += " + CID)
wl = d.get("ratelimit_whitelist") or []
if wl_ip not in wl:
    wl.append(wl_ip); d["ratelimit_whitelist"] = wl; changed.append("ratelimit_whitelist += <ip>")
pers = c.setdefault("clients", {}).setdefault("persistent", []) or []
if not any(CID in (p.get("ids") or []) for p in pers):
    base = copy.deepcopy(pers[0]) if pers else {}
    base.update(name=CID, ids=[CID], uid=str(uuid.uuid4()), tags=[], upstreams=[],
                use_global_settings=True, use_global_blocked_services=True,
                ignore_querylog=False, ignore_statistics=False)
    pers.append(base); c["clients"]["persistent"] = pers; changed.append("clients.persistent += " + CID)
if changed:
    yaml.safe_dump(c, open(path, "w"), sort_keys=False, allow_unicode=True)
print("changed: " + "; ".join(changed) if changed else "no change")
