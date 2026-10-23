#!/data/data/com.termux/files/usr/bin/bash

# The generic GPU module consumes a Linux-visible VirGL socket.  The Android
# provider itself is started and stopped by NonRootStart in the Termux UID.
GPU_MODULE_ROOT="${LSA_CHROOT_DIR:-${CHROOT_DIR:-/data/local/linux}}"
GPU_MODULE_SOCKET="$GPU_MODULE_ROOT/mnt/gpubridge/.virgl_test"
GPU_MODULE_CLIENT_POLICY="$GPU_MODULE_ROOT/usr/local/lib/lsa/gpu/lsa-gpu-env.sh"

backend_gpu_virgl_start() {
    if [ ! -S "$GPU_MODULE_SOCKET" ]; then
        printf 'Linux VirGL socket is not mounted: %s' "$GPU_MODULE_SOCKET"
        return 1
    fi
    if [ ! -r "$GPU_MODULE_CLIENT_POLICY" ]; then
        printf 'Linux VirGL client policy is unavailable: %s' "$GPU_MODULE_CLIENT_POLICY"
        return 1
    fi
    printf 'generic Linux VirGL consumer activated on %s with client policy %s' \
        "$GPU_MODULE_SOCKET" "$GPU_MODULE_CLIENT_POLICY"
}

backend_gpu_virgl_stop() {
    # Do not cross the UID boundary and terminate the Android provider here.
    # NonRootStart owns that provider lifecycle; Linux clients simply release
    # the normal VTEST socket endpoint.
    printf 'generic Linux VirGL consumer released; Android provider remains NonRootStart-owned'
}

backend_gpu_virgl_status() {
    if [ -S "$GPU_MODULE_SOCKET" ] && [ -r "$GPU_MODULE_CLIENT_POLICY" ]; then
        printf RUNNING
    else
        printf STOPPED
    fi
}
