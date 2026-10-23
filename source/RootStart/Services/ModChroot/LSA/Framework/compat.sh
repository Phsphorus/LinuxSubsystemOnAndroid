#!/data/data/com.termux/files/usr/bin/bash
# Shared, intentionally small compatibility helpers for descriptor callbacks.

LSA_TERMUX_HOME="${LSA_TERMUX_HOME:-/data/data/com.termux/files/home}"
LSA_TERMUX_PREFIX="${LSA_TERMUX_PREFIX:-/data/data/com.termux/files/usr}"
LSA_NONROOT_BASE="${LSA_NONROOT_BASE:-$LSA_TERMUX_HOME/NonRootStart}"
LSA_ROOTSTART_BASE="${LSA_ROOTSTART_BASE:-/data/local/RootStart}"

lsa_compat_pid_file_running() {
    local pidfile="$1" pid
    [ -f "$pidfile" ] || return 1
    pid="$(tr -cd '0-9' <"$pidfile" 2>/dev/null)"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

lsa_compat_mount_present() {
    local target="$1"
    grep -F " $target " /proc/mounts >/dev/null 2>&1
}

lsa_compat_chroot_path() {
    printf '%s%s' "$LSA_CHROOT_DIR" "$1"
}
