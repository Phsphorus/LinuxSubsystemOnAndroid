#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

BASE="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
ROOTSTART="$(CDPATH= cd -- "$BASE/../../.." && pwd)"
CONFIG="$ROOTSTART/Services/ModChroot/config/config.sh"
TX11_PID_FILE="$BASE/run/termux-x11.pid"

# shellcheck source=/dev/null
source "$CONFIG"

display_num="${TERMUX_X11_DISPLAY#:}"
display_num="${display_num%%.*}"
socket="@${CHROOT_DIR}/tmp/.X11-unix/X${display_num}"

pid="$(cat "$TX11_PID_FILE" 2>/dev/null || true)"
if echo "$pid" | grep -Eq '^[0-9]+$'; then kill -TERM "$pid" 2>/dev/null || true; fi

socket_pid="$(ss -lxnp 2>/dev/null | grep -F "$socket" | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | head -n 1 || true)"
if echo "$socket_pid" | grep -Eq '^[0-9]+$'; then
  echo "Android TermuxX11 provider: stopping display=$TERMUX_X11_DISPLAY pid=$socket_pid"
  kill -TERM "$socket_pid" 2>/dev/null || true
  sleep 1
  kill -KILL "$socket_pid" 2>/dev/null || true
fi

rm -f "$TX11_PID_FILE"
rm -f "$CHROOT_DIR/tmp/.X${display_num}-lock" 2>/dev/null || true
rm -f "$CHROOT_DIR/tmp/.X11-unix/X${display_num}" 2>/dev/null || true
