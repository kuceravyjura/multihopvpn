#!/usr/bin/env python3
"""Phase 4: send Server 1 users' DNS to Server 2's AdGuard. Idempotent.

Reads a 3x-ui Xray template (or a full Xray config) and writes it back with:
  - dns: AdGuard DoH via the relay (ClientID srv1-moscow, 1.5 s timeout), then 1.1.1.1
  - outbound dns-out
  - routing: DNS module -> relay (AdGuard only) / direct (fallback); user port 53 -> dns-out
Every added rule carries a ruleTag, which is its description in the panel.

usage: xray-dns-adguard.py <in.json> <out.json> <s2-domain> <s2-ip> <inbound-tag>[,...]|ALL
  <inbound-tag>  canary: only those inbounds;  ALL: every inbound, including future ones
Runbook: docs/runbooks/05-moscow-dns-via-adguard.md"""
import sys, json
src, dst, dom, ip, tags = sys.argv[1:6]
c = json.load(open(src, encoding="utf-8"))
RELAY = "xhttptest-rurelay"
c["dns"] = {
    "tag": "dns-module",
    "hosts": {dom: ip},
    # AdGuard via the relay; if it doesn't answer in 1.5 s, a public resolver straight from
    # Moscow (no ad blocking, but DNS keeps working). "localhost" as the fallback lost
    # NXDOMAIN answers (clients waited out their timeouts) - lab test 2026-11-22.
    "servers": [{"address": f"https://{dom}:3452/dns-query/srv1-moscow", "timeoutMs": 1500},
                "1.1.1.1"],
    "queryStrategy": "UseIPv4",
}
outs = [o for o in c["outbounds"] if o.get("tag") != "dns-out"]
outs.append({"tag": "dns-out", "protocol": "dns"})
c["outbounds"] = outs
rules = [r for r in c["routing"]["rules"]
         if r.get("outboundTag") != "dns-out" and r.get("inboundTag") != ["dns-module"]]
# ruleTag = the rule's description in the panel (Xray JSON has no comments).
dns_rule = {"type": "field", "ruleTag": "Phase 4: user DNS (port 53) -> AdGuard via dns-out",
            "port": "53", "network": "tcp,udp", "outboundTag": "dns-out"}
if tags != "ALL":   # canary: only the listed inbounds
    dns_rule["inboundTag"] = tags.split(",")
    dns_rule["ruleTag"] += " (canary)"
# ALL: no inboundTag, so inbounds added later are covered too. No loop: the DNS module's
# own fallback query to 1.1.1.1:53 matches the "fallback direct" rule above it first.
new = [{"type": "field", "ruleTag": "Phase 4: AdGuard DoH via relay to Server 2 (by name)",
        "inboundTag": ["dns-module"], "domain": [f"full:{dom}"], "outboundTag": RELAY},
       {"type": "field", "ruleTag": "Phase 4: AdGuard DoH via relay to Server 2 (by IP)",
        "inboundTag": ["dns-module"], "ip": [ip], "outboundTag": RELAY},
       {"type": "field", "ruleTag": "Phase 4: DNS fallback 1.1.1.1 leaves directly",
        "inboundTag": ["dns-module"], "outboundTag": "direct"},
       dns_rule]
i = 1 if rules and rules[0].get("inboundTag") == ["api"] else 0
c["routing"]["rules"] = rules[:i] + new + rules[i:]
json.dump(c, open(dst, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
for r in c["routing"]["rules"]:
    print(f'  {",".join(r.get("inboundTag", ["*"]))[:16]:16} -> {r["outboundTag"]:18} {r.get("ruleTag", "")}')
