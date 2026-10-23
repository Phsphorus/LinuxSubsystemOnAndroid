#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

BASE="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
RUN="$BASE/run"
LOG_DIR="$BASE/logs"
LOG="$LOG_DIR/gpubridge.log"
SOCKET="$RUN/.virgl_test"
PID_FILE="$RUN/virgl.pid"
MODE_FILE="$RUN/mode"
MODE="${GPU_BRIDGE_MODE:-generic}"
VIDEO_LAUNCHER="${GPU_BRIDGE_VIDEO_LAUNCHER:-}"
VIDEO_SOCKET="${GPU_BRIDGE_VIDEO_SOCKET:-$RUN/.lsa-video}"

ANGLE="$PREFIX/opt/angle-android/vulkan"

normalize_architecture() {
    local raw
    raw="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')"
    case "$raw" in
        aarch64|arm64|arm64-v8a) printf arm64 ;;
        armv8l|armv7l|armv7|armv7a|armeabi-v7a|arm) printf armv7 ;;
        i386|i486|i586|i686|x86) printf x86 ;;
        x86_64|amd64) printf x86_64 ;;
        *) printf unknown ;;
    esac
}

select_vulkan_icd() {
    local raw normalized directory suffix suffixes candidate count=0 selected=""
    raw="$("$PREFIX/bin/dpkg" --print-architecture 2>/dev/null || uname -m 2>/dev/null || printf unknown)"
    normalized="$(normalize_architecture "$raw")"
    directory="$PREFIX/share/vulkan/icd.d"
    case "$normalized" in
        arm64) suffixes='aarch64 arm64 arm64-v8a' ;;
        armv7) suffixes='armv7a armv7 armeabi-v7a' ;;
        x86) suffixes='x86 i686' ;;
        x86_64) suffixes='x86_64 amd64' ;;
        *) suffixes='' ;;
    esac
    for suffix in $suffixes; do
        candidate="$directory/wrapper_icd.$suffix.json"
        [ -f "$candidate" ] && { printf '%s' "$candidate"; return 0; }
    done
    for candidate in "$directory"/wrapper_icd.*.json; do
        [ -f "$candidate" ] || continue
        selected="$candidate"
        count=$((count + 1))
    done
    [ "$count" = 1 ] || return 1
    printf '%s' "$selected"
}

ICD="$(select_vulkan_icd 2>/dev/null || true)"

mkdir -p "$RUN" "$LOG_DIR"
chmod 755 "$RUN"
chmod 700 "$LOG_DIR"

exec >>"$LOG" 2>&1

echo
echo "=== Android GPUBridge start $(date) ==="
case "$MODE" in
  generic|video) ;;
  *) echo "ERROR: unsupported GPU bridge mode: $MODE"; exit 2 ;;
esac
if [ "$MODE" = video ] && [ ! -x "$VIDEO_LAUNCHER" ]; then
    echo "ERROR: device video launcher is unavailable: $VIDEO_LAUNCHER"
    exit 2
fi
if [ -z "$ICD" ]; then
    echo "ERROR: no Vulkan wrapper ICD matches the detected Termux architecture"
    exit 2
fi

if [ -f "$PID_FILE" ]; then
    OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if echo "$OLD_PID" | grep -Eq '^[0-9]+$' && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping old VirGL pid=$OLD_PID"
        kill "$OLD_PID" 2>/dev/null || true
        sleep 1
        if kill -0 "$OLD_PID" 2>/dev/null; then
            kill -9 "$OLD_PID" 2>/dev/null || true
        fi
    fi
fi

# Preserve the proven server cleanup behavior while keeping it inside this
# provider.  The single Android GPUBridge provider owns virgl_test_server.
pkill -f virgl_test_server 2>/dev/null || true
sleep 1
rm -f "$SOCKET" "$VIDEO_SOCKET" "$PID_FILE" "$MODE_FILE"

export VK_ICD_FILENAMES="$ICD"
echo "--- Vulkan GPU ---"
VK_ICD_FILENAMES="$ICD" vulkaninfo --summary 2>/dev/null | \
  grep -E 'vendorID|deviceName|driverID|driverName' || true

echo "--- Android GPUBridge config ---"
echo "ANGLE:  $ANGLE"
echo "ICD:    $ICD"
echo "Socket: $SOCKET"
echo "Mode:   $MODE"
echo "--- Starting VirGL ---"

if [ "$MODE" = video ]; then
    GPU_BRIDGE_VIDEO_SOCKET="$VIDEO_SOCKET" \
    LD_LIBRARY_PATH="$ANGLE" \
    "$VIDEO_LAUNCHER" \
        --use-egl-surfaceless \
        --use-gles \
        --socket-path "$SOCKET" &
else
    LD_LIBRARY_PATH="$ANGLE" \
    virgl_test_server \
        --use-egl-surfaceless \
        --use-gles \
        --socket-path "$SOCKET" &
fi

PID=$!
echo "$PID" > "$PID_FILE"

SOCKET_READY=0
for _ in $(seq 1 50); do
    if [ -S "$SOCKET" ] && { [ "$MODE" != video ] || [ -S "$VIDEO_SOCKET" ]; }; then
        SOCKET_READY=1
        break
    fi
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "ERROR: virgl_test_server exited before socket appeared"
        exit 1
    fi
    sleep 0.1
done

if [ "$SOCKET_READY" -ne 1 ]; then
    echo "ERROR: VirGL endpoint was not created for mode=$MODE"
    kill "$PID" 2>/dev/null || true
    rm -f "$SOCKET" "$VIDEO_SOCKET" "$PID_FILE" "$MODE_FILE"
    exit 1
fi

chmod 666 "$SOCKET"
if [ "$MODE" = video ]; then
    chmod 666 "$VIDEO_SOCKET"
fi
chmod 644 "$PID_FILE"
printf '%s\n' "$MODE" > "$MODE_FILE"
chmod 644 "$MODE_FILE"

echo "--- process ---"
pgrep -af virgl_test_server || true
echo "--- socket ---"
ls -la "$RUN"

if kill -0 "$PID" 2>/dev/null; then
    echo "Android GPUBridge running pid=$PID"
else
    echo "ERROR: Android GPUBridge process is not alive"
    exit 1
fi

echo "=== Android GPUBridge ready ==="
