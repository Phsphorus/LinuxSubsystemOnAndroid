mkdir -p \
  "$CHROOT_DIR/mnt/halbridge/cam" \
  "$CHROOT_DIR/mnt/halbridge/rec" \
  "$CHROOT_DIR/mnt/halbridge/secret"

if [ -d "$HALBRIDGE/cam" ]; then
  mount_if_needed "$HALBRIDGE/cam" \
    "$CHROOT_DIR/mnt/halbridge/cam" \
    "--bind"
fi

if [ -d "$HALBRIDGE/rec" ]; then
  mount_if_needed "$HALBRIDGE/rec" \
    "$CHROOT_DIR/mnt/halbridge/rec" \
    "--bind"
fi

if [ -d "$SECRET_DIR" ]; then
  mount_if_needed "$SECRET_DIR" \
    "$CHROOT_DIR/mnt/halbridge/secret" \
    "--bind"
fi
