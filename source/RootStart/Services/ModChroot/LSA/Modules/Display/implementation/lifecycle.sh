#!/data/data/com.termux/files/usr/bin/bash

# The generic module exposes the normal Linux X11 endpoint. Android app_process
# remains lifecycle-owned by the RootStart TermuxX11 provider.
DISPLAY_MODULE_VALUE="${TERMUX_X11_DISPLAY:-:0}"
DISPLAY_MODULE_NUMBER="${DISPLAY_MODULE_VALUE#:}"
DISPLAY_MODULE_NUMBER="${DISPLAY_MODULE_NUMBER%%.*}"
DISPLAY_MODULE_SOCKET="${LSA_CHROOT_DIR:-${CHROOT_DIR:-/data/local/linux}}/tmp/.X11-unix/X${DISPLAY_MODULE_NUMBER}"

backend_display_termux_x11_start() {
    if [ ! -S "$DISPLAY_MODULE_SOCKET" ]; then
        printf 'Linux X11 socket is not available: %s' "$DISPLAY_MODULE_SOCKET"
        return 1
    fi
    printf 'generic Linux X11 consumer activated on %s' "$DISPLAY_MODULE_SOCKET"
}

backend_display_termux_x11_stop() {
    printf 'generic Linux X11 consumer released; Android provider remains RootStart-owned'
}

backend_display_termux_x11_status() {
    if [ -S "$DISPLAY_MODULE_SOCKET" ]; then printf RUNNING; else printf STOPPED; fi
}
