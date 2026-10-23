#!/data/data/com.termux/files/usr/bin/bash
set -u

BASE="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
RUN="$BASE/run"
PID_FILE="$RUN/virgl.pid"
SOCKET="$RUN/.virgl_test"
VIDEO_SOCKET="$RUN/.lsa-video"
MODE_FILE="$RUN/mode"

if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if echo "$PID" | grep -Eq '^[0-9]+$' && kill -0 "$PID" 2>/dev/null; then
        echo "Android GPUBridge: stopping VirGL pid=$PID"
        kill -TERM "$PID" 2>/dev/null || true
        sleep 1
        kill -0 "$PID" 2>/dev/null && kill -KILL "$PID" 2>/dev/null || true
    fi
fi

pkill -f virgl_test_server 2>/dev/null || true
rm -f "$PID_FILE" "$SOCKET" "$VIDEO_SOCKET" "$MODE_FILE"
echo "Android GPUBridge: stopped"
