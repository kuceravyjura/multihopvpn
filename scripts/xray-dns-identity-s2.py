#!/usr/bin/env python3
"""Per-user DNS identity, Server 2 side: deliver DNS for 10.53.0.0/24 locally (AdGuard).
Inserted right after the api rule, so it wins over the WARP and private-IP rules. Idempotent.
Deferred (ADR 0004): lab-tested on staging, never applied to Server 2.
usage: xray-dns-identity-s2.py <template.json> <out.json>"""
import sys, json
c = json.load(open(sys.argv[1], encoding="utf-8"))
TAG = "Per-user DNS: 10.53.0.N:53 -> local AdGuard (client = 10.53.0.N)"
rules = [r for r in c["routing"]["rules"] if r.get("ruleTag") != TAG]
i = 1 if rules and rules[0].get("inboundTag") == ["api"] else 0
rules.insert(i, {"type": "field", "ruleTag": TAG, "ip": ["10.53.0.0/24"], "port": "53",
                 "network": "tcp,udp", "outboundTag": "adguard-local"})
c["routing"]["rules"] = rules
# "direct" refuses private addresses (finalRules: block geoip:private). This outbound allows
# exactly the identity range and still blocks every other private address.
outs = [o for o in c["outbounds"] if o.get("tag") != "adguard-local"]
outs.append({"tag": "adguard-local", "protocol": "freedom", "settings": {"finalRules": [
    {"action": "allow", "ip": ["10.53.0.0/24"], "port": "53"},
    {"action": "block", "ip": ["geoip:private"]},
    {"action": "allow"}]}})
c["outbounds"] = outs
json.dump(c, open(sys.argv[2], "w", encoding="utf-8"), indent=2, ensure_ascii=False)
for r in rules[:4]: print(" ", r.get("inboundTag", ["*"])[0][:14], "->", r["outboundTag"], r.get("ruleTag", ""))
