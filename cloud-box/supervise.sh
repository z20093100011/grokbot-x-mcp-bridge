#!/bin/sh
DIR=/home/box/x-bridge
LOCK=$DIR/supervise.lock

mkdir -p "$DIR/responses" "$DIR/requests" "$DIR/done"
/home/box/x-bridge/bin/ensure_tailscale.sh >/dev/null 2>&1 || true

(
  flock -n 9 || exit 0
  while true; do
    /home/box/x-bridge/bin/ensure_tailscale.sh >/dev/null 2>&1 || true
    sleep 20
  done
) 9>"$DIR/ts_watchdog.lock" >/dev/null 2>&1 &

cd "$DIR" || exit 1
exec flock -n "$LOCK" /bin/sh -c '
while true; do
  python3 /home/box/x-bridge/bin/http_server.py >> /home/box/x-bridge/http_server.log 2>&1
  echo "$(date -u +%FT%TZ) x-bridge http_server exit, restart in 2s" >> /home/box/x-bridge/http_server.log
  sleep 2
done
'
