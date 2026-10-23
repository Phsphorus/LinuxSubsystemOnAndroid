#!/data/data/com.termux/files/usr/bin/bash

# The D-Bus module owns only the generic Linux system bus it starts. If another
# supervisor has already supplied a system socket, this module consumes it and
# never kills a process it does not own.
DBUS_CHROOT_DIR="${LSA_CHROOT_DIR:-${CHROOT_DIR:-/data/local/linux}}"
DBUS_SOCKET="$DBUS_CHROOT_DIR/run/dbus/system_bus_socket"
DBUS_PID_FILE="$DBUS_CHROOT_DIR/run/dbus/lsa-system.pid"
DBUS_PATH="${CHROOT_PATH:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"
DBUS_LAUNCH_HELPER="/usr/lib/dbus-1.0/dbus-daemon-launch-helper"
DBUS_IMPLEMENTATION_DIR="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DBUS_ISOLATED_LAUNCHER="${DBUS_ISOLATED_LAUNCHER:-$DBUS_IMPLEMENTATION_DIR/isolated-system-bus.py}"
DBUS_ISOLATED_RUNTIME_DIR="${RUNTIME_DIR:-/data/local/RootStart/Services/ModChroot/runtime}"
DBUS_ISOLATED_LOG_FILE="${DBUS_ISOLATED_LOG_FILE:-$DBUS_ISOLATED_RUNTIME_DIR/system-dbus.log}"
DBUS_ISOLATED_STAGE_ROOT="${DBUS_ISOLATED_STAGE_ROOT:-$DBUS_ISOLATED_RUNTIME_DIR/system-dbus-stage}"
# Normal boot inherits ModChroot's PID. A live repair can override this with
# that same long-lived supervisor rather than tying the bus to a short shell.
DBUS_OWNER_PID="${DBUS_OWNER_PID:-$$}"

