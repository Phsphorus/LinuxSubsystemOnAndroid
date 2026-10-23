#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Providers run as the Termux application user, but should still not inherit
# arbitrary linker/Python overrides from the shell that launched NRS.
TERMUX_PREFIX="/data/data/com.termux/files/usr"
export PREFIX="$TERMUX_PREFIX"
export PATH="$TERMUX_PREFIX/bin:/system/bin:/system/xbin"
unset LD_PRELOAD LD_AUDIT PYTHONPATH PYTHONHOME TMPDIR
export HOME="/data/data/com.termux/files/home"
umask 077

BASE="$HOME/NonRootStart/Services"
SWITCH_FILE="$BASE/SWITCH"
STATE="$BASE/.supervisor"
LOG="$BASE/termux-services.log"
WPID="$STATE/switch-watcher.pid"
LOCK="$STATE/.teardown.lock"
INSTANCE_LOCK="$STATE/.instance.lock"
INSTANCE_PID="$STATE/nrs.pid"

# Provider lifecycle runs as the Termux user. RootStart only consumes its
# published capability endpoints; it never starts this Android-facing service.
# Android providers are ordinary, broadly applicable Termux-user services.
# Vendor and device providers are discovered below and must self-probe before
# they are started.  NonRootStart owns their lifecycle but does not decide
# which one RootStart's capability framework will select.
GENERIC_PROVIDER_ORDER=(
  "$HOME/NonRootStart/Providers/Android/Capture/lifecycle.sh"
  "$HOME/NonRootStart/Providers/Android/Audio/lifecycle.sh"
  "$HOME/NonRootStart/Providers/Android/GPUBridge/lifecycle.sh"
)
PROVIDER_ORDER=()

# Hard dependency order. RootStart is assumed to start only after all of these.
SERVICE_ORDER=(HALSensorBus)
COMPONENT_STATE="$STATE/components.tsv"

mkdir -p "$STATE"
touch "$LOG"
exec > >(tee -a "$LOG") 2>&1
log(){ printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
MAIN_PID="$$"

acquire_instance_lock(){
  local existing=""
  if mkdir "$INSTANCE_LOCK" 2>/dev/null; then
    printf '%s\n' "$MAIN_PID" > "$INSTANCE_PID"
    return 0
  fi
  existing="$(cat "$INSTANCE_PID" 2>/dev/null || true)"
  if [[ "$existing" =~ ^[0-9]+$ ]] && kill -0 "$existing" 2>/dev/null; then
    log "start: an existing NonRootStart supervisor is already active pid=$existing"
    return 1
  fi
  rm -f "$INSTANCE_PID"
  rmdir "$INSTANCE_LOCK" 2>/dev/null || true
  mkdir "$INSTANCE_LOCK" || return 1
  printf '%s\n' "$MAIN_PID" > "$INSTANCE_PID"
}

release_instance_lock(){
  [ "${BASHPID:-$$}" = "$MAIN_PID" ] || return 0
  rm -f "$INSTANCE_PID"
  rmdir "$INSTANCE_LOCK" 2>/dev/null || true
}

# The Android-facing providers must survive a display-off idle period.  This
# process is also placed on Android's device-idle allowlist during deployment;
# the Termux:API wake lock keeps the CPU available while the LSA stack owns an
# active switch file.
acquire_wake_lock(){
  if command -v termux-wake-lock >/dev/null 2>&1; then
    termux-wake-lock >/dev/null 2>&1 && log "power: Termux wake lock acquired" || log "WARNING: power: could not acquire Termux wake lock"
  else
    log "WARNING: power: termux-wake-lock command is unavailable"
  fi
}

release_wake_lock(){
  command -v termux-wake-unlock >/dev/null 2>&1 || return 0
  termux-wake-unlock >/dev/null 2>&1 && log "power: Termux wake lock released" || true
}

record_component(){
  local kind="$1" path="$2" result="$3"
  printf '%s\t%s\t%s\n' "$kind" "${path#$HOME/NonRootStart/}" "$result" >> "$COMPONENT_STATE"
}

discover_provider_lifecycles(){
  local provider_root lifecycle
  PROVIDER_ORDER=("${GENERIC_PROVIDER_ORDER[@]}")
  for provider_root in \
    "$HOME/NonRootStart/Providers/Vendors" \
    "$HOME/NonRootStart/Providers/Devices"
  do
    [ -d "$provider_root" ] || continue
    while IFS= read -r lifecycle; do
      [ -n "$lifecycle" ] && PROVIDER_ORDER+=("$lifecycle")
    done < <(find "$provider_root" -type f -name lifecycle.sh -print 2>/dev/null | sort)
  done
}

start_provider(){
  local lifecycle="$1" rc
  if [ ! -x "$lifecycle" ]; then
    log "provider unavailable: missing $lifecycle"
    record_component provider "$lifecycle" ERROR
    return 0
  fi

  # A vendor/device provider is optional by definition. It must decline from
  # its own scope before any provider process is created; this is deliberately
  # path-scope based rather than a branch for one device model.
  case "$lifecycle" in
    "$HOME/NonRootStart/Providers/Vendors/"*|"$HOME/NonRootStart/Providers/Devices/"*)
      if "$lifecycle" probe; then
        :
      else
        rc=$?
        log "optional provider unsupported: $lifecycle (self-probe exit=$rc)"
        record_component provider "$lifecycle" UNSUPPORTED
        return 0
      fi
      ;;
  esac

  if "$lifecycle" start; then
    record_component provider "$lifecycle" RUNNING
  else
    rc=$?
    log "provider failed; continuing capability preflight: $lifecycle (exit=$rc)"
    record_component provider "$lifecycle" ERROR
  fi
  return 0
}

