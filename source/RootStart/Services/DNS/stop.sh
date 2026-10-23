#!/data/data/com.termux/files/usr/bin/bash
set -u

BASE="/data/local/RootStart/Services/DNS"
PIDFILE="$BASE/run/cloudflared.pid"

pid=""

if [ -f "$PIDFILE" ]; then
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
fi

if [[ "$pid" =~ ^[0-9]+$ ]]; then
  kill -TERM "$pid" 2>/dev/null || true

  for _ in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || break
    sleep .2
  done

  kill -KILL "$pid" 2>/dev/null || true
fi

rm -f "$PIDFILE"

# Recover an orphaned RootStart resolver if its pidfile was lost.
pkill -f 'cloudflared proxy-dns --address 127.0.0.1 --port 53' \
  2>/dev/null || true

echo "DNS: stopped"
