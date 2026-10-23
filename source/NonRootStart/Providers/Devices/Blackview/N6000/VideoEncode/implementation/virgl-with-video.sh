#!/data/data/com.termux/files/usr/bin/bash
set -eu

# This launcher is invoked only by the generic GPUBridge provider while it is
# in the N6000 video mode. It remains a Termux-user process and leaves the
# ordinary VirGL socket intact; the preload adds the separate video-tap socket.
BASE="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
RUN="$BASE/state/run"
LOG_DIR="$BASE/state/logs"
VIDEO_LIB="$RUN/libLSAGPUTap.so"
VIDEO_SOCKET="${GPU_BRIDGE_VIDEO_SOCKET:-$RUN/.lsa-video}"

[ -f "$VIDEO_LIB" ] || {
  echo "N6000 VideoEncode: generated GPU tap library is missing: $VIDEO_LIB" >&2
  exit 1
}

mkdir -p "$RUN" "$LOG_DIR"
export LSA_GPU_TAP_SOCKET="$VIDEO_SOCKET"
export LSA_GPU_TAP_LOG="$LOG_DIR/lsa-video.log"
if [ -n "${LD_PRELOAD:-}" ]; then
  export LD_PRELOAD="$VIDEO_LIB:$LD_PRELOAD"
else
  export LD_PRELOAD="$VIDEO_LIB"
fi

exec "$PREFIX/bin/virgl_test_server" "$@"