start_service(){
  local name="$1" script="$BASE/$1/start.sh" rc
  if [ ! -x "$script" ]; then
    log "service unavailable: missing $script"
    record_component service "$script" ERROR
    return 0
  fi
  if "$script"; then
    record_component service "$script" RUNNING
  else
    rc=$?
    log "service failed; continuing capability preflight: $name (exit=$rc)"
    record_component service "$script" ERROR
  fi
  return 0
}

stop_service(){
  local name="$1" script="$BASE/$1/stop.sh"
  if [ -x "$script" ]; then
    log "stop: $name"
    "$script" || true
  fi
}

stop_provider(){
  local lifecycle="$1"
  if [ -x "$lifecycle" ]; then
    log "stop provider: $(basename "$(dirname "$lifecycle")")"
    "$lifecycle" stop || true
  fi
}

teardown_all_once(){
  [ -e "$LOCK" ] && return 0
  : > "$LOCK"
  log "teardown: begin"
  local i
  for ((i=${#SERVICE_ORDER[@]}-1; i>=0; i--)); do
    stop_service "${SERVICE_ORDER[$i]}"
  done
  for ((i=${#PROVIDER_ORDER[@]}-1; i>=0; i--)); do
    stop_provider "${PROVIDER_ORDER[$i]}"
  done
  release_wake_lock
  rm -f "$SWITCH_FILE" "$WPID"
  log "teardown: done"
}

watch_switch(){
  log "switch: watcher started (file=$SWITCH_FILE)"
  while [ -e "$SWITCH_FILE" ]; do sleep 1; done
  log "switch: missing -> teardown"
  teardown_all_once
  exit 0
}

dirty_cleanup(){
  log "dirty: cleanup begin"
  rm -f "$LOCK"
  local old="" i
  [ -f "$WPID" ] && old="$(cat "$WPID" 2>/dev/null || true)"
  if [[ "$old" =~ ^[0-9]+$ ]] && kill -0 "$old" 2>/dev/null; then
    kill -TERM "$old" 2>/dev/null || true
  fi
  rm -f "$WPID"
  for ((i=${#SERVICE_ORDER[@]}-1; i>=0; i--)); do
    stop_service "${SERVICE_ORDER[$i]}"
  done
  for ((i=${#PROVIDER_ORDER[@]}-1; i>=0; i--)); do
    stop_provider "${PROVIDER_ORDER[$i]}"
  done
  log "dirty: cleanup done"
}

trap 'teardown_all_once; release_instance_lock' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

log "start: begin"
acquire_instance_lock || exit 0
discover_provider_lifecycles
dirty_cleanup

: > "$COMPONENT_STATE"
printf 'kind\tpath\tresult\n' > "$COMPONENT_STATE"

touch "$SWITCH_FILE"
chmod 644 "$SWITCH_FILE" 2>/dev/null || true
acquire_wake_lock
( watch_switch ) &
WATCH_PID=$!
echo "$WATCH_PID" > "$WPID"

for lifecycle in "${PROVIDER_ORDER[@]}"; do
  log "start provider: $(basename "$(dirname "$lifecycle")")"
  start_provider "$lifecycle"
done

for name in "${SERVICE_ORDER[@]}"; do
  log "start: $name"
  start_service "$name"
done

log "start: all non-root prerequisites active"
wait "$WATCH_PID"
