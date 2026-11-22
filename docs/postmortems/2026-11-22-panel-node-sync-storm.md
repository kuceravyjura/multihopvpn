# Postmortem: 3x-ui node-sync storm wipes inbounds on both servers

**Date:** 2026-11-22, ~17:45–18:05 MSK
**Impact:**
- Server 2 vless 8443 users: no service for about 15 minutes.
- Server 1 (Moscow) WireGuard and vless users: no service for about 1–2 minutes.
- wg-easy users: unaffected.
- Lost: Server 1's panel traffic counters since 15:44.

**Severity:** high. Users were cut off on both servers, and the second outage was caused during recovery.

## Summary

The two 3x-ui panels were linked as nodes **in both directions**: Server 2's panel managed Server 1 as
`ru-1`, and Server 1's panel managed Server 2 as `lith1`. Both links used inbound sync "all".

During the wg-easy migration (phase 5), importing one inbound on Server 2's panel also created a node
copy, and the link synced that copy to Server 1. Deleting the copy started a reconcile storm in both
directions. Inbounds were deleted, re-adopted under new ids and re-labelled. Server 2 lost its own
8443 inbound, and Server 1's panel database was rewritten.

Server 1's running Xray still held the old, correct inbounds. While stopping the sync, a
`systemctl restart x-ui` on Server 1 rebuilt Xray from the rewritten database, and 13 of its 15 user
inbounds disappeared.

Both panel databases were restored from backups taken before the storm, and both node links were
switched off.

## Timeline (MSK)

| Time | Event |
|---|---|
| 17:42 | Backup of Server 2 pulled home before the cutover (`homelab-backup`) |
| ~17:43 | wg-easy inbound imported on Server 2's panel: one local inbound (as intended) and one node copy for `ru-1`; the copy synced to Server 1 |
| ~17:44 | Pre-cutover check finds two inbounds on 51820; the cutover is paused; the owner is asked to delete the node copy |
| 17:45 | Delete in the panel; burst of `inbounds/update` calls (ids 38–72) failing with port clashes; `DelInbound` / "adopted compatible inbound" on `ru-1`; Server 2 loses 8443 and the panel UI stops working |
| ~17:48 | Diagnosis: Server 1's live Xray intact (15 inbounds); Server 2 missing 8443; sync active on both panels |
| ~18:00 | Server 1: node link disabled in the database, x-ui restarted. **Xray comes back with only 2 of 15 inbounds** |
| ~18:02 | Server 1: database restored from the 15:44 backup, phase 4 DNS template re-applied, link off. All 15 inbounds live |
| ~18:04 | Server 2: 17:42 backup checked first (all 10 inbounds, wg-easy inbound disabled), node copy removed, link off, restored. 8443 live |
| ~18:10 | End-to-end check: ads blocked through Server 1 → relay → AdGuard, NXDOMAIN fine, both panels open |

## Root causes

1. **Two-way node links with full sync.** Each panel treated the other server's inbounds as its own to
   reconcile. One change fanned out in both directions, and port clashes made the reconcile fail
   halfway.
2. **The import targeted a node as well as the local server.** The import produced a node copy that
   nobody asked for.
3. **Restart without checking the source of truth (recovery error).** The live Xray config and the
   panel database had drifted apart. A restart regenerates Xray from the database, and nobody checked
   the database first.

## What went well

- The pre-cutover check caught the duplicate inbound before wg-easy was stopped. wg-easy users were
  never affected.
- Backups existed from minutes before the storm (Server 2, 17:42) and from the phase 4 change
  (Server 1, 15:44). Both restores were exact.
- Phase 4's DNS template was in the repo workflow (`backups/phase4/`) and was re-applied in one step.

## Action items

| Action | Status |
|---|---|
| Both node links disabled (`nodes.enable = 0`) | done |
| Before any x-ui restart or panel-database write, compare the database's local inbounds with the live `config.json` ports | rule adopted |
| Imports on a panel with node links target the local server only; check the inbound count on that port afterwards | runbook (phase 5) |
| Owner decision: keep the links off, or one-way only | open |
| Clean the leftover duplicates on Server 1's panel (now unused) and compare it with the restored state | open |
| Broken databases kept for analysis: `/root/x-ui.db.incident-2026-11-22-s1`, `-s2`, `/root/x-ui.db.broken-after-restart-2026-11-22` | delete after 2026-12-06 |

## Note on panel access

The firewall still lets each server's address reach the other server's panel port (6902/6903). That
was originally for the node links. It is kept on purpose as the owner's second way in, for example
from a phone on the other server's VPN profile. The panels still require the secret path and login.
