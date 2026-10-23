MOUNT_TARGETS=()

mount_if_needed() {
  local src="$1" dst="$2" opts="${3:-}" fstype="${4:-}"

  mkdir -p "$dst"

  if mountpoint -q "$dst"; then
    log "mount skip: $dst"
    MOUNT_TARGETS+=("$dst")
    return 0
  fi

  if [ -n "$fstype" ]; then
    log "mount: $src -> $dst (type=$fstype $opts)"
    mount -t "$fstype" $opts "$src" "$dst"
  else
    log "mount: $src -> $dst ($opts)"
    mount $opts "$src" "$dst"
  fi

  MOUNT_TARGETS+=("$dst")
}

umount_if_mounted() {
  local dst="$1"

  if mountpoint -q "$dst"; then
    log "umount: $dst"

    umount "$dst" 2>/dev/null ||
      umount -l "$dst" 2>/dev/null ||
      true
  fi
}

unmount_registered_reverse() {
  local i

  for ((i=${#MOUNT_TARGETS[@]}-1; i>=0; i--)); do
    umount_if_mounted "${MOUNT_TARGETS[$i]}"
  done
}

# Used by preflight.
# Unlike MOUNT_TARGETS, this discovers mounts left by an older implementation.
unmount_entire_chroot_tree() {
  local targets target

  targets="$(
    awk -v root="$CHROOT_DIR/" '
      index($5, root) == 1 {
        print length($5), $5
      }
    ' /proc/self/mountinfo 2>/dev/null |
    sort -nr |
    awk '{print $2}'
  )"

  [ -n "$targets" ] || return 0

  while IFS= read -r target; do
    [ -n "$target" ] || continue
    log "preflight: unmount stale $target"

    umount "$target" 2>/dev/null ||
      umount -l "$target" 2>/dev/null ||
      true
  done <<EOF_TARGETS
$targets
EOF_TARGETS
}
