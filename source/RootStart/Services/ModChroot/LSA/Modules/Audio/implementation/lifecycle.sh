#!/data/data/com.termux/files/usr/bin/bash
set -u

IMPLEMENTATION_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
MODCHROOT_BASE="$(CDPATH= cd -- "$IMPLEMENTATION_DIR/../../../.." && pwd)"

CHROOT_DIR="${CHROOT_DIR:-/data/local/linux}"
CHROOT_PATH="${CHROOT_PATH:-/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin}"
RUNTIME_DIR="${RUNTIME_DIR:-$MODCHROOT_BASE/runtime}"
PID_FILE="${HALAUDIO_PID_FILE:-$RUNTIME_DIR/halaudio.pid}"
AUTOSTART="${HALAUDIO_AUTOSTART:-/usr/local/lib/halbridge/HALAudioAutouser.sh}"
SCRIPT="${HALAUDIO_SCRIPT:-/usr/local/lib/halbridge/HALAudio.py}"

log(){ printf 'ModChroot: audio: %s\n' "$*"; }

cleanup_chroot_audio(){
    chroot "$CHROOT_DIR" /usr/bin/env -i PATH="$CHROOT_PATH" /bin/sh -lc '
      pkill -f "HALAudio.py" 2>/dev/null || true
      rm -f /tmp/halaudio*.sock 2>/dev/null || true
    ' >/dev/null 2>&1 || true
}

start(){
    local backend="${LSA_AUDIO_BACKEND:-aaudio}"
    local aec_backend="${LSA_AUDIO_AEC_BACKEND:-auto}"
    [ -x "$CHROOT_DIR/bin/sh" ] || { log "ERROR chroot shell missing"; return 1; }
    mkdir -p "$RUNTIME_DIR"
    cleanup_chroot_audio

    if chroot "$CHROOT_DIR" /usr/bin/env -i PATH="$CHROOT_PATH" /bin/sh -lc "[ -x '$AUTOSTART' ]"; then
        log "starting Linux Pulse/ALSA consumer through $AUTOSTART"
        chroot "$CHROOT_DIR" /usr/bin/env -i PATH="$CHROOT_PATH" LSA_AUDIO_BACKEND="$backend" LSA_AEC_BACKEND="$aec_backend" /bin/sh -lc "$AUTOSTART" >/dev/null 2>&1 &
        echo "$!" >"$PID_FILE"
        return 0
    fi

    log "autostart missing; using portable Linux consumer fallback"
    chroot "$CHROOT_DIR" /usr/bin/env -i PATH="$CHROOT_PATH" LSA_AUDIO_BACKEND="$backend" LSA_AEC_BACKEND="$aec_backend" /bin/sh -lc "python3 '$SCRIPT' >/tmp/HALAudio.log 2>&1 &" >/dev/null 2>&1 &
    echo "$!" >"$PID_FILE"
}

stop(){
    if [ -f "$PID_FILE" ]; then
        local pid
        pid="$(cat "$PID_FILE" 2>/dev/null || true)"
        if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
            log "stopping launcher pid=$pid"
            kill -TERM "$pid" 2>/dev/null || true
            sleep 1
            kill -KILL "$pid" 2>/dev/null || true
        fi
    fi
    rm -f "$PID_FILE"
    [ -x "$CHROOT_DIR/bin/sh" ] && cleanup_chroot_audio
}

status(){
    if [ -S "$CHROOT_DIR/tmp/pa-run/pulse/native" ]; then
        printf 'RUNNING\n'
    else
        printf 'STOPPED\n'
    fi
}

case "${1:-}" in
    start) start ;;
    stop) stop ;;
    restart) stop; start ;;
    status) status ;;
    *) echo "usage: $0 {start|stop|restart|status}" >&2; exit 2 ;;
esac
