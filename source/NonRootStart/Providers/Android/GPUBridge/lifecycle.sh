#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# This provider runs as the Termux user.  RootStart consumes the published
# VirGL socket but never starts or stops this Android-facing process.
BASE="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
RUN="$BASE/run"
LOGS="$BASE/logs"
PID_FILE="$RUN/virgl.pid"
SOCKET="$RUN/.virgl_test"
MODE_FILE="$RUN/mode"
SERVER="$BASE/implementation/server.sh"
STOPPER="$BASE/implementation/stop.sh"

pid_running() {
  [ -f "$PID_FILE" ] || return 1
  local pid
  pid="$(tr -cd '0-9' <"$PID_FILE" 2>/dev/null)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

start() {
  mkdir -p "$RUN" "$LOGS"
  if pid_running && [ -S "$SOCKET" ]; then
    printf 'Android GPUBridge: already running pid=%s\n' "$(cat "$PID_FILE")"
    return 0
  fi
  "$SERVER"
}

video_start() {
  local launcher="${1:-}"
  [ -n "$launcher" ] && [ -x "$launcher" ] || {
    echo "Android GPUBridge: video launcher is missing or not executable" >&2
    return 2
  }
  # Switching modes necessarily replaces the one Termux-user VirGL server.
  # The N6000 device provider performs this only after a requested video
  # activation; ordinary NonRootStart always calls the generic start path.
  stop
  GPU_BRIDGE_MODE=video GPU_BRIDGE_VIDEO_LAUNCHER="$launcher" "$SERVER"
}

video_stop() {
  # Return the generic Linux render endpoint after releasing the optional
  # device video tap. This is a provider-owned mode change, not a root or
  # chroot process operation.
  stop
  start
}

stop() {
  "$STOPPER"
}

status() {
  if pid_running && [ -S "$SOCKET" ]; then
    printf 'RUNNING\n'
  else
    printf 'STOPPED\n'
  fi
}

mode() {
  if pid_running && [ -f "$MODE_FILE" ]; then
    tr -d '\r\n' <"$MODE_FILE"
  elif pid_running; then
    printf generic
  else
    printf STOPPED
  fi
  printf '\n'
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  video-start) video_start "${2:-}" ;;
  video-stop) video_stop ;;
  status) status ;;
  mode) mode ;;
  *) echo "usage: $0 {start|stop|restart|video-start|video-stop|status|mode}" >&2; exit 2 ;;
esac
