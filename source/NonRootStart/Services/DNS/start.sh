#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
BASE="$HOME/NonRootStart/Services/DNS"
RUN="$BASE/run"
LOGS="$BASE/logs"
mkdir -p "$RUN" "$LOGS"
CF="$PREFIX/bin/cloudflared"
SOCAT="$PREFIX/bin/socat"
CFPID="$RUN/cloudflared.pid"
SUDP="$RUN/socat-udp.pid"
STCP="$RUN/socat-tcp.pid"

"$BASE/stop.sh" >/dev/null 2>&1 || true
[ -x "$CF" ] || { echo "DNS: cloudflared missing at $CF" >&2; exit 1; }

"$CF" proxy-dns --address 127.0.0.1 --port 5053 >>"$LOGS/cloudflared.log" 2>&1 &
echo $! > "$CFPID"
sleep 1
kill -0 "$(cat "$CFPID")" 2>/dev/null || { echo "DNS: cloudflared failed" >&2; exit 1; }

if [ -x "$SOCAT" ]; then
  "$SOCAT" -T1 -u UDP4-RECVFROM:53,bind=127.0.0.1,fork,reuseaddr UDP4-SENDTO:127.0.0.1:5053 >>"$LOGS/socat-udp.log" 2>&1 &
  echo $! > "$SUDP"
  "$SOCAT" -T1 TCP4-LISTEN:53,bind=127.0.0.1,fork,reuseaddr TCP4:127.0.0.1:5053 >>"$LOGS/socat-tcp.log" 2>&1 &
  echo $! > "$STCP"
else
  echo "DNS: socat missing; 5053 only"
fi

echo "DNS: started"
