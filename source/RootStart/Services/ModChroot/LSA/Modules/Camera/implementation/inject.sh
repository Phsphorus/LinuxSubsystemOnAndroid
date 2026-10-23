#!/data/data/com.termux/files/usr/bin/bash
set -eu
# This file is sourced by ModChroot.  Keep its path variables module-scoped:
# changing the caller's BASE made later module injectors resolve beneath the
# camera implementation directory rather than the ModChroot service root.
CAMERA_INJECT_BASE="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAMERA_ROOTFS="$CAMERA_INJECT_BASE/rootfs"
CAMERA_DEST="${CHROOT_DIR:-/data/local/linux}"

install -d -m 755 -o 0 -g 0 "$CAMERA_DEST/usr/local/lib/lsa" "$CAMERA_DEST/usr/local/bin"
install -m 644 -o 0 -g 0 "$CAMERA_ROOTFS/lsa-camera/liblsa_camera_v4l2.c" "$CAMERA_DEST/usr/local/lib/lsa/liblsa_camera_v4l2.c"
install -m 755 -o 0 -g 0 "$CAMERA_ROOTFS/lsa-camera/camera-record" "$CAMERA_DEST/usr/local/bin/camera-record"
