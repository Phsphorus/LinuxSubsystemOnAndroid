#!/system/bin/sh

# 12-private-dev.sh has established the chroot-private /dev.
# Give that private namespace a real POSIX shared-memory tmpfs and
# register it through ModChroot's normal reverse-order teardown.

mkdir -p "$CHROOT_DIR/dev/shm"
chmod 1777 "$CHROOT_DIR/dev/shm"

mount_if_needed \
    tmpfs \
    "$CHROOT_DIR/dev/shm" \
    "-o mode=1777,nosuid,nodev" \
    tmpfs

chmod 1777 "$CHROOT_DIR/dev/shm"
