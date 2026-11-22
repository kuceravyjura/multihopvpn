#!/usr/bin/env bash
# Read-only health check. Changes nothing on the server.
sec() { echo; echo "## $*"; }

sec "system"
. /etc/os-release; echo "$PRETTY_NAME | running kernel $(uname -r) | $(uptime -p)"
echo "installed kernels: $(ls /boot/vmlinuz-* 2>/dev/null | sed 's#/boot/vmlinuz-##' | tr '\n' ' ')"
[ -f /var/run/reboot-required ] && echo "REBOOT REQUIRED: $(cat /var/run/reboot-required.pkgs 2>/dev/null | tr '\n' ' ')" || echo "no reboot-required flag"

sec "memory / disk"
free -m
df -h / | tail -1
swapon --show --noheadings

sec "services"
for s in x-ui zapret AdGuardHome nginx tor fail2ban docker containerd multipathd ModemManager udisks2 upower unattended-upgrades; do
  st=$(systemctl is-active "$s" 2>/dev/null); en=$(systemctl is-enabled "$s" 2>/dev/null)
  [ -n "$en" ] && [ "$en" != "not-found" ] && printf '%-22s %-9s %s\n' "$s" "$st" "$en"
done
echo "failed units:"; systemctl --failed --no-legend --plain || true

sec "packages"
echo "dpkg audit: $(dpkg --audit 2>&1 | head -3)"; [ -z "$(dpkg --audit 2>&1)" ] && echo "(clean)"
n=$(apt list --upgradable 2>/dev/null | tail -n +2 | wc -l); echo "upgradable: $n"
apt list --upgradable 2>/dev/null | tail -n +2 | grep -Ei 'linux-image|openssh|openssl|libc6|systemd|grub' | cut -d' ' -f1,2
echo "unattended-upgrades last runs:"; grep -h 'Packages that will be upgraded\|No packages found\|error' /var/log/unattended-upgrades/unattended-upgrades.log 2>/dev/null | tail -3
debconf-show grub-pc 2>/dev/null | grep -E '\* grub-pc/install_devices:' || true

sec "logs"
journalctl --disk-usage 2>/dev/null
cat /etc/systemd/journald.conf.d/*.conf 2>/dev/null | grep -i SystemMaxUse

sec "public TCP listeners"
ss -tlnH | awk '{print $4}' | grep -vE '^(127\.|\[::1\])' | sed -E 's/.*:([0-9]+)$/\1/' | sort -n | uniq | tr '\n' ' '; echo

sec "docker"
if command -v docker >/dev/null 2>&1; then
  docker ps -a --format '{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}'
  docker system df 2>/dev/null
  docker volume ls -q | wc -l | xargs echo "volumes:"
else
  echo "docker not installed"
  ip -br link show docker0 2>/dev/null | sed 's/^/leftover: /'
fi

sec "ssh"
sshd -T 2>/dev/null | grep -Ei '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication) '
echo "failed ssh logins last 24h: $(journalctl -u ssh -u sshd --since '24 hours ago' 2>/dev/null | grep -c 'Invalid user\|Failed\|Connection closed by authenticating')"
