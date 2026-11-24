#!/usr/bin/env python3
"""Remove 3x-ui node links and the inbound copies they left behind (2026-11-22 postmortem).

  check <x-ui.db>   what would be removed, and the guard (default; changes nothing)
  apply <x-ui.db>   remove it (x-ui must be STOPPED; saves a copy of the database first)

Removed: every inbound with node_id set (copies of the other server's inbounds, plus garbage from
the sync storm), their client links and traffic rows, clients that belong to nothing else, the
node entries and the node-only tables (traffic, IPs, pending resets).
Kept: every local inbound (node_id empty), every client that is also on a local inbound.
Guard: every client named in a local inbound's settings must still exist afterwards; otherwise
nothing is written."""
import json
import sqlite3
import sys
import time

if len(sys.argv) != 3 or sys.argv[1] not in ("check", "apply"):
    sys.exit(__doc__)
mode, db = sys.argv[1], sys.argv[2]
con = sqlite3.connect(db, isolation_level=None)   # explicit transactions below
q =lambda sql, *a: con.execute(sql, a).fetchall()

COPIES = "(select id from inbounds where node_id is not null)"
copies = q(f"select id, port, remark from inbounds where node_id is not null order by port")
only = [r[0] for r in q(f"""select id from clients
          where id in (select client_id from client_inbounds where inbound_id in {COPIES})
            and id not in (select client_id from client_inbounds where inbound_id not in {COPIES})""")]
plan = {
    "node links": q("select count(*) from nodes")[0][0],
    "inbound copies": len(copies),
    "client links to copies": q(f"select count(*) from client_inbounds where inbound_id in {COPIES}")[0][0],
    "traffic rows of copies": q(f"select count(*) from client_traffics where inbound_id in {COPIES}")[0][0],
    "clients only on copies": len(only),
    "node traffic rows": q("select count(*) from node_client_traffics")[0][0],
    "node IP rows": q("select count(*) from node_client_ips")[0][0],
    "node pending resets": q("select count(*) from node_pending_resets")[0][0],
}
local = q("select port, remark, settings from inbounds where node_id is null order by port")
print(f"local inbounds kept: {len(local)} (ports {', '.join(str(p) for p, _, _ in local)})")
for k, v in plan.items():
    print(f"remove {k}: {v}")
if not copies and not plan["node links"]:
    print("nothing to do")
    sys.exit(0)


def local_emails():
    out = set()
    for _, _, s in q("select port, remark, settings from inbounds where node_id is null"):
        try:
            out |= {c.get("email") for c in json.loads(s or "{}").get("clients", []) if c.get("email")}
        except ValueError:
            pass
    return out


need = local_emails()
if mode == "check":
    lost = need & {r[0] for r in q(f"select email from clients where id in ({','.join(map(str, only)) or 0})")}
    print("guard:", "OK, no local client would be removed" if not lost else f"FAIL, would remove {sorted(lost)}")
    sys.exit(1 if lost else 0)

dst = f"{db}.bak-nodes-{time.strftime('%Y%m%d-%H%M%S')}"
con.execute(f"vacuum into '{dst}'")
print(f"backup: {dst}")
try:
    con.execute("begin")
    ids = ",".join(map(str, only)) or "0"
    con.execute(f"delete from client_external_links where client_id in ({ids})")
    con.execute(f"delete from client_inbounds where inbound_id in {COPIES}")
    con.execute(f"delete from client_traffics where inbound_id in {COPIES}")
    con.execute(f"delete from clients where id in ({ids})")
    con.execute("delete from inbounds where node_id is not null")
    for t in ("node_pending_resets", "node_client_ips", "node_client_traffics", "nodes"):
        con.execute(f"delete from {t}")
    have = {r[0] for r in q("select email from clients")}
    missing = need - have
    if missing:
        raise RuntimeError(f"guard: local clients would be gone: {sorted(missing)}")
    con.execute("commit")
except Exception as e:
    con.execute("rollback")
    sys.exit(f"nothing changed: {e}")
print("done; start x-ui")
