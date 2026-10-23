#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

TERMUX_PREFIX="/data/data/com.termux/files/usr"
export PREFIX="$TERMUX_PREFIX"
# A root launch may originate in an interactive Termux-derived shell.  Do not
# inherit its command search path or dynamic-loader/Python overrides across
# the Android-root boundary.
export PATH="$TERMUX_PREFIX/bin:/system/bin:/system/xbin"
unset LD_LIBRARY_PATH LD_PRELOAD LD_AUDIT PYTHONPATH PYTHONHOME TMPDIR
export HOME=/root
umask 077

ROOTSTART="/data/local/RootStart"
# Android's mount tree is shared on the supported root environments.  The
# namespace launcher is mandatory before any LSA mount: without recursive
# private propagation, a private chroot /dev can hide host Binder devices.
# `--lsa-mountns-ready` is an internal re-exec marker consumed before public
# argument parsing; the launcher only accepts an absolute executable path.
if [ "${1:-}" = "--lsa-mountns-ready" ]; then
  shift
else
  MOUNTNS_LAUNCHER="$ROOTSTART/Tools/mountns/lsa-mountns"
  if [ ! -x "$MOUNTNS_LAUNCHER" ]; then
    printf '%s\n' "RootStart: missing required private mount-namespace launcher: $MOUNTNS_LAUNCHER" >&2
    exit 1
  fi
  exec "$MOUNTNS_LAUNCHER" "$TERMUX_PREFIX/bin/bash" "$0" --lsa-mountns-ready "$@"
fi

SERVICES="$ROOTSTART/Services"
MODCHROOT="$SERVICES/ModChroot/ModChroot.sh"
STARTED_SERVICES=()
ROOT_PROVIDER_ORDER=(
  "$ROOTSTART/Providers/Android/TermuxX11/lifecycle.sh"
)
STARTED_ROOT_PROVIDERS=()

# RootStart accepts only the explicit noninteractive runtime mode.  It is
# useful for deployment/ADB control and avoids treating the caller's terminal
# state as an implicit privilege or lifecycle input.
MODCHROOT_SESSION_ARG=""
case "${1:-}" in
  '') ;;
  --daemon) MODCHROOT_SESSION_ARG="--daemon" ;;
  *) printf '%s\n' "usage: $0 [--daemon]" >&2; exit 64 ;;
esac

log(){ printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

stop_started_services(){ local i svc; for ((i=${#STARTED_SERVICES[@]}-1; i>=0; i--)); do svc="${STARTED_SERVICES[$i]}"; if [ -x "$svc/stop.sh" ]; then log "RootStart: stopping $(basename "$svc")"; "$svc/stop.sh" || true; fi; done; }

stop_root_providers(){ local i lifecycle; for ((i=${#ROOT_PROVIDER_ORDER[@]}-1; i>=0; i--)); do lifecycle="${ROOT_PROVIDER_ORDER[$i]}"; if [ -x "$lifecycle" ]; then log "RootStart: stopping provider $(basename "$(dirname "$lifecycle")")"; "$lifecycle" stop || true; fi; done; }

start_root_providers(){
  local lifecycle
  for lifecycle in "${ROOT_PROVIDER_ORDER[@]}"; do
    if [ ! -x "$lifecycle" ]; then
      log "RootStart: optional provider lifecycle missing: $lifecycle"
      continue
    fi
    log "RootStart: starting provider $(basename "$(dirname "$lifecycle")")"
    if "$lifecycle" start; then
      STARTED_ROOT_PROVIDERS+=("$lifecycle")
    else
      # A root-side Android integration (currently Termux:X11) is a capability
      # candidate, not a prerequisite for mounting and starting Linux. Its
      # provider probe/report remains the source of the support diagnostic.
      log "RootStart: optional provider unavailable; continuing: $lifecycle"
    fi
  done
}

stop_existing_services(){ local svc name; for svc in "$SERVICES"/*; do [ -d "$svc" ] || continue; name="$(basename "$svc")"; [ "$name" = "ModChroot" ] && continue; [ -x "$svc/stop.sh" ] || continue; log "RootStart: clearing old $name"; "$svc/stop.sh" || true; done; }

cleanup_all(){ set +e; log "RootStart: tearing down ModChroot"; "$MODCHROOT" --preflight || true; stop_root_providers; stop_started_services; }

trap 'cleanup_all' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

SELINUX_MODE="$(getenforce 2>/dev/null || echo unknown)"
# Production startup never alters host SELinux enforcement.  A backend which
# cannot run in the current mode must report/fall back through its capability
# contract; global Permissive is an explicit developer action outside LSA.
log "RootStart: SELinux=$SELINUX_MODE"
if [ "$SELINUX_MODE" = Permissive ]; then
  log "RootStart: WARNING host SELinux is Permissive; LSA did not request this mode"
fi

stop_existing_services
stop_root_providers

log "RootStart: ModChroot preflight"
"$MODCHROOT" --preflight

for svc in "$SERVICES"/*; do
  [ -d "$svc" ] || continue
  name="$(basename "$svc")"
  [ "$name" = "ModChroot" ] && continue
  [ -x "$svc/start.sh" ] || continue
  log "RootStart: starting $name"
  if "$svc/start.sh"; then
    STARTED_SERVICES+=("$svc")
  else
    # Root-side helpers publish optional capabilities.  A missing resolver,
    # HAL endpoint, or other helper must be visible in its own diagnostics but
    # must not prevent the framework from starting the remaining Linux stack.
    log "RootStart: supporting service unavailable; continuing: $name"
  fi
done

start_root_providers

log "RootStart: starting ModChroot LAST${MODCHROOT_SESSION_ARG:+ ($MODCHROOT_SESSION_ARG)}"
if [ -n "$MODCHROOT_SESSION_ARG" ]; then
  "$MODCHROOT" "$MODCHROOT_SESSION_ARG"
else
  "$MODCHROOT"
fi