dbus_module_pid_running() {
    [ -f "$DBUS_PID_FILE" ] || return 1
    local pid
    pid="$(tr -cd '0-9' <"$DBUS_PID_FILE" 2>/dev/null)"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

dbus_module_socket_usable() {
    [ -S "$DBUS_SOCKET" ] || return 1
    [ -x "$DBUS_CHROOT_DIR/usr/bin/dbus-send" ] || return 1
    chroot "$DBUS_CHROOT_DIR" /usr/bin/env -i PATH="$DBUS_PATH" \
        /usr/bin/dbus-send --system \
        --dest=org.freedesktop.DBus --type=method_call \
        --print-reply / org.freedesktop.DBus.ListNames >/dev/null 2>&1
}

dbus_module_rootfs_nosuid() {
    # A normal system bus can answer ListNames while its setuid launch helper
    # is still unusable. This check describes the default desktop rootfs only.
    [ -x "$DBUS_CHROOT_DIR/usr/bin/python3" ] || return 1
    chroot "$DBUS_CHROOT_DIR" /usr/bin/env -i PATH="$DBUS_PATH" \
        /usr/bin/python3 -c '
import os
raise SystemExit(0 if os.statvfs("/").f_flag & getattr(os, "ST_NOSUID", 2) else 1)
' >/dev/null 2>&1
}

dbus_module_pid_uses_private_suid_rootfs() {
    # The launcher itself remains outside the chroot so it can reliably close
    # the clone. Enter only its mount namespace and inspect the rootfs there.
    local pid
    dbus_module_pid_running || return 1
    pid="$(tr -cd '0-9' <"$DBUS_PID_FILE" 2>/dev/null)"
    [ -n "$pid" ] && [ -r "/proc/$pid/mountinfo" ] || return 1
    printf '%s\n' \
        'import os' \
        'raise SystemExit(0 if not (os.statvfs("/").f_flag & getattr(os, "ST_NOSUID", 2)) else 1)' |
        nsenter -t "$pid" -m chroot "$DBUS_CHROOT_DIR" /usr/bin/python3 >/dev/null 2>&1
}

dbus_module_clear_stale_owned_state() {
    [ -f "$DBUS_PID_FILE" ] || return 1
    local pid
    pid="$(tr -cd '0-9' <"$DBUS_PID_FILE" 2>/dev/null)"
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && return 2
    rm -f "$DBUS_PID_FILE" "$DBUS_SOCKET"
    return 0
}

dbus_module_repair_launch_helper() {
    # Debian installs this helper setuid root and group-executable by
    # messagebus. A rootfs copied or repaired through an Android app UID can
    # retain the setuid mode while changing its owner and group, which leaves
    # messagebus unable to execute activation helpers.
    [ -e "$DBUS_CHROOT_DIR$DBUS_LAUNCH_HELPER" ] || return 0

    local messagebus_gid actual expected
    messagebus_gid="$(chroot "$DBUS_CHROOT_DIR" /usr/bin/env -i PATH="$DBUS_PATH" /usr/bin/id -g messagebus 2>/dev/null)" || {
        printf 'unable to resolve the messagebus group for the D-Bus launch helper'
        return 1
    }
    case "$messagebus_gid" in
        ''|*[!0-9]*)
            printf 'invalid messagebus group for the D-Bus launch helper'
            return 1
            ;;
    esac

    expected="0:$messagebus_gid:4754"
    actual="$(chroot "$DBUS_CHROOT_DIR" /usr/bin/env -i PATH="$DBUS_PATH" /usr/bin/stat -c '%u:%g:%a' "$DBUS_LAUNCH_HELPER" 2>/dev/null)" || {
        printf 'unable to inspect the D-Bus launch helper'
        return 1
    }
    [ "$actual" = "$expected" ] && return 0

    chroot "$DBUS_CHROOT_DIR" /usr/bin/env -i PATH="$DBUS_PATH" \
        /usr/bin/chown root:messagebus "$DBUS_LAUNCH_HELPER" || {
        printf 'unable to restore D-Bus launch-helper ownership'
        return 1
    }
    chroot "$DBUS_CHROOT_DIR" /usr/bin/env -i PATH="$DBUS_PATH" \
        /usr/bin/chmod 4754 "$DBUS_LAUNCH_HELPER" || {
        printf 'unable to restore D-Bus launch-helper mode'
        return 1
    }

    actual="$(chroot "$DBUS_CHROOT_DIR" /usr/bin/env -i PATH="$DBUS_PATH" /usr/bin/stat -c '%u:%g:%a' "$DBUS_LAUNCH_HELPER" 2>/dev/null)" || actual=''
    if [ "$actual" != "$expected" ]; then
        printf 'D-Bus launch-helper repair did not produce %s (got %s)' "$expected" "${actual:-missing}"
        return 1
    fi
}

dbus_module_start_isolated() {
    local daemon_pid
    [ -r "$DBUS_ISOLATED_LAUNCHER" ] || {
        printf 'isolated D-Bus launcher is missing: %s' "$DBUS_ISOLATED_LAUNCHER"
        return 1
    }
    mkdir -p "$DBUS_CHROOT_DIR/run/dbus" "$DBUS_ISOLATED_RUNTIME_DIR"
    rm -f "$DBUS_SOCKET" "$DBUS_PID_FILE"
    : >"$DBUS_ISOLATED_LOG_FILE"
    chmod 600 "$DBUS_ISOLATED_LOG_FILE" 2>/dev/null || true

    python "$DBUS_ISOLATED_LAUNCHER" \
        --rootfs "$DBUS_CHROOT_DIR" \
        --stage-root "$DBUS_ISOLATED_STAGE_ROOT" \
        --owner-pid "$DBUS_OWNER_PID" \
        >>"$DBUS_ISOLATED_LOG_FILE" 2>&1 &
    daemon_pid="$!"
    printf '%s\n' "$daemon_pid" >"$DBUS_PID_FILE"

    for _ in $(seq 1 50); do
        dbus_module_socket_usable && dbus_module_pid_uses_private_suid_rootfs && {
            printf 'LSA-owned Linux system D-Bus started in a private suid rootfs clone'
            return 0
        }
        kill -0 "$daemon_pid" 2>/dev/null || break
        sleep 0.1
    done

    kill -TERM "$daemon_pid" 2>/dev/null || true
    rm -f "$DBUS_PID_FILE" "$DBUS_SOCKET"
    printf 'isolated Linux system D-Bus did not become usable; inspect %s' "$DBUS_ISOLATED_LOG_FILE"
    return 1
}

