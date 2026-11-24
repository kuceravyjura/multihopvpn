#!/usr/bin/env bash
# homelab-geodata: refresh Russia's block list for Xray (runetfreedom geosite.dat -> geosite_RU.dat).
# Safe update: checksum, then "xray -test" with the new file, then restart x-ui and check Xray came
# back with the same listening sockets; any failure puts the previous file back. ADR 0008, runbook 12.
#   homelab-geodata              update if upstream changed, restart x-ui
#   homelab-geodata --no-restart update the file only (the caller restarts)
#   homelab-geodata --force      update even if unchanged
set -uo pipefail
BIN=/usr/local/x-ui/bin
DST=$BIN/geosite_RU.dat
URL=${GEODATA_URL:-https://github.com/runetfreedom/russia-v2ray-rules-dat/releases/latest/download/geosite.dat}
PROM=${GEODATA_PROM:-/var/lib/prometheus/node-exporter/homelab_geodata.prom}
RESTART=1; FORCE=0
for a in "$@"; do case $a in --no-restart) RESTART=0 ;; --force) FORCE=1 ;; esac; done
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
log() { echo "homelab-geodata: $*"; }
report() {  # $1 = 1 ok / 0 failed
  [ -d "$(dirname "$PROM")" ] || return 0
  { echo "# TYPE homelab_geodata_last_check_ok gauge"; echo "homelab_geodata_last_check_ok $1"
    echo "# TYPE homelab_geodata_file_timestamp_seconds gauge"; echo "homelab_geodata_file_timestamp_seconds $(stat -c %Y "$DST" 2>/dev/null || echo 0)"
    echo "# TYPE homelab_geodata_last_run_timestamp_seconds gauge"; echo "homelab_geodata_last_run_timestamp_seconds $(date +%s)"
  } > "$PROM.tmp" && mv "$PROM.tmp" "$PROM"
}
fail() { log "FAILED: $*"; report 0; exit 1; }
# Inbound ports from Xray's running config that nothing is bound to (0 = all up). Counting sockets
# would not work: short-lived UDP sessions come and go.
missing() {
  python3 - "$BIN/config.json" <<'PY'
import json, subprocess, sys
ports = {i["port"] for i in json.load(open(sys.argv[1]))["inbounds"] if isinstance(i.get("port"), int)}
out = subprocess.run(["ss", "-ltnupH"], capture_output=True, text=True).stdout
bound = {int(l.split()[4].rsplit(":", 1)[1]) for l in out.splitlines() if len(l.split()) > 4}
print(len(ports - bound))
PY
}

curl -fsSL --retry 3 --max-time 300 -o "$TMP/geosite.dat" "$URL" || fail "download"
curl -fsSL --retry 3 --max-time 60 -o "$TMP/sum" "$URL.sha256sum" || fail "checksum download"
want=$(awk '{print $1}' "$TMP/sum"); got=$(sha256sum "$TMP/geosite.dat" | awk '{print $1}')
[ -n "$want" ] && [ "$want" = "$got" ] || fail "checksum mismatch"
if [ $FORCE = 0 ] && [ -f "$DST" ] && [ "$(sha256sum "$DST" | awk '{print $1}')" = "$got" ]; then
  log "unchanged"; report 1; exit 0
fi

XRAY=$(ls $BIN/xray-linux-* | head -1)
[ -f "$DST" ] && cp -p "$DST" "$DST.prev"
install -m 644 "$TMP/geosite.dat" "$DST"
if ! "$XRAY" run -test -c $BIN/config.json >"$TMP/test.log" 2>&1; then
  [ -f "$DST.prev" ] && mv "$DST.prev" "$DST"
  fail "xray -test rejected the new file: $(tail -2 "$TMP/test.log" | tr '\n' ' ')"
fi
log "new file installed ($(( $(stat -c %s "$DST") / 1048576 )) MB)"
[ $RESTART = 1 ] || { report 1; exit 0; }

systemctl restart x-ui
for i in $(seq 1 45); do sleep 2; [ "$(missing)" = 0 ] && break; done
if ! systemctl is-active -q x-ui || [ "$(missing)" != 0 ]; then
  log "Xray did not come back fully ($(missing) inbound ports not bound): restoring the previous file"
  [ -f "$DST.prev" ] && mv "$DST.prev" "$DST" && systemctl restart x-ui
  fail "rolled back"
fi
log "x-ui restarted, all inbound ports bound"
report 1
