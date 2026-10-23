#!/data/data/com.termux/files/usr/bin/bash
set -u
BASE="$HOME/NonRootStart/Services/DNS/run"
killfile(){
  local f="$1" p=""
  [ -f "$f" ] && p="$(cat "$f" 2>/dev/null || true)"
  if [[ "$p" =~ ^[0-9]+$ ]]; then
    kill -TERM "$p" 2>/dev/null || true
    sleep .2
    kill -KILL "$p" 2>/dev/null || true
  fi
  rm -f "$f"
}
killfile "$BASE/socat-tcp.pid"
killfile "$BASE/socat-udp.pid"
killfile "$BASE/cloudflared.pid"
pkill -f "cloudflared proxy-dns" 2>/dev/null || true
pkill -f "UDP4-RECVFROM:53,bind=127\.0\.0\.1" 2>/dev/null || true
pkill -f "TCP4-LISTEN:53,bind=127\.0\.0\.1" 2>/dev/null || true