dbus_module_start_standard() {
    local daemon_pid
    daemon_pid="$(
        chroot "$DBUS_CHROOT_DIR" /usr/bin/env -i PATH="$DBUS_PATH" \
            /usr/bin/dbus-daemon --system --fork --nopidfile --print-pid=1 |
            tr -cd '0-9'
    )"
    if ! echo "$daemon_pid" | grep -Eq '^[0-9]+$'; then
        printf 'dbus-daemon did not return an owned PID'
        return 1
    fi
    printf '%s\n' "$daemon_pid" >"$DBUS_PID_FILE"

    for _ in $(seq 1 30); do
        dbus_module_socket_usable && {
            printf 'LSA-owned Linux system D-Bus started'
            return 0
        }
        sleep 0.1
    done

    printf 'Linux system D-Bus did not create %s' "$DBUS_SOCKET"
    return 1
}

backend_dbus_system_start() {
    [ -x "$DBUS_CHROOT_DIR/usr/bin/dbus-daemon" ] || {
        printf 'Debian dbus-daemon is unavailable in %s' "$DBUS_CHROOT_DIR"
        return 1
    }
    dbus_module_repair_launch_helper || return 1

    if dbus_module_socket_usable; then
        if ! dbus_module_rootfs_nosuid; then
            printf 'Linux system D-Bus socket already available and accepting requests'
            return 0
        fi
        if dbus_module_pid_uses_private_suid_rootfs; then
            printf 'isolated Linux system D-Bus socket already available and accepting requests'
            return 0
        fi
        if dbus_module_pid_running; then
            backend_dbus_system_stop || return 1
        else
            printf 'an unowned Linux system D-Bus is running on a nosuid rootfs; refusing to replace it'
            return 1
        fi
    fi

    if [ -S "$DBUS_SOCKET" ]; then
        if dbus_module_clear_stale_owned_state; then
            :
        elif [ "$?" -eq 2 ]; then
            printf 'LSA-owned D-Bus PID is alive but its socket is not accepting requests'
            return 1
        else
            printf 'unowned Linux system D-Bus socket is not accepting requests'
            return 1
        fi
    elif [ -f "$DBUS_PID_FILE" ]; then
        if ! dbus_module_clear_stale_owned_state; then
            printf 'LSA-owned D-Bus PID is alive but its socket is absent'
            return 1
        fi
    fi

    if dbus_module_rootfs_nosuid; then
        dbus_module_start_isolated
    else
        dbus_module_start_standard
    fi
}

backend_dbus_system_stop() {
    if ! dbus_module_pid_running; then
        rm -f "$DBUS_PID_FILE"
        printf 'no LSA-owned Linux system D-Bus PID to stop'
        return 0
    fi

    local pid
    pid="$(tr -cd '0-9' <"$DBUS_PID_FILE" 2>/dev/null)"
    kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 50); do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.1
    done
    if kill -0 "$pid" 2>/dev/null; then
        printf 'LSA-owned Linux system D-Bus did not stop cleanly'
        return 1
    fi
    rm -f "$DBUS_PID_FILE" "$DBUS_SOCKET"
    printf 'LSA-owned Linux system D-Bus stopped'
}

backend_dbus_system_status() {
    if ! dbus_module_socket_usable; then
        printf STOPPED
    elif dbus_module_rootfs_nosuid && ! dbus_module_pid_uses_private_suid_rootfs; then
        printf DEGRADED
    else
        printf RUNNING
    fi
}

