#!/data/data/com.termux/files/usr/bin/bash
set -u

BASE="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
CHROOT_DIR="${CHROOT_DIR:-/data/local/linux}"
CAPTURE_CONTROL="${LSA_ANDROID_CAPTURE_CONTROL:-${LSA_NONROOT_BASE:-/data/data/com.termux/files/home/NonRootStart}/Providers/Android/Capture/control.py}"
TERMUX_PYTHON="${LSA_TERMUX_PREFIX:-/data/data/com.termux/files/usr}/bin/python"
SOURCE="/usr/local/lib/lsa/liblsa_camera_v4l2.c"
LIBRARY="/usr/local/lib/lsa/liblsa-camera-v4l2.so"
MODULE_SOURCE="$BASE/rootfs/lsa-camera/liblsa_camera_v4l2.c"
RECORD_SOURCE="$BASE/rootfs/lsa-camera/camera-record"
RECORD_TOOL="/usr/local/bin/camera-record"

log(){ printf 'ModChroot: camera: %s\n' "$*"; }

in_chroot(){
  chroot "$CHROOT_DIR" /usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin "$@"
}

build_compat(){
  [ -f "$MODULE_SOURCE" ] || { log "module V4L2 compatibility source is missing"; return 1; }
  # Keep the compiled rootfs shim tied to the canonical module source.  This
  # makes a focused Camera sync take effect on the next module start instead
  # of silently recompiling an older injection-time copy.
  mkdir -p "$(dirname "$CHROOT_DIR$SOURCE")" || return 1
  cp -f "$MODULE_SOURCE" "$CHROOT_DIR$SOURCE" || return 1
  chmod 644 "$CHROOT_DIR$SOURCE" || return 1
  [ -f "$RECORD_SOURCE" ] || { log "module camera recorder is missing"; return 1; }
  mkdir -p "$(dirname "$CHROOT_DIR$RECORD_TOOL")" || return 1
  cp -f "$RECORD_SOURCE" "$CHROOT_DIR$RECORD_TOOL" || return 1
  chmod 755 "$CHROOT_DIR$RECORD_TOOL" || return 1
  [ -x "$CHROOT_DIR/usr/bin/gcc" ] || { log "gcc is required to build the V4L2 compatibility layer"; return 1; }
  in_chroot /usr/bin/gcc -shared -fPIC -O2 -Wall -Wextra -o "$LIBRARY" "$SOURCE" -ldl || return 1
  chmod 755 "$CHROOT_DIR$LIBRARY"
  # The preload shim owns open/ioctl for this node. The node only makes it
  # discoverable to normal Linux camera enumeration.
  for node in video0 lsa-camera; do
    # Private /dev normally provides a host read-through symlink.  Replace
    # that symlink for camera nodes so stat(), directory scans, and V4L2 apps
    # see a real device rather than a dangling Android host path.
    [ -L "$CHROOT_DIR/dev/$node" ] && rm -f "$CHROOT_DIR/dev/$node"
    if [ ! -e "$CHROOT_DIR/dev/$node" ]; then
      mknod "$CHROOT_DIR/dev/$node" c 81 0 2>/dev/null || true
      chmod 666 "$CHROOT_DIR/dev/$node" 2>/dev/null || true
    fi
  done
}

start(){
  "$TERMUX_PYTHON" "$CAPTURE_CONTROL" camera start || return 1
  build_compat
}

stop(){ "$TERMUX_PYTHON" "$CAPTURE_CONTROL" camera stop || true; }

status(){
  response="$("$TERMUX_PYTHON" "$CAPTURE_CONTROL" camera status 2>/dev/null)" || { printf STOPPED; return 0; }
  if [ -f "$CHROOT_DIR$LIBRARY" ] && printf '%s' "$response" | grep -q '"camera_active":true'; then printf RUNNING; else printf STOPPED; fi
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  restart) stop; start ;;
  status) status ;;
  *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
