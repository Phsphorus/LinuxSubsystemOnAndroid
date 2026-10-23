#!/system/bin/sh
set -eu

# The device provider owns Android acquisition. This module owns the verified
# Linux H.264 consumer asset and its ordinary Linux command entrypoint.
lsa_video_encode_install_rootfs() {
  base="${START_CHROOT_BASE:-/data/local/RootStart/Services/ModChroot}"
  root="${CHROOT_DIR:-/data/local/linux}"
  source="$base/LSA/Modules/VideoEncode/implementation/rootfs"
  destination="$root/usr/local/lib/lsa/video"
  [ -x "$source/lsa_ahb_encode" ] || {
    echo "ModChroot: video: verified consumer asset missing: $source/lsa_ahb_encode" >&2
    return 1
  }
  mkdir -p "$destination" "$root/usr/local/bin"
  install -m 755 "$source/lsa_ahb_encode" "$destination/lsa_ahb_encode"
  install -m 755 "$source/lsa-h264-encode" "$root/usr/local/bin/lsa-h264-encode"
  if command -v log >/dev/null 2>&1; then
    log "video: injected module-owned Linux H.264 consumer"
  else
    echo "ModChroot: video: injected module-owned Linux H.264 consumer"
  fi
}
