#!/system/bin/sh
BASE="/data/local/RootStart/Services/ModChroot"
CONFIG="$BASE/config/config.sh"
[ -f "$CONFIG" ] && . "$CONFIG"
CHROOT_DIR="${CHROOT_DIR:-/data/local/linux}"
SRC="$BASE/injects/rootfs"

ensure_public_rootfs_dir() {
  # These are rootfs path components, not private service state.  Every
  # regular Linux user must be able to traverse them to execute /bin/sh,
  # /bin/bash, desktop applications, and module-provided helpers.
  [ -d "$1" ] || return 0
  chown 0:0 "$1"
  chmod 755 "$1"
}

copy_public_file() {
  source_file="$1"
  target_file="$2"
  target_mode="$3"
  target_dir="$(dirname "$target_file")"
  mkdir -p "$target_dir"
  chown 0:0 "$target_dir"
  chmod 755 "$target_dir"
  cp -f "$source_file" "$target_file"
  chown 0:0 "$target_file"
  chmod "$target_mode" "$target_file"
}

# Older releases used `cp -a "$SRC"/. "$CHROOT_DIR"/`.  That preserved the
# release-tree directory mode (0770) on rootfs parents and prevented normal
# users from traversing /usr, which made `su myuser` fail at /bin/bash.
for path in \
  "$CHROOT_DIR" \
  "$CHROOT_DIR/usr" \
  "$CHROOT_DIR/usr/local" \
  "$CHROOT_DIR/usr/local/bin" \
  "$CHROOT_DIR/usr/local/lib"
do
  ensure_public_rootfs_dir "$path"
done

if [ -d "$SRC" ]; then
  if command -v log >/dev/null 2>&1; then
    log "inject: applying rootfs overlay $SRC"
  else
    echo "ModChroot inject: applying $SRC"
  fi

  copy_public_file "$SRC/usr/local/bin/androidctl" \
    "$CHROOT_DIR/usr/local/bin/androidctl" 755

  CLIENT_SRC="$SRC/usr/local/lib/halbridge/androidctl_client"
  CLIENT_DST="$CHROOT_DIR/usr/local/lib/halbridge/androidctl_client"
  if [ -d "$CLIENT_SRC" ]; then
    mkdir -p "$CLIENT_DST"
    chown 0:0 "$CHROOT_DIR/usr/local/lib/halbridge" "$CLIENT_DST"
    chmod 755 "$CHROOT_DIR/usr/local/lib/halbridge" "$CLIENT_DST"
    for source_file in "$CLIENT_SRC"/*.py; do
      [ -f "$source_file" ] || continue
      copy_public_file "$source_file" "$CLIENT_DST/$(basename "$source_file")" 644
    done
  fi

  # The framework owns this directory.  It remains traversable but is never
  # populated through a metadata-preserving recursive overlay copy.
  mkdir -p "$CHROOT_DIR/usr/local/lib/lsa/sensorproxy"
  chown 0:0 "$CHROOT_DIR/usr/local/lib/lsa" "$CHROOT_DIR/usr/local/lib/lsa/sensorproxy"
  chmod 755 "$CHROOT_DIR/usr/local/lib/lsa" "$CHROOT_DIR/usr/local/lib/lsa/sensorproxy"
fi
