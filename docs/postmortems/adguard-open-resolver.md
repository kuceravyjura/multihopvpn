# Postmortem: AdGuard Home used as an open DNS resolver

**Status:** draft. Fill in the TODOs from memory and from any provider emails or graphs.
**Severity:** medium. No data loss; the server was used against third parties.

## Summary

AdGuard Home on Server 2 answered plain DNS (port 53) from any address on the internet. Bots found
it and sent large volumes of queries, most likely spoofed queries for DNS amplification attacks.
Plain DNS was disabled and AdGuard now serves only DNS-over-HTTPS.

## Timeline

| When | What |
|---|---|
| TODO | AdGuard installed on Server 2, listening on all interfaces |
| TODO | First sign of trouble (traffic graph, CPU, provider email, query log?) |
| TODO | Cause identified |
| TODO | Plain DNS disabled in AdGuard; DoH kept on :3452 |
| 2026-11-21 | Verified from outside: a plain DNS query to port 53 times out |

## Root cause

AdGuard listened on `0.0.0.0:53` with no firewall in front and no client allowlist. An open UDP
resolver lets an attacker forge the victim's IP as the source address; small queries produce large
answers sent to the victim. Internet-wide scanners find open resolvers within hours.

## What went well

- The problem was noticed and the service was closed.
- The 3x-ui panels were on non-default ports with random paths and were not hit.

## What could have gone better

- No firewall policy existed, so one setting was the only protection.
- No monitoring: the abuse was noticed by symptom, not by an alert.
- AdGuard still binds `*:53` after plain DNS was disabled. Outside queries time out, but the socket is open.
- The 2026-11-21 inventory found the AdGuard web UI (3000) public as well, and DoT (853) open without
  a client allowlist.

## Action items

| Action | Phase | Status |
|---|---|---|
| Default-deny firewall; port 53 allowed only from Docker bridges | 1 / 3 | open |
| AdGuard plain DNS listens on localhost and Docker bridge only | 3 | open |
| DoH and DoT restricted to known ClientIDs | 1 | open |
| AdGuard web UI (3000) reachable over wg-mgmt only | 1 / 3 | open |
| Alert on unusual outbound traffic and CPU | 6 | open |
| External port scan as part of every firewall change | 1 | open |
