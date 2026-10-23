#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="/data/data/com.termux/files/usr"
export PREFIX="$TERMUX_PREFIX"
export PATH="$TERMUX_PREFIX/bin:/system/bin:/system/xbin"
unset LD_LIBRARY_PATH LD_PRELOAD LD_AUDIT PYTHONPATH PYTHONHOME TMPDIR
export HOME=/root
umask 077

BASE="$(cd "$(dirname "$0")" && pwd)"

# =========================
# CONFIG
# =========================
# shellcheck source=/dev/null
source "$BASE/config/config.sh"

# =========================
# LIBRARIES
# =========================
for lib in \
  logging \
  pid \
  mounts \
  processes \
  dns \
  env \
  debian_family \
  hooks \
  vnc \
  desktop \
  lifecycle
do
  # shellcheck source=/dev/null
  source "$BASE/lib/$lib.sh"
done

if [ -r "$BASE/LSA/Modules/UnsafeSudo/implementation/lifecycle.sh" ]; then
  # shellcheck source=/dev/null
  source "$BASE/LSA/Modules/UnsafeSudo/implementation/lifecycle.sh"
fi

log_init

# The framework observes and selects existing implementations during this
# migration.  It deliberately does not replace the proven lifecycle calls
# below; descriptors expose those calls as capability-backed backends.
LSA_FRAMEWORK_ENABLED=0
if [ -r "$BASE/LSA/Framework/core.sh" ]; then
  # shellcheck source=/dev/null
  source "$BASE/LSA/Framework/core.sh"
  LSA_FRAMEWORK_ENABLED=1
else
  log "framework: unavailable; continuing with compatibility lifecycle"
fi

MODE="${1:-start}"
case "$MODE" in
  start) CHROOT_SESSION_MODE=interactive ;;
  --daemon) CHROOT_SESSION_MODE=daemon ;;
  --preflight)
    log "ModChroot: preflight requested"
    modchroot_preflight
    exit 0
    ;;
  *) log "ERROR: unsupported ModChroot session mode: $MODE"; exit 64 ;;
esac

log "start: begin"
log "start: rootfs=$CHROOT_DIR"
log "start: modular RootStart implementation"

if [ ! -x "$CHROOT_DIR/bin/sh" ]; then
  log "ERROR: rootfs does not look bootable: $CHROOT_DIR/bin/sh missing"
  exit 1
fi

prepare_rootfs

# A prior RootStart process can leave this root-side daemon alive even though
# its Debian children were swept.  Stop it before discarding its PID record.
if declare -F lsa_unsafe_sudo_stop >/dev/null 2>&1; then
  lsa_unsafe_sudo_stop || log "unsafe-sudo: previous daemon did not stop cleanly"
fi

# Clean stale chroot processes from an interrupted previous run.
kill_by_chroot_root_sweep

# Clear our own old runtime state.
rm -f \
  "$PID_FILE" \
  "$WATCH_PID_FILE" \
  "$HALAUDIO_PID_FILE" \
  "$UNSAFE_SUDO_PID_FILE" \
  "$TEARDOWN_LOCK" \
  2>/dev/null || true

trap 'teardown_all' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

run_hooks pre-start

touch "$SWITCH_FILE"
chmod 644 "$SWITCH_FILE" 2>/dev/null || true
log "switch: ensured $SWITCH_FILE"

start_switch_watcher

# =========================
# COMPONENT BOOTSTRAP
# =========================
# These mounts must precede capability selection. The implementation remains
# in its module/provider owner; ModChroot supplies only the fixed dependency
# order needed to create the initial Linux namespace.
for component_implementation in \
  "$BASE/LSA/Modules/CoreChroot/implementation/mounts.sh" \
  "$BASE/LSA/Modules/DeviceNamespace/implementation/private-dev.sh" \
  "$BASE/LSA/Modules/DeviceNamespace/implementation/shared-memory.sh" \
  "$BASE/LSA/Providers/Android/GPUBridge/implementation/mounts.sh" \
  "$BASE/LSA/Providers/Android/HALAgent/implementation/mounts.sh"
do
  [ -r "$component_implementation" ] || {
    log "ERROR: missing component implementation $component_implementation"
    exit 1
  }
  log "component bootstrap: $component_implementation"
  # shellcheck source=/dev/null
  source "$component_implementation"
done

run_hooks post-mount

if [ -r "$BASE/LSA/Modules/Audio/implementation/inject.sh" ]; then
  # shellcheck source=/dev/null
  source "$BASE/LSA/Modules/Audio/implementation/inject.sh"
fi

if [ -r "$BASE/LSA/Modules/Sensors/implementation/inject.sh" ]; then
  # shellcheck source=/dev/null
  source "$BASE/LSA/Modules/Sensors/implementation/inject.sh"
  lsa_sensors_install_rootfs
fi

if [ -r "$BASE/LSA/Modules/Camera/implementation/inject.sh" ]; then
  # shellcheck source=/dev/null
  source "$BASE/LSA/Modules/Camera/implementation/inject.sh"
fi

if [ -r "$BASE/LSA/Modules/VideoEncode/implementation/inject.sh" ]; then
  # shellcheck source=/dev/null
  source "$BASE/LSA/Modules/VideoEncode/implementation/inject.sh"
  lsa_video_encode_install_rootfs
fi

if [ -r "$BASE/LSA/Modules/GPU/implementation/inject.sh" ]; then
  # shellcheck source=/dev/null
  source "$BASE/LSA/Modules/GPU/implementation/inject.sh"
  lsa_gpu_install_rootfs
fi

