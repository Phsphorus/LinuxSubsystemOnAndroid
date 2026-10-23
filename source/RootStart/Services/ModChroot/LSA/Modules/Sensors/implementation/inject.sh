#!/data/data/com.termux/files/usr/bin/bash

# The Sensors module owns its Linux-side implementation. Injection is a
# module operation, not a duplicate source tree in the generic rootfs overlay.
lsa_sensors_install_rootfs() {
    local module_base source destination
    module_base="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    source="$module_base/src"
    destination="$CHROOT_DIR/usr/local/lib/lsa/sensors"
    [ -d "$source" ] || { log "sensors: source missing $source"; return 1; }
    mkdir -p "$destination"
    cp -a "$source"/. "$destination"/
    chmod 755 "$destination"/*.py 2>/dev/null || true
    log "sensors: injected module-owned IIO implementation"
}
