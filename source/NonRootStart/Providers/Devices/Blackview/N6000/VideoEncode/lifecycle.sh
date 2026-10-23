#!/data/data/com.termux/files/usr/bin/bash
set -u

BASE="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
STATE="$BASE/state"
RUN="$STATE/run"
LOGS="$STATE/logs"
PID_FILE="$RUN/video-provider.pid"
CONTROL_SOCKET="$HOME/.lsa-n6000-video-control.sock"
MANAGER="$BASE/implementation/manager.py"
CONTROL="$BASE/control.py"
PY="${PREFIX:-/data/data/com.termux/files/usr}/bin/python"

pid_running() {
  [ -f "$PID_FILE" ] || return 1
  local pid
  pid="$(tr -cd '0-9' <"$PID_FILE" 2>/dev/null)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

probe() {
  [ "$(getprop ro.product.manufacturer 2>/dev/null)" = Blackview ] || {
    echo "N6000 VideoEncode: device manufacturer does not match" >&2
    return 3
  }
  [ "$(getprop ro.product.model 2>/dev/null)" = N6000 ] || {
    echo "N6000 VideoEncode: device model does not match" >&2
    return 3
  }
  case "$(getprop ro.product.cpu.abi 2>/dev/null)" in
    arm64-v8a|arm64|aarch64) ;;
    *) echo "N6000 VideoEncode: proven provider requires arm64 Android ABI" >&2; return 3 ;;
  esac
  [ -x "$PY" ] && [ -f "$MANAGER" ] || {
    echo "N6000 VideoEncode: implementation prerequisites are unavailable" >&2
    return 3
  }
  return 0
}

start() {
  mkdir -p "$RUN" "$LOGS"
  if pid_running; then
    echo "N6000 VideoEncode: control provider already running pid=$(cat "$PID_FILE")"
    return 0
  fi
  rm -f "$PID_FILE" "$CONTROL_SOCKET"
  [ -x "$PY" ] || { echo "N6000 VideoEncode: missing Python $PY" >&2; return 1; }
  [ -f "$MANAGER" ] || { echo "N6000 VideoEncode: missing manager $MANAGER" >&2; return 1; }
  nohup "$PY" "$MANAGER" serve >>"$LOGS/provider.log" 2>&1 &
  local pid=$!
  echo "$pid" > "$PID_FILE"
  for _ in $(seq 1 30); do
    [ -S "$CONTROL_SOCKET" ] && kill -0 "$pid" 2>/dev/null && {
      echo "N6000 VideoEncode: Termux control provider started pid=$pid"
      return 0
    }
    sleep 0.1
  done
  echo "N6000 VideoEncode: control provider failed; see $LOGS/provider.log" >&2
  kill -TERM "$pid" 2>/dev/null || true
  rm -f "$PID_FILE" "$CONTROL_SOCKET"
  return 1
}

stop() {
  if pid_running; then
    "$PY" "$CONTROL" shutdown >/dev/null 2>&1 || true
    local pid
    pid="$(cat "$PID_FILE")"
    kill -TERM "$pid" 2>/dev/null || true
    sleep 1
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$PID_FILE" "$CONTROL_SOCKET"
  echo "N6000 VideoEncode: Termux control provider stopped"
}

status() {
  if pid_running && [ -S "$CONTROL_SOCKET" ]; then echo RUNNING; else echo STOPPED; fi
}

case "${1:-status}" in
  probe) probe ;;
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
