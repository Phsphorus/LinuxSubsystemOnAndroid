desktop_detect_command() {
  local cmd

  if [ "${DESKTOP_COMMAND:-auto}" = "none" ]; then
    return 1
  fi

  if [ "${DESKTOP_COMMAND:-auto}" != "auto" ]; then
    printf '%s\n' "$DESKTOP_COMMAND"
    return 0
  fi

  for cmd in \
    startlxde \
    startxfce4 \
    mate-session \
    cinnamon-session \
    startplasma-x11 \
    openbox-session
  do
    if chroot "$CHROOT_DIR" /usr/bin/env -i \
        PATH="$CHROOT_PATH" \
        /bin/sh -c "command -v '$cmd' >/dev/null 2>&1"; then
      printf '%s\n' "$cmd"
      return 0
    fi
  done

  return 1
}

desktop_start() {
  [ "${DESKTOP_AUTOSTART:-0}" = "1" ] || {
    log "desktop: autostart disabled"
    return 0
  }

  local cmd
  cmd="$(desktop_detect_command || true)"

  if [ -z "$cmd" ]; then
    log "desktop: no supported desktop session command found; skipping"
    return 0
  fi

  log "desktop: starting '$cmd' on $CHROOT_DISPLAY"

  setsid chroot "$CHROOT_DIR" \
    /usr/bin/env -i \
    "${CHROOT_ENV_VARS[@]}" \
    HOME=/root \
    USER=root \
    LOGNAME=root \
    /bin/sh -lc "exec $cmd" \
    >"$RUNTIME_DIR/desktop.log" 2>&1 &

  log "desktop: launcher pid=$!"
}
