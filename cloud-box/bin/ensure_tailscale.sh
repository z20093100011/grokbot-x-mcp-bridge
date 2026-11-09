#!/bin/bash
# Keep Tailscale up on the Grok Bot cloud box. Customize HOSTNAME via env.
set -e
HOSTNAME="${CLOUD_HOSTNAME:-grokbot-x-bridge}"
STATE_BACKUP="${TAILSCALE_STATE_BACKUP:-/home/box/.tailscale}"

sudo mkdir -p /var/lib/tailscale /var/run/tailscale
if ! sudo test -s /var/lib/tailscale/tailscaled.state && [ -s "$STATE_BACKUP/state/tailscaled.state" ]; then
  sudo cp -a "$STATE_BACKUP/state/." /var/lib/tailscale/ && sudo chown -R root:root /var/lib/tailscale && sudo chmod 700 /var/lib/tailscale
fi
sudo update-alternatives --set iptables /usr/sbin/iptables-legacy >/dev/null 2>&1 || true
sudo update-alternatives --set ip6tables /usr/sbin/ip6tables-legacy >/dev/null 2>&1 || true

restart_ts() {
  sudo pkill -9 -x tailscaled 2>/dev/null || true
  sleep 0.5
  sudo sh -c 'nohup /usr/sbin/tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/var/run/tailscale/tailscaled.sock >/var/log/tailscaled.log 2>&1 </dev/null &'
  for i in $(seq 15); do
    tailscale status >/dev/null 2>&1 && break
    sleep 0.5
  done
  sudo tailscale set --ssh --hostname="$HOSTNAME" --operator=box >/dev/null 2>&1 || true
}

if ! pgrep -x tailscaled >/dev/null 2>&1; then
  restart_ts
else
  ST=$(timeout 4 tailscale status 2>&1 || echo "offline")
  if echo "$ST" | head -n 5 | grep -qE "${HOSTNAME}.*offline|stopped|NeedsLogin|hasn't received a network map|failed to connect"; then
    restart_ts
  fi
fi
