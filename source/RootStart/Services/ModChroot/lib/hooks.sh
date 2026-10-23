run_hooks() {
  local phase="$1"
  local dir="$START_CHROOT_BASE/hooks.d/$phase"
  local f

  [ -d "$dir" ] || return 0

  for f in "$dir"/*; do
    [ -f "$f" ] || continue
    log "hook[$phase]: $(basename "$f")"

    if [ -x "$f" ]; then
      "$f"
    else
      # shellcheck source=/dev/null
      source "$f"
    fi
  done
}
