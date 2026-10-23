#!/data/data/com.termux/files/usr/bin/bash

# DeviceNamespace publishes the generic Linux /dev/fuse character device.
# The FUSE module owns the Linux-facing capability boundary; concrete mounts
# (such as Sensors' IIO overlay) remain owned by their respective modules.
FUSE_MODULE_DEVICE="${LSA_CHROOT_DIR:-${CHROOT_DIR:-/data/local/linux}}/dev/fuse"

backend_fuse_userspace_start() {
    if [ ! -e "$FUSE_MODULE_DEVICE" ]; then
        printf 'Linux FUSE device is unavailable: %s' "$FUSE_MODULE_DEVICE"
        return 1
    fi
    printf 'generic Linux userspace FUSE capability activated on %s' "$FUSE_MODULE_DEVICE"
}

backend_fuse_userspace_stop() {
    # A generic capability has no provider process to terminate. Individual
    # FUSE mounts are lifecycle-owned by the modules that created them.
    printf 'generic Linux userspace FUSE capability released'
}

backend_fuse_userspace_status() {
    if [ -e "$FUSE_MODULE_DEVICE" ]; then printf RUNNING; else printf STOPPED; fi
}
