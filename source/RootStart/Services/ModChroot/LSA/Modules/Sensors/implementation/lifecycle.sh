#!/system/bin/sh
set -u

CHROOT_DIR="${CHROOT_DIR:-/data/local/linux}"

LIB="/usr/local/lib/lsa/sensors"
RUN="/run/lsa-iio"
TMP="/tmp/lsa-iio"
SYS="/sys/bus/iio/devices"

H_RUN="$CHROOT_DIR$RUN"
H_TMP="$CHROOT_DIR$TMP"
H_SYS="$CHROOT_DIR$SYS"

CHROOT_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

log()
{
    echo "ModChroot: sensor: $*"
}

in_chroot()
{
    chroot "$CHROOT_DIR" \
        /usr/bin/env -i \
        HOME=/root \
        PATH="$CHROOT_PATH" \
        "$@"
}

mounted()
{
    grep -F " $1 " /proc/mounts >/dev/null 2>&1
}

stop_pidfile()
{
    name="$1"
    file="$H_RUN/$name.pid"

    [ -f "$file" ] || return 0

    pid="$(cat "$file" 2>/dev/null || true)"

    rm -f "$file"

    [ -n "$pid" ] || return 0

    if kill -0 "$pid" 2>/dev/null; then
        log "stopping $name pid=$pid"

        kill -TERM "$pid" 2>/dev/null || true

        n=0
        while kill -0 "$pid" 2>/dev/null
        do
            n=$((n + 1))

            [ "$n" -lt 5 ] || break
            sleep 1
        done

        if kill -0 "$pid" 2>/dev/null; then
            log "forcing $name pid=$pid"
            kill -KILL "$pid" 2>/dev/null || true
        fi
    fi
}

stop_pattern()
{
    pattern="$1"

    chroot "$CHROOT_DIR" \
        /usr/bin/env -i \
        PATH="$CHROOT_PATH" \
        /usr/bin/pkill \
        -TERM \
        -f "$pattern" \
        2>/dev/null || true
}


unmount_all()
{
    target="$1"

    while mounted "$target"
    do
        log "unmounting $target"

        umount "$target" 2>/dev/null || {
            log "lazy unmount $target"
            umount -l "$target" 2>/dev/null || break
        }
    done
}

cleanup_synthetic_dev()
{
    registry="$H_RUN/registry.json"
    list="$H_RUN/synthetic-devices.list"

    [ -f "$registry" ] || return 0

    in_chroot /usr/bin/python3 - <<'PY' >"$list" 2>/dev/null || return 0
import json

with open("/run/lsa-iio/registry.json") as f:
    r = json.load(f)

for d in r.get("devices", []):
    print(d["dirname"])
PY

    while IFS= read -r dirname
    do
        [ -n "$dirname" ] || continue

        path="$CHROOT_DIR/dev/$dirname"

        #
        # Registry contains synthetic devices only.
        # Native device0/device1 etc. are never listed here.
        #
        rm -f "$path" 2>/dev/null || true

    done <"$list"

    rm -f "$list"
}

build_shim()
{
    log "building target-native IIO event shim"

    in_chroot \
        /usr/bin/gcc \
        -shared \
        -fPIC \
        -O2 \
        -Wall \
        -Wextra \
        -o /usr/local/lib/lsa/liblsa-iio-eventshim.so \
        "$LIB/lsa_iio_eventshim.c"
}

generate_registry()
{
    log "generating sensor registry"

    in_chroot \
        /usr/bin/python3 \
        "$LIB/LSAIIORegistry.py"
}

verify_fuse_device()
{
    # Opening the device is stronger than a path-existence check.  The proxy
    # runs in this same chroot context, so this gives the selected backend a
    # precise capability failure if the Android private-device namespace has
    # not propagated a usable FUSE character device.
    log "checking chroot FUSE device"

    in_chroot \
        /usr/bin/python3 \
        -c 'import os; fd = os.open("/dev/fuse", os.O_RDWR); os.close(fd)'
}

