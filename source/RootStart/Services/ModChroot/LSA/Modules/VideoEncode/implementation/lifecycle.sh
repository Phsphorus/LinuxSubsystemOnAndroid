#!/data/data/com.termux/files/usr/bin/bash

VIDEO_MODULE_BASE="$(CDPATH= cd -- "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VIDEO_CHROOT_DIR="${LSA_CHROOT_DIR:-${CHROOT_DIR:-/data/local/linux}}"
VIDEO_ROOTFS_ASSET="$VIDEO_MODULE_BASE/implementation/rootfs/lsa_ahb_encode"
VIDEO_ROOTFS_BINARY="$VIDEO_CHROOT_DIR/usr/local/lib/lsa/video/lsa_ahb_encode"
VIDEO_ROOTFS_COMMAND="$VIDEO_CHROOT_DIR/usr/local/bin/lsa-h264-encode"
LSA_N6000_VIDEO_PROVIDER="${LSA_N6000_VIDEO_PROVIDER:-${LSA_NONROOT_BASE:-/data/data/com.termux/files/home/NonRootStart}/Providers/Devices/Blackview/N6000/VideoEncode}"
VIDEO_CONTROL="$LSA_N6000_VIDEO_PROVIDER/control.py"
VIDEO_PYTHON="${LSA_TERMUX_PREFIX:-/data/data/com.termux/files/usr}/bin/python"

backend_video_encode_lsa_install_client() {
    [ -x "$VIDEO_ROOTFS_ASSET" ] || { printf 'verified module-owned H.264 consumer asset is missing'; return 1; }
    [ -x "$VIDEO_ROOTFS_COMMAND" ] || { printf 'Linux H.264 command entrypoint has not been injected'; return 1; }
    [ -x "$VIDEO_ROOTFS_BINARY" ] || { printf 'verified Linux H.264 consumer has not been injected'; return 1; }
    printf 'verified Linux H.264 client is installed at /usr/local/bin/lsa-h264-encode'
}

backend_video_encode_lsa_start() {
    backend_video_encode_lsa_install_client || return 1
    [ -x "$VIDEO_PYTHON" ] || { printf 'Termux Python control runtime is missing'; return 1; }
    [ -f "$VIDEO_CONTROL" ] || { printf 'N6000 video control client is missing'; return 1; }
    "$VIDEO_PYTHON" "$VIDEO_CONTROL" start
}

backend_video_encode_lsa_stop() {
    [ -x "$VIDEO_PYTHON" ] || { printf 'Termux Python control runtime is missing'; return 1; }
    [ -f "$VIDEO_CONTROL" ] || { printf 'N6000 video control client is missing'; return 1; }
    "$VIDEO_PYTHON" "$VIDEO_CONTROL" stop
}

backend_video_encode_lsa_status() {
    if [ -S "$VIDEO_CHROOT_DIR/mnt/gpubridge/.lsa-video" ] && [ -x "$VIDEO_ROOTFS_BINARY" ]; then
        printf RUNNING
    else
        printf STOPPED
    fi
}
