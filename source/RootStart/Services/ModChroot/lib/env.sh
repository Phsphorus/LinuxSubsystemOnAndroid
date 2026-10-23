CHROOT_ENV_VARS=()

load_chroot_environment() {
  local f

  CHROOT_ENV_VARS=()

  for f in "$START_CHROOT_BASE"/env.d/*.env; do
    [ -f "$f" ] || continue
    log "env: loading $(basename "$f")"
    # shellcheck source=/dev/null
    source "$f"
  done
}

print_chroot_environment() {
  local item
  for item in "${CHROOT_ENV_VARS[@]}"; do
    log "env: $item"
  done
}