start_process()
{
    name="$1"
    script="$2"
    shift 2

    log "starting $name"

    chroot "$CHROOT_DIR" \
        /usr/bin/env -i \
        HOME=/root \
        PATH="$CHROOT_PATH" \
        /usr/bin/python3 \
        "$LIB/$script" \
        "$@" \
        >"$H_RUN/$name.log" 2>&1 &

    pid=$!

    echo "$pid" >"$H_RUN/$name.pid"

    sleep 1

    if ! kill -0 "$pid" 2>/dev/null; then
        log "$name failed"

        cat "$H_RUN/$name.log" 2>/dev/null || true

        return 1
    fi

    return 0
}

stop_stack()
{
    mkdir -p "$H_RUN"

    #
    # Consumers first.
    #
    stop_pidfile event
    stop_pidfile state
    stop_pidfile stream

    #
    # Also adopt/clean processes from manual testing or an
    # interrupted older controller run.
    #
    stop_pattern "$LIB/LSAIIOEventBroker.py"
    stop_pattern "$LIB/LSAIIOStateBroker.py"
    stop_pattern "$LIB/LSAIIOStreamBroker.py"

    stop_pattern "/tmp/LSAIIOEventBroker.py"
    stop_pattern "/tmp/LSAIIOStateBroker.py"
    stop_pattern "/tmp/LSAIIOStreamBroker.py"

    #
    # Expose native sysfs before killing the FUSE provider.
    #
    unmount_all "$H_SYS"
    unmount_all "$H_TMP"

    stop_pidfile proxy

    stop_pattern "$LIB/LSAIIOProxy.py"
    stop_pattern "/tmp/LSAIIOProxy.py"

    cleanup_synthetic_dev

    rm -f \
        "$H_RUN/state.sock" \
        "$H_RUN/events.sock"

    log "stopped"
}

start_stack()
{
    mkdir -p "$H_RUN"

    #
    # Idempotent restart.
    #
    stop_stack

    rm -rf "$H_TMP"
    mkdir -p "$H_TMP"

    verify_fuse_device || {
        log "FUSE device is not openable in the chroot"
        return 1
    }

    #
    # With FUSE removed, registry generation sees only real
    # native kernel IIO devices.
    #
    generate_registry || return 1

    build_shim || return 1

    start_process \
        proxy \
        LSAIIOProxy.py \
        "$TMP" || return 1

    #
    # Wait for the FUSE mount before hiding native sysfs with
    # the canonical merged namespace.
    #
    n=0

    while ! mounted "$H_TMP"
    do
        n=$((n + 1))

        if [ "$n" -ge 5 ]; then
            log "proxy FUSE mount did not appear"
            stop_stack
            return 1
        fi

        sleep 1
    done

    log "binding synthetic IIO namespace"

    mount --bind \
        "$H_TMP" \
        "$H_SYS" || {
            stop_stack
            return 1
        }

    start_process \
        stream \
        LSAIIOStreamBroker.py || {
            stop_stack
            return 1
        }

    start_process \
        state \
        LSAIIOStateBroker.py || {
            stop_stack
            return 1
        }

    start_process \
        event \
        LSAIIOEventBroker.py || {
            stop_stack
            return 1
        }

    n=0

    while [ ! -e "$H_RUN/state.sock" ] ||
          [ ! -e "$H_RUN/events.sock" ]
    do
        n=$((n + 1))

        if [ "$n" -ge 5 ]; then
            log "sensor runtime sockets did not appear"
            stop_stack
            return 1
        fi

        sleep 1
    done

    log "started"
}

case "${1:-}" in
    start)
        start_stack
        ;;

    stop)
        stop_stack
        ;;

    restart)
        stop_stack
        start_stack
        ;;

    *)
        echo "usage: $0 {start|stop|restart}" >&2
        exit 2
        ;;
esac
