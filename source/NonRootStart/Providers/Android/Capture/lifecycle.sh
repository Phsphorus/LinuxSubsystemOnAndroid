#!/data/data/com.termux/files/usr/bin/sh
set -u

BASE="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
STATE="$BASE/state"
RUN="$STATE/run"
LOGS="$STATE/logs"
PIDFILE="$RUN/capture-provider.pid"
PY="${PREFIX:-/data/data/com.termux/files/usr}/bin/python"
SCRIPT="$BASE/capture_provider.py"

pid_running() {
  [ -f "$PIDFILE" ] || return 1
  pid="$(tr -cd '0-9' <"$PIDFILE" 2>/dev/null)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

start() {
  mkdir -p "$RUN" "$LOGS" "$STATE/camera"
  if pid_running; then
    echo "AndroidCapture: already running pid=$(cat "$PIDFILE")"
    return 0
  fi
  rm -f "$PIDFILE"
  [ -x "$PY" ] || { echo "AndroidCapture: missing Python $PY" >&2; return 1; }
  [ -f "$SCRIPT" ] || { echo "AndroidCapture: missing provider $SCRIPT" >&2; return 1; }
  nohup "$PY" "$SCRIPT" >>"$LOGS/provider.log" 2>&1 &
  pid=$!
  echo "$pid" >"$PIDFILE"
  sleep 1
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "AndroidCapture: failed; see $LOGS/provider.log" >&2
    rm -f "$PIDFILE"
    return 1
  fi
  echo "AndroidCapture: started pid=$pid"
}

stop() {
  if pid_running; then
    pid="$(cat "$PIDFILE")"
    kill -TERM "$pid" 2>/dev/null || true
    sleep 1
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
  echo "AndroidCapture: stopped"
}

status() {
  if pid_running; then echo RUNNING; else echo STOPPED; fi
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
