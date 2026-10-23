TEARDOWN_DONE=0

prepare_rootfs() {
  mkdir -p \
    "$RUNTIME_DIR" \
    "$CHROOT_DIR/tmp" \
    "$CHROOT_DIR/tmp/.X11-unix" \
    "$CHROOT_DIR/mnt"

  chmod 1777 "$CHROOT_DIR/tmp" "$CHROOT_DIR/tmp/.X11-unix" 2>/dev/null || true
}

start_switch_watcher() {
  local parent_pid="$$"

  (
    log "switch: watcher started file=$SWITCH_FILE"

    while true; do
      if [ ! -e "$SWITCH_FILE" ]; then
        log "switch: missing; requesting teardown"
        kill -TERM "$parent_pid" 2>/dev/null || true
        exit 0
      fi
      sleep 1
    done
  ) &

  echo "$!" >"$WATCH_PID_FILE"
}

stop_switch_watcher() {
  local pid
  pid="$(pid_read "$WATCH_PID_FILE")"

  if pid_valid "$pid"; then
    kill "$pid" 2>/dev/null || true
  fi

  rm -f "$WATCH_PID_FILE" 2>/dev/null || true
}

teardown_all() {
  [ "$TEARDOWN_DONE" = "0" ] || return 0
  TEARDOWN_DONE=1

  log "teardown: begin"

  # This runs before chroot processes are swept so a confirmed unsafe sudo
  # lease always returns the rootfs to nosuid during normal shutdown.
  if declare -F lsa_unsafe_sudo_stop >/dev/null 2>&1; then
    lsa_unsafe_sudo_stop || log "unsafe-sudo: stop did not complete cleanly"
  fi

  if [ "${LSA_FRAMEWORK_ENABLED:-0}" = 1 ]; then
    for lsa_module in Sensors Location Camera Audio Display DBus; do
      lsa_framework_lifecycle_module stop "$lsa_module" || true
    done
  fi

  stop_switch_watcher
  vnc_stop
  #
  # Allow chroot-backed services to shut down cleanly before
  # the general chroot process/group/root sweep.
  #
  run_hooks pre-stop || true

  kill_chroot_session

  #
  # Final idempotent cleanup after the process sweep.
  #
  run_hooks post-stop || true

  sync 2>/dev/null || true
  sleep 1

  unmount_registered_reverse

  # Keep the last selected backends visible after teardown.  Availability is
  # intentionally retained while runtime states become STOPPED/FAILED.
  if [ "${LSA_FRAMEWORK_ENABLED:-0}" = 1 ]; then
    lsa_framework_refresh_runtime
    lsa_framework_write_state teardown
  fi

  rm -f "$TEARDOWN_LOCK" 2>/dev/null || true

  log "teardown: done"
}

modchroot_preflight() {
  log "preflight: checking previous chroot"

  local active=0

  if chroot_has_processes; then
    active=1
    log "preflight: existing chroot processes detected"
  fi

  if [ -f "$PID_FILE" ] ||
     [ -f "$CHROOT_DIR/chroot.pid" ] ||
     [ -f "$WATCH_PID_FILE" ] ||
     [ -f "$CHROOT_DIR/chroot.watch.pid" ]; then
    active=1
    log "preflight: existing/stale chroot state detected"
  fi

  stop_old_watchers

  if declare -F lsa_unsafe_sudo_stop >/dev/null 2>&1; then
    lsa_unsafe_sudo_stop || log "unsafe-sudo: previous daemon did not stop cleanly"
  fi

  if [ "$active" = "1" ]; then
    log "preflight: tearing down previous session"
  else
    log "preflight: no running session; cleaning stale state"
  fi

  # Kill everything belonging to the old rootfs before touching mounts.
  kill_chroot_session

  sync 2>/dev/null || true
  sleep 1

  # Handles mounts created by BOTH the modular and old monolithic versions.
  unmount_entire_chroot_tree

  rm -f \
    "$CHROOT_DIR/tmp/.X"*"-lock" \
    "$CHROOT_DIR/tmp/.X11-unix/X"* \
    "$CHROOT_DIR/halaudio.pid" \
    "$CHROOT_DIR/chroot.pid" \
    "$CHROOT_DIR/chroot.watch.pid" \
    2>/dev/null || true

  log "preflight: previous chroot completely cleared"
}
