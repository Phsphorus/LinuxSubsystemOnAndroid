#!/system/bin/sh

#
# Tier-D private /dev.
#
# 10-core.sh has already bound Android /dev and /dev/pts into
# the chroot. Cover that shared /dev with a fresh private tmpfs,
# then expose Android's real device namespace read-through at
# /dev/.host.
#
# No synthetic entries are ever created in Android /dev.
#

PRIVATE_DEV="$CHROOT_DIR/dev"
HOST_DEV="$PRIVATE_DEV/.host"
HOST_PTS="$HOST_DEV/pts"
PUBLIC_PTS="$PRIVATE_DEV/pts"


#
# Cover the Android-backed /dev from 10-core.sh.
#
# A newly-created tmpfs has no shared propagation tag on the
# supported Android kernels, so no mount propagation operation
# is required.
#
log "mount: private tmpfs -> $PRIVATE_DEV"

mount -t tmpfs \
    -o mode=755,nosuid \
    tmpfs \
    "$PRIVATE_DEV"

MOUNT_TARGETS+=("$PRIVATE_DEV")


#
# Re-expose Android /dev underneath the private namespace.
#
mkdir -p "$HOST_DEV"

log "mount: host /dev -> $HOST_DEV"

mount -o bind \
    /dev \
    "$HOST_DEV"

MOUNT_TARGETS+=("$HOST_DEV")


#
# Android's mount implementation does not provide a working
# recursive bind, so preserve devpts explicitly.
#
mkdir -p "$HOST_PTS"

log "mount: host /dev/pts -> $HOST_PTS"

mount -o bind \
    /dev/pts \
    "$HOST_PTS"

MOUNT_TARGETS+=("$HOST_PTS")


#
# The private tmpfs hides the earlier CoreChroot bind at /dev/pts. Rebind the
# host devpts mount at the public path after the tmpfs is in place so Linux
# pty users see the normal /dev/pts namespace.
#
mkdir -p "$PUBLIC_PTS"

log "mount: host /dev/pts -> $PUBLIC_PTS"

mount -o bind \
    /dev/pts \
    "$PUBLIC_PTS"

MOUNT_TARGETS+=("$PUBLIC_PTS")


#
# Mirror Android's visible top-level device names into private /dev.
#
# Do this with ONE ln invocation. Spawning Android's ln once per
# device is extremely expensive (~160 seconds for ~211 entries).
#
# Because we execute from $PRIVATE_DEV, each generated target is
# relative, e.g.:
#
#   /dev/null -> .host/null
#   /dev/pts  -> .host/pts
#
(
    cd "$PRIVATE_DEV" || exit 1

    # devpts is a public bind mount, not a symlink into the host read-through
    # tree. Do not replace its mountpoint with a symlink: Android ln correctly
    # rejects that as an existing entry and, with `set -e`, used to abort all
    # of RootStart.
    #
    # Build one bounded ln argument list for the remaining top-level nodes.
    # A single invocation is still important on Android, where starting ln
    # once per device node is prohibitively slow.
    set --
    for host_node in .host/*; do
        [ "$host_node" = '.host/pts' ] && continue
        [ -e "$host_node" ] || [ -L "$host_node" ] || continue
        set -- "$@" "$host_node"
    done

    [ "$#" -eq 0 ] || ln -s "$@" .
)

# FUSE is a capability required by the Linux sensor provider.  Some Android
# ln implementations do not reliably include this character device in the
# bulk mirror above, so publish this generic host-device view explicitly.
if [ -e "$HOST_DEV/fuse" ]; then
    ln -snf .host/fuse "$PRIVATE_DEV/fuse"
    if [ -e "$PRIVATE_DEV/fuse" ]; then
        log "mount: private /dev FUSE read-through ready"
    else
        log "ERROR: private /dev FUSE publication failed after host device bind"
    fi
else
    log "ERROR: host /dev/fuse is unavailable in the private device namespace"
fi

# Test through the chroot view as well. A separate SSH root shell can be in a
# different Android mount namespace, so this is the authoritative check for
# the namespace that Linux applications will actually receive.
if chroot "$CHROOT_DIR" /bin/sh -c '[ -e /dev/fuse ]' 2>/dev/null; then
    log "mount: chroot /dev/fuse reachable"
else
    log "ERROR: chroot /dev/fuse is not reachable"
fi

if chroot "$CHROOT_DIR" /bin/sh -c '[ -d /dev/pts ] && [ -e /dev/ptmx ]' 2>/dev/null; then
    log "mount: chroot devpts reachable"
else
    log "ERROR: chroot devpts is not reachable"
fi


#
# /dev/shm belongs exclusively to 15-dev-shm.sh, not Android.
#
rm -f "$PRIVATE_DEV/shm"
mkdir -p "$PRIVATE_DEV/shm"
chmod 1777 "$PRIVATE_DEV/shm"

log "mount: private /dev ready"
