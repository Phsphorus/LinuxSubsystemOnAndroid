#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Termux:X11 is an Android-generic root provider. It launches app_process,
# while Linux consumers only see the normal X11 socket published in the chroot.
BASE="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
SERVER="$BASE/implementation/server.sh"
STOPPER="$BASE/implementation/stop.sh"

case "${1:-}" in
  start) "$SERVER" ;;
  stop) "$STOPPER" ;;
  restart) "$STOPPER"; "$SERVER" ;;
  status)
    pid_file="$BASE/run/termux-x11.pid"
    if [ -f "$pid_file" ] && pid="$(tr -cd '0-9' <"$pid_file" 2>/dev/null)" && [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      printf 'RUNNING\n'
    else
      printf 'STOPPED\n'
    fi
    ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
