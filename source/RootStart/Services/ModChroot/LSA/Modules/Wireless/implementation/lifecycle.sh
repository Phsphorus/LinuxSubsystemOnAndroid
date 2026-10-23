#!/data/data/com.termux/files/usr/bin/bash
set -u

WIRELESS_MODULE_BASE="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIRELESS_RUNTIME_DIR="${LSA_RUNTIME_DIR:-/data/local/RootStart/Services/ModChroot/runtime/capability-framework}"
WIRELESS_STATE="$WIRELESS_RUNTIME_DIR/wireless.tsv"
WIRELESS_OWNER_DIR="$WIRELESS_RUNTIME_DIR/wireless-owned"

wireless_primary_interface() {
    awk -F '\t' 'NR > 1 && $1 == "interface" && $2 == "host.primary" && $3 == "AVAILABLE" { print $5; exit }' "$WIRELESS_STATE" 2>/dev/null
}

wireless_rootfs_interface_visible() {
    local interface="$1"
    [ -n "$interface" ] && [ -e "$LSA_CHROOT_DIR/sys/class/net/$interface" ]
}

wireless_owned_state() {
    printf '%s/%s.state' "$WIRELESS_OWNER_DIR" "$1"
}

wireless_start_host_interface() {
    local interface state
    interface="$(wireless_primary_interface)"
    [ -n "$interface" ] || { printf 'no safe host wireless interface was inventoried'; return 1; }
    wireless_rootfs_interface_visible "$interface" || { printf 'Linux rootfs cannot see host interface %s' "$interface"; return 1; }
    mkdir -p "$WIRELESS_OWNER_DIR"
    chmod 700 "$WIRELESS_OWNER_DIR" 2>/dev/null || true
    state="$(wireless_owned_state host-interface)"
    {
        printf 'interface=%s\n' "$interface"
        printf 'owner=wireless.host-interface\n'
        printf 'started_utc=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    } > "$state"
    chmod 600 "$state" 2>/dev/null || true
    printf 'Linux-visible host wireless interface active: %s' "$interface"
}

wireless_start_termux_uplink() {
    local interface state
    interface="$(wireless_primary_interface)"
    [ -n "$interface" ] || { printf 'no Android wireless uplink is visible'; return 1; }
    mkdir -p "$WIRELESS_OWNER_DIR"
    chmod 700 "$WIRELESS_OWNER_DIR" 2>/dev/null || true
    state="$(wireless_owned_state termux-uplink)"
    {
        printf 'interface=%s\n' "$interface"
        printf 'owner=wireless.termux-uplink\n'
        printf 'started_utc=%s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    } > "$state"
    chmod 600 "$state" 2>/dev/null || true
    printf 'Termux-backed Linux socket uplink active through %s' "$interface"
}

wireless_stop_owned() {
    local owner="$1" state
    state="$(wireless_owned_state "$owner")"
    [ -e "$state" ] || { printf 'no %s state owned by this backend' "$owner"; return 0; }
    rm -f "$state"
    printf 'removed only %s-owned wireless state' "$owner"
}

wireless_status_owned() {
    local owner="$1" state interface
    state="$(wireless_owned_state "$owner")"
    [ -r "$state" ] || { printf STOPPED; return 0; }
    interface="$(sed -n 's/^interface=//p' "$state" | head -n 1)"
    if [ -n "$interface" ] && [ -e "/sys/class/net/$interface" ]; then
        printf RUNNING
    else
        printf DEGRADED
    fi
}

wireless_health_host_interface() {
    local interface
    interface="$(wireless_primary_interface)"
    [ -n "$interface" ] || { printf 'no primary wireless interface in inventory'; return 1; }
    wireless_rootfs_interface_visible "$interface" || { printf 'rootfs does not expose /sys/class/net/%s' "$interface"; return 1; }
    [ -r "$LSA_CHROOT_DIR/proc/net/dev" ] || { printf 'rootfs cannot read standard /proc/net/dev'; return 1; }
    grep -q "^[[:space:]]*$interface:" "$LSA_CHROOT_DIR/proc/net/dev" || { printf 'rootfs /proc/net/dev does not list %s' "$interface"; return 1; }
    printf 'Linux sees %s through standard /sys/class/net and /proc/net/dev; packet transfer remains separately verified' "$interface"
}

wireless_health_termux_uplink() {
    local interface
    interface="$(wireless_primary_interface)"
    [ -n "$interface" ] || { printf 'no Android wireless uplink in inventory'; return 1; }
    [ -r /proc/net/route ] || { printf 'host routing table is unavailable'; return 1; }
    printf 'Android-owned %s uplink is present; this compatibility tier exposes normal Linux sockets only' "$interface"
}
