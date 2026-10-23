mount_if_needed /dev \
  "$CHROOT_DIR/dev" \
  "-o bind"

mount_if_needed /dev/pts \
  "$CHROOT_DIR/dev/pts" \
  "-o bind"

mount_if_needed /proc \
  "$CHROOT_DIR/proc" \
  "" \
  "proc"

mount_if_needed /sys \
  "$CHROOT_DIR/sys" \
  "" \
  "sysfs"
