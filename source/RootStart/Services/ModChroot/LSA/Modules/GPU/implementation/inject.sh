#!/data/data/com.termux/files/usr/bin/bash

# Install the Linux-side VirGL client policy.  The Android provider owns the
# server; this module only makes the already-mounted endpoint usable by Debian
# applications and sessions.
lsa_gpu_install_rootfs() {
  local root source destination
  root="${CHROOT_DIR:-/data/local/linux}"
  source="$BASE/LSA/Modules/GPU/implementation/rootfs"
  destination="$root/usr/local/lib/lsa/gpu"

  [ -d "$source" ] || {
    log "gpu: rootfs source directory missing: $source"
    return 1
  }

  install -d -m 755 -o 0 -g 0 "$destination" "$root/etc/profile.d"
  install -m 644 -o 0 -g 0 "$source/lsa-gpu-env.sh" "$destination/lsa-gpu-env.sh"
  install -m 644 -o 0 -g 0 "$source/30-lsa-gpu.sh" "$root/etc/profile.d/30-lsa-gpu.sh"
  install -m 755 -o 0 -g 0 "$source/dolphin-emu" "$root/usr/local/bin/dolphin-emu"
  log "gpu: installed VirGL client policy for Debian sessions"
}
