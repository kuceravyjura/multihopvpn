#!/usr/bin/env bash
# Phase-0 backup: gathers VPN/DNS configs and a state snapshot into one tarball.
# Read-only on the server apart from a temporary folder in /tmp.
# Prints the tarball path as the last line of output.
set -euo pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"
NAME="homelab-backup-$(hostname)-${STAMP}"
OUT="/tmp/${NAME}"
mkdir -p "${OUT}"
chmod 700 "${OUT}"

# 3x-ui database (all inbounds, clients, routing). Use sqlite's online backup when possible.
if [ -f /etc/x-ui/x-ui.db ]; then
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 /etc/x-ui/x-ui.db ".backup '${OUT}/x-ui.db'"
  else
    cp -a /etc/x-ui/x-ui.db "${OUT}/x-ui.db"
  fi
fi
[ -f /usr/local/x-ui/bin/config.json ] && cp -a /usr/local/x-ui/bin/config.json "${OUT}/xray-config.json"

# AdGuard Home (default install path)
[ -f /opt/AdGuardHome/AdGuardHome.yaml ] && cp -a /opt/AdGuardHome/AdGuardHome.yaml "${OUT}/"

# Plain WireGuard configs, if any
[ -d /etc/wireguard ] && cp -a /etc/wireguard "${OUT}/etc-wireguard"

# wg-easy: copy whatever folders/volumes the container mounts
if command -v docker >/dev/null 2>&1; then
  docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}' > "${OUT}/docker-ps.txt" || true
  for c in $(docker ps -a --format '{{.Names}} {{.Image}}' | awk '/wg-easy/ {print $1}'); do
    docker inspect "${c}" > "${OUT}/docker-inspect-${c}.json"
    mkdir -p "${OUT}/wg-easy-${c}"
    for src in $(docker inspect "${c}" --format '{{range .Mounts}}{{.Source}} {{end}}'); do
      [ -e "${src}" ] && cp -a "${src}" "${OUT}/wg-easy-${c}/"
    done
  done
fi

# State snapshot for docs/inventory (remove IPs before committing anything from it)
{
  echo "== os-release";   cat /etc/os-release
  echo; echo "== kernel"; uname -a
  echo; echo "== memory"; free -m
  echo; echo "== disk";   df -h
  echo; echo "== tcp listeners"; ss -tlnp
  echo; echo "== udp listeners (without xray client sockets)"; ss -ulnp | grep -v xray || true
  echo; echo "== running services"; systemctl list-units --type=service --state=running --no-pager
} > "${OUT}/inventory.txt" 2>&1

{
  echo "== nft";      nft list ruleset 2>/dev/null || echo "(nft not available)"
  echo; echo "== iptables"; iptables-save 2>/dev/null || echo "(iptables not available)"
  echo; echo "== ufw";  ufw status verbose 2>/dev/null || echo "(ufw not installed)"
} > "${OUT}/firewall.txt" 2>&1

tar czf "${OUT}.tgz" -C /tmp "${NAME}"
chmod 600 "${OUT}.tgz"
rm -rf "${OUT}"
echo "${OUT}.tgz"
