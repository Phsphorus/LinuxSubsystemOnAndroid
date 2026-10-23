#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

BASE="$(cd "$(dirname "$0")" && pwd)"
IMPLEMENTATION="$BASE/implementation"
RUN="$BASE/run"
LOGS="$BASE/logs"
PID_FILE="$RUN/provider.pid"
LOG_FILE="$LOGS/provider.log"
PY="$PREFIX/bin/python"
SCRIPT="$IMPLEMENTATION/provider.py"

log(){ printf '%s AndroidAudioProvider: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

pid_running(){
  [ -f "$PID_FILE" ] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null
}

start(){
  mkdir -p "$RUN" "$LOGS"
  if pid_running; then
    log "already running pid=$(cat "$PID_FILE")"
    return 0
  fi
  rm -f "$PID_FILE"
  [ -x "$PY" ] || { log "ERROR Termux Python missing: $PY"; return 1; }
  [ -f "$SCRIPT" ] || { log "ERROR provider source missing: $SCRIPT"; return 1; }
  "$PY" "$SCRIPT" >>"$LOG_FILE" 2>&1 &
  local pid=$!
  echo "$pid" >"$PID_FILE"
  sleep 1
  if ! kill -0 "$pid" 2>/dev/null; then
    log "ERROR provider failed; see $LOG_FILE"
    rm -f "$PID_FILE"
    return 1
  fi
  log "started pid=$pid"
}

stop(){
  if ! pid_running; then
    rm -f "$PID_FILE"
    return 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  kill -TERM "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
  done
  kill -KILL "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  log "stopped"
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) if pid_running; then printf 'RUNNING\n'; else printf 'STOPPED\n'; fi ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
