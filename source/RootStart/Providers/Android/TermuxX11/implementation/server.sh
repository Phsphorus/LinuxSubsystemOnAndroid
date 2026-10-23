#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

BASE="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
ROOTSTART="$(CDPATH= cd -- "$BASE/../../.." && pwd)"
CHROOT_CONFIG="$ROOTSTART/Services/ModChroot/config/config.sh"
RUN="$BASE/run"
LOGS="$BASE/logs"
TX11_PID_FILE="$RUN/termux-x11.pid"
TX11_LOG_FILE="$LOGS/termux-x11.log"
TX11_PACKAGE="com.phsphorus.lsa.x11"

mkdir -p "$RUN" "$LOGS"
touch "$TX11_LOG_FILE"

# shellcheck source=/dev/null
source "$CHROOT_CONFIG"

if [ "${TERMUX_X11_ENABLE:-1}" != "1" ]; then
  echo "Android TermuxX11 provider: disabled" >>"$TX11_LOG_FILE"
  exit 0
fi

mkdir -p "$CHROOT_DIR/tmp/.X11-unix"
chmod 1777 "$CHROOT_DIR/tmp" "$CHROOT_DIR/tmp/.X11-unix" 2>/dev/null || true

if [ ! -d "$CHROOT_DIR/usr/share/X11/xkb" ]; then
  echo "Android TermuxX11 provider: rootfs has no XKB data" >>"$TX11_LOG_FILE"
  exit 0
fi

apk="$(/system/bin/pm path "$TX11_PACKAGE" 2>/dev/null | sed -n '1s/^package://p')"
if [ -z "$apk" ]; then
  echo "Android TermuxX11 provider: ERROR Android app $TX11_PACKAGE is not installed" >>"$TX11_LOG_FILE"
  exit 1
fi

echo "Android TermuxX11 provider: package=$TX11_PACKAGE apk=$apk" >>"$TX11_LOG_FILE"

if [ -f "$TX11_PID_FILE" ]; then
  pid="$(cat "$TX11_PID_FILE" 2>/dev/null || true)"
  if echo "$pid" | grep -Eq '^[0-9]+$' && kill -0 "$pid" 2>/dev/null; then
    echo "Android TermuxX11 provider: already running pid=$pid" >>"$TX11_LOG_FILE"
    exit 0
  fi
fi

# Do not adopt arbitrary CmdEntryPoint processes: upstream and LSA builds use
# the same Java class name. Only this provider's recorded PID is trusted.
display_num="${TERMUX_X11_DISPLAY#:}"
display_num="${display_num%%.*}"
rm -f "$CHROOT_DIR/tmp/.X${display_num}-lock" 2>/dev/null || true
rm -f "$CHROOT_DIR/tmp/.X11-unix/X${display_num}" 2>/dev/null || true

CLASSPATH="$apk" \
TMPDIR="$CHROOT_DIR/tmp" \
XKB_CONFIG_ROOT="$CHROOT_DIR/usr/share/X11/xkb" \
/system/bin/env -u LD_LIBRARY_PATH -u LD_PRELOAD -u LD_AUDIT /system/bin/app_process / \
  --nice-name=lsa-x11 \
  com.termux.x11.CmdEntryPoint "$TERMUX_X11_DISPLAY" \
  >>"$TX11_LOG_FILE" 2>&1 &

pid="$!"
echo "$pid" >"$TX11_PID_FILE"
echo "Android TermuxX11 provider: started display=$TERMUX_X11_DISPLAY pid=$pid" >>"$TX11_LOG_FILE"

for _ in $(seq 1 50); do
  [ -S "$CHROOT_DIR/tmp/.X11-unix/X${display_num}" ] && exit 0
  kill -0 "$pid" 2>/dev/null || break
  sleep 0.1
done

if [ ! -S "$CHROOT_DIR/tmp/.X11-unix/X${display_num}" ]; then
  echo "Android TermuxX11 provider: ERROR X socket did not appear" >>"$TX11_LOG_FILE"
  exit 1
fi
