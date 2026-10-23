#!/system/bin/sh
set -u
BASE="/data/local/RootStart/Services/halagent"
PIDFILE="$BASE/run/halagent.pid"
AGENT="$BASE/halagent.py"
if [ -f "$PIDFILE" ]; then
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  case "$pid" in *[!0-9]*|'') ;; *)
    kill -TERM "$pid" 2>/dev/null || true
    sleep 1
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
  esac
fi
pkill -f "$AGENT" 2>/dev/null || true
rm -f "$PIDFILE"
