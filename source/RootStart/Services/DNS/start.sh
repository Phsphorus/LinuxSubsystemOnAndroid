#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

BASE="/data/local/RootStart/Services/DNS"
RUN="$BASE/run"
LOGS="$BASE/logs"

CF="/data/data/com.termux/files/usr/bin/cloudflared"
PIDFILE="$RUN/cloudflared.pid"
LOG="$LOGS/cloudflared.log"

mkdir -p "$RUN" "$LOGS"

"$BASE/stop.sh" >/dev/null 2>&1 || true

if [ ! -x "$CF" ]; then
  echo "DNS: ERROR cloudflared missing: $CF" >&2
  exit 1
fi

"$CF" proxy-dns \
  --address 127.0.0.1 \
  --port 53 \
  >>"$LOG" 2>&1 &

pid=$!
echo "$pid" >"$PIDFILE"

sleep 1

if ! kill -0 "$pid" 2>/dev/null; then
  echo "DNS: ERROR cloudflared failed; see $LOG" >&2
  rm -f "$PIDFILE"
  exit 1
fi

# Android's /system/bin/ss does not reliably expose this loopback
# listener even when cloudflared is healthy. Process survival is checked
# here; ModChroot's network preflight performs the real resolver test.
if ! kill -0 "$pid" 2>/dev/null; then
  echo "DNS: ERROR cloudflared exited during startup; see $LOG" >&2
  rm -f "$PIDFILE"
  exit 1
fi

echo "DNS: started pid=$pid resolver=127.0.0.1:53"
