chroot_process_pids() {
  # Enumerate every process whose root is CHROOT_DIR.
  #
  # IMPORTANT:
  # Do this as one batched /proc scan. The old implementation launched
  # readlink once per PID, which takes minutes on some Android systems.
  { ls -ld /proc/[0-9]*/root 2>/dev/null || true; } |
    awk -v root="$CHROOT_DIR" '
      {
        path = ""
        target = ""

        for (i = 1; i <= NF; i++) {
          if ($i == "->" && (i + 1) <= NF) {
            path = $(i - 1)
            target = $(i + 1)
            break
          }
        }

        if (path == "")
          next

        if (target == root || index(target, root "/") == 1) {
          pid = path
          sub("^/proc/", "", pid)
          sub("/root$", "", pid)

          if (pid ~ /^[0-9]+$/)
            print pid
        }
      }
    '
}


chroot_has_processes() {
  [ -n "$(chroot_process_pids)" ]
}


kill_pid_and_group() {
  local pid="$1"

  pid_valid "$pid" || return 0

  log "kill: TERM pid=$pid group=-$pid"

  kill -TERM -- "-$pid" 2>/dev/null || true
  kill -TERM "$pid" 2>/dev/null || true

  sleep 1

  kill -KILL -- "-$pid" 2>/dev/null || true
  kill -KILL "$pid" 2>/dev/null || true
}


kill_by_chroot_root_sweep() {
  local pid pids

  log "kill: root-sweep /proc/*/root under $CHROOT_DIR"

  pids="$(chroot_process_pids)"

  if [ -z "$pids" ]; then
    log "kill: root-sweep no matching processes"
    return 0
  fi

  set -- $pids
  log "kill: root-sweep TERM matched=$#"

  for pid in $pids; do
    kill -TERM "$pid" 2>/dev/null || true
  done

  sleep 1

  # Re-scan because processes may have exited, forked, or changed state.
  pids="$(chroot_process_pids)"

  if [ -z "$pids" ]; then
    log "kill: root-sweep cleared after TERM"
    return 0
  fi

  set -- $pids
  log "kill: root-sweep KILL remaining=$#"

  for pid in $pids; do
    kill -KILL "$pid" 2>/dev/null || true
  done
}


kill_chroot_session() {
  local pid

  pid="$(pid_read "$PID_FILE")"
  pid_valid "$pid" && kill_pid_and_group "$pid"

  pid="$(pid_read "$CHROOT_DIR/chroot.pid")"
  pid_valid "$pid" && kill_pid_and_group "$pid"

  rm -f \
    "$PID_FILE" \
    "$CHROOT_DIR/chroot.pid" \
    2>/dev/null || true

  kill_by_chroot_root_sweep
}


stop_old_watchers() {
  local pid file

  for file in \
    "$WATCH_PID_FILE" \
    "$CHROOT_DIR/chroot.watch.pid"
  do
    pid="$(pid_read "$file")"

    if pid_valid "$pid"; then
      log "kill: stale watcher pid=$pid"
      kill "$pid" 2>/dev/null || true
    fi

    rm -f "$file" 2>/dev/null || true
  done
}
