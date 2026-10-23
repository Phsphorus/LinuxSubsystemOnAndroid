vnc_start() {
  [ "${VNC_ENABLE:-0}" = "1" ] || { log "vnc: disabled"; return 0; }

  if ! chroot "$CHROOT_DIR" /usr/bin/env -i PATH="$CHROOT_PATH" /bin/sh -c "command -v vncserver >/dev/null 2>&1"; then
    log "vnc: vncserver not installed; skip"
    return 0
  fi

  log "vnc: clearing stale display $VNC_DISPLAY"
  chroot "$CHROOT_DIR" /usr/bin/env -i PATH="$CHROOT_PATH" HOME=/root USER=root LOGNAME=root /bin/sh -lc "vncserver -kill '$VNC_DISPLAY' >/dev/null 2>&1 || true; rm -f /tmp/.X${VNC_DISPLAY#:}-lock /tmp/.X11-unix/X${VNC_DISPLAY#:} 2>/dev/null || true"

  log "vnc: starting $VNC_DISPLAY geometry=$VNC_GEOMETRY localhost=$VNC_LOCALHOST"
  chroot "$CHROOT_DIR" /usr/bin/env -i PATH="$CHROOT_PATH" HOME=/root USER=root LOGNAME=root /bin/sh -lc "vncserver '$VNC_DISPLAY' -geometry '$VNC_GEOMETRY' -localhost '$VNC_LOCALHOST'" >>"$RUNTIME_DIR/vnc.log" 2>&1 || { log "vnc: ERROR startup failed; see $RUNTIME_DIR/vnc.log"; return 1; }
}

vnc_stop() {
  [ "${VNC_ENABLE:-0}" = "1" ] || return 0
  [ -x "$CHROOT_DIR/bin/sh" ] || return 0

  log "vnc: stopping $VNC_DISPLAY"
  chroot "$CHROOT_DIR" /usr/bin/env -i PATH="$CHROOT_PATH" HOME=/root USER=root LOGNAME=root /bin/sh -lc "vncserver -kill '$VNC_DISPLAY' >/dev/null 2>&1 || true" >/dev/null 2>&1 || true
}
