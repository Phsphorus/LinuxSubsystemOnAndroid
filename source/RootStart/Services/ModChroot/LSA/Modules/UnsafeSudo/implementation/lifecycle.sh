#!/data/data/com.termux/files/usr/bin/bash

# This module is intentionally separate from the normal capability framework.
# It is a user-confirmed developer escape hatch for devices that cannot pass
# lsectl containment, not a safe generic privilege provider.

lsa_unsafe_sudo_install_rootfs() {
  local source root destination uid gid
  source="$BASE/LSA/Modules/UnsafeSudo/implementation/rootfs"
  root="${CHROOT_DIR:-/data/local/linux}"
  destination="$root/usr/local/lib/lsa/unsafe-sudo"

  [ "${UNSAFE_SUDO_ENABLE:-0}" = "1" ] || return 0
  [ -d "$source" ] || {
    log "unsafe-sudo: source directory missing: $source"
    return 1
  }

  uid="$(chroot "$root" /usr/bin/id -u "${UNSAFE_SUDO_USER:-myuser}" 2>/dev/null || true)"
  gid="$(chroot "$root" /usr/bin/id -g "${UNSAFE_SUDO_USER:-myuser}" 2>/dev/null || true)"
  case "$uid:$gid" in
    *[!0-9:]*|:) log "unsafe-sudo: Linux user ${UNSAFE_SUDO_USER:-myuser} is unavailable"; return 1 ;;
  esac

  install -d -m 755 -o 0 -g 0 "$destination" "$root/usr/local/bin"
  install -d -m 750 -o 0 -g "$gid" "$root/run/lsa"
  install -m 755 -o 0 -g 0 "$source/sudo" "$root/usr/local/bin/sudo"
  install -m 755 -o 0 -g 0 "$source/lsudo-run.py" "$destination/lsudo-run.py"
  log "unsafe-sudo: installed explicit warning wrapper for ${UNSAFE_SUDO_USER:-myuser}"
}

lsa_unsafe_sudo_stop() {
  local pid attempt
  pid="$(pid_read "${UNSAFE_SUDO_PID_FILE:-$RUNTIME_DIR/unsafe-sudo.pid}")"

  if pid_valid "$pid" && kill -0 "$pid" 2>/dev/null; then
    log "unsafe-sudo: requesting daemon stop pid=$pid"
    kill -TERM "$pid" 2>/dev/null || true
    for attempt in $(seq 1 50); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    if kill -0 "$pid" 2>/dev/null; then
      # Give an active disposable command namespace time to receive TERM and
      # exit through its parent-death signal instead of forcing it abruptly.
      log "unsafe-sudo: daemon did not stop; refusing SIGKILL while a command may be active"
      return 1
    fi
  fi

  rm -f \
    "${UNSAFE_SUDO_PID_FILE:-$RUNTIME_DIR/unsafe-sudo.pid}" \
    "${UNSAFE_SUDO_SOCKET:-$CHROOT_DIR/run/lsa/unsafe-sudo.sock}" \
    2>/dev/null || true
}

lsa_unsafe_sudo_start() {
  local daemon uid gid groups owner_pid owner_start_ticks attempt

  [ "${UNSAFE_SUDO_ENABLE:-0}" = "1" ] || return 0
  daemon="$BASE/LSA/Modules/UnsafeSudo/implementation/unsafe-sudo-daemon.py"
  [ -x "$daemon" ] || {
    log "unsafe-sudo: daemon is missing or not executable: $daemon"
    return 1
  }

  uid="$(chroot "$CHROOT_DIR" /usr/bin/id -u "${UNSAFE_SUDO_USER:-myuser}" 2>/dev/null || true)"
  gid="$(chroot "$CHROOT_DIR" /usr/bin/id -g "${UNSAFE_SUDO_USER:-myuser}" 2>/dev/null || true)"
  groups="$(chroot "$CHROOT_DIR" /usr/bin/id -G "${UNSAFE_SUDO_USER:-myuser}" 2>/dev/null || true)"
  case "$uid:$gid" in
    *[!0-9:]*|:) log "unsafe-sudo: Linux user ${UNSAFE_SUDO_USER:-myuser} is unavailable"; return 1 ;;
  esac
  case "$groups" in
    ''|*[!0-9\ ]*) log "unsafe-sudo: Linux groups for ${UNSAFE_SUDO_USER:-myuser} are unavailable"; return 1 ;;
  esac
  groups="${groups// /,}"

  # The daemon can be restarted independently of this shell, so tying it to
  # the transient launcher with PR_SET_PDEATHSIG makes a successful restart
  # disappear as soon as that launcher exits.  Bind it to the long-lived
  # ModChroot owner instead and pass its start tick as an anti-PID-reuse
  # identity check.
  owner_pid="${UNSAFE_SUDO_OWNER_PID:-$$}"
  case "$owner_pid" in
    ''|*[!0-9]*) log "unsafe-sudo: owner pid is invalid"; return 1 ;;
  esac
  owner_start_ticks="$(awk '{print $22}' "/proc/$owner_pid/stat" 2>/dev/null || true)"
  case "$owner_start_ticks" in
    ''|*[!0-9]*) log "unsafe-sudo: could not identify owner pid=$owner_pid"; return 1 ;;
  esac

  lsa_unsafe_sudo_stop || return 1
  rm -f "$UNSAFE_SUDO_LOG_FILE" 2>/dev/null || true
  python "$daemon" \
    --rootfs "$CHROOT_DIR" \
    --socket "$UNSAFE_SUDO_SOCKET" \
    --pid-file "$UNSAFE_SUDO_PID_FILE" \
    --log-file "$UNSAFE_SUDO_LOG_FILE" \
    --stage-root "$UNSAFE_SUDO_STAGE_ROOT" \
    --allowed-uid "$uid" \
    --allowed-gid "$gid" \
    --run-user "${UNSAFE_SUDO_USER:-myuser}" \
    --run-groups "$groups" \
    --owner-pid "$owner_pid" \
    --owner-start-ticks "$owner_start_ticks" \
    >/dev/null 2>&1 &

  for attempt in $(seq 1 30); do
    [ -S "$UNSAFE_SUDO_SOCKET" ] && [ -f "$UNSAFE_SUDO_PID_FILE" ] && {
      log "unsafe-sudo: daemon ready for ${UNSAFE_SUDO_USER:-myuser}"
      return 0
    }
    sleep 0.1
  done

  log "unsafe-sudo: daemon did not create its control socket"
  lsa_unsafe_sudo_stop || true
  return 1
}