# The phone UI is a Debian-side X11 client.  Install its source-owned files
# before the configured desktop command starts.
if [ -r "$BASE/LSA/Shell/implementation/inject.sh" ]; then
  # shellcheck source=/dev/null
  source "$BASE/LSA/Shell/implementation/inject.sh"
  lsa_shell_install_rootfs
fi

if declare -F lsa_unsafe_sudo_install_rootfs >/dev/null 2>&1; then
  lsa_unsafe_sudo_install_rootfs || log "unsafe-sudo: rootfs injection failed; ordinary sudo stays unavailable"
  lsa_unsafe_sudo_start || log "unsafe-sudo: daemon failed to start; ordinary sudo stays unavailable"
fi

if [ "$LSA_FRAMEWORK_ENABLED" = 1 ]; then
  lsa_framework_refresh post-mount || log "framework: post-mount refresh failed; compatibility lifecycle continues"
  lsa_framework_lifecycle_module start Storage || log "framework: Storage activation unavailable"
  lsa_framework_refresh_runtime
  lsa_framework_write_state post-mount-active
else
  # shellcheck source=/dev/null
  source "$BASE/LSA/Modules/Storage/implementation/android-shared.sh"
  lsa_storage_android_shared_start || log "storage: Android shared storage unavailable"
  lsa_storage_external_start || log "storage: Android removable-storage ownership watcher unavailable"
fi

# =========================
# DNS
# =========================
# RootStart owns the local resolver on 127.0.0.1:53.
# ModChroot only configures the disposable rootfs to use it.
write_resolv_to_local_stub

# Debian-family provisioning requires the final chroot DNS path to exist.
run_hooks post-network

if [ "$LSA_FRAMEWORK_ENABLED" = 1 ]; then
  lsa_framework_refresh post-network || log "framework: post-network refresh failed; compatibility lifecycle continues"
  for lsa_module in Wireless Sensors Camera Location Display D-Bus; do
    lsa_framework_lifecycle_module start "$lsa_module" || log "framework: $lsa_module activation unavailable"
  done
  lsa_framework_refresh_runtime
  lsa_framework_write_state post-network-active
fi

# =========================
# RUNTIME ENVIRONMENT
# =========================
load_chroot_environment
print_chroot_environment

# =========================
# ROOTFS SERVICES
# =========================
if [ "$LSA_FRAMEWORK_ENABLED" = 1 ]; then
  lsa_framework_lifecycle_module start Audio || log "framework: Audio activation unavailable"
else
  "$BASE/LSA/Modules/Audio/implementation/lifecycle.sh" start || log "audio: module activation unavailable"
fi
vnc_start

run_hooks pre-enter

if [ "$LSA_FRAMEWORK_ENABLED" = 1 ]; then
  # SensorBus is non-root and can come online shortly after the mounts do.
  # Wait for its PID cheaply, then perform one capability refresh.  A full
  # refresh performs several Android probes, so retrying it in a tight loop
  # turned a short provider delay into a multi-minute chroot boot.
  sensorbus_pid_file="$LSA_NONROOT_BASE/Services/HALSensorBus/run/HALSensorBus.pid"
  sensorbus_ready=0
  for sensor_attempt in $(seq 1 30); do
    if [ -r "$sensorbus_pid_file" ]; then
      sensorbus_pid="$(cat "$sensorbus_pid_file" 2>/dev/null || true)"
      if [ -n "$sensorbus_pid" ] && kill -0 "$sensorbus_pid" 2>/dev/null; then
        sensorbus_ready=1
        break
      fi
    fi
    sleep 1
  done
  [ "$sensorbus_ready" = 1 ] || log "framework: SensorBus was not ready after 30 seconds"
  lsa_framework_refresh runtime-ready || log "framework: runtime-ready refresh failed"
  if [ -n "${LSA_SELECTED_BACKEND[Sensors]:-}" ]; then
    lsa_framework_lifecycle_module start Sensors || log "framework: Sensors activation unavailable"
  else
    log "framework: Sensors has no selected backend after readiness wait"
  fi
  lsa_framework_refresh_runtime
  lsa_framework_write_state runtime-ready
fi

# Start the installed desktop on the canonical Termux:X11 display.
desktop_start

# =========================
# CHROOT SESSION
# =========================
# Most interactive launches should continue to open a Debian login shell.
# Deployment and ADB qualification, however, deliberately have no controlling
# terminal.  `--daemon` is an explicit lifecycle mode: it keeps the selected
# providers and mounted namespace alive without fabricating or borrowing a
# tty.  It is not an unbounded detached process: the normal switch watcher
# and RootStart TERM cleanup own and stop its process group.
if [ "$CHROOT_SESSION_MODE" = daemon ]; then
  log "chroot: launching daemon supervisor (no interactive tty)"
  setsid -w chroot "$CHROOT_DIR" \
    /usr/bin/env -i \
    "${CHROOT_ENV_VARS[@]}" \
    HOME=/root \
    USER=root \
    LOGNAME=root \
    /bin/sh -c 'trap "exit 0" HUP INT TERM; while :; do sleep 60; done' \
    </dev/null >/dev/null 2>&1 &
else
  log "chroot: launching interactive shell"
  setsid -w chroot "$CHROOT_DIR" \
    /usr/bin/env -i \
    "${CHROOT_ENV_VARS[@]}" \
    HOME=/root \
    USER=root \
    LOGNAME=root \
    /bin/bash --login \
    </dev/tty >/dev/tty 2>&1 &
fi

CHROOT_SESS_PID="$!"
echo "$CHROOT_SESS_PID" >"$PID_FILE"

log "chroot: session pid=$CHROOT_SESS_PID"

wait "$CHROOT_SESS_PID" || true

log "chroot: exited"
log "start: end"
