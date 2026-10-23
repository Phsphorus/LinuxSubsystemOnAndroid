#!/system/bin/sh
set -eu

TERMUX_PREFIX="/data/data/com.termux/files/usr"
TERMUX_HOME="/data/data/com.termux/files/home"

ROOT_DST="/data/local/RootStart"
NONROOT_DST="$TERMUX_HOME/NonRootStart"
ROOTFS="/data/local/linux"

SELF_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
MODE="${1:-full}"

case "$MODE" in
    full|framework-only)
        ;;
    *)
        echo "usage: $0 [full|framework-only]" >&2
        exit 2
        ;;
esac

TAR="$TERMUX_PREFIX/bin/tar"
PYTHON="$TERMUX_PREFIX/bin/python"
SHA256SUM="$TERMUX_PREFIX/bin/sha256sum"

echo "======================================="
echo " LSA Full-Stack Auto Deployment"
echo "======================================="

[ "$(id -u)" = "0" ] || {
    echo "ERROR: deploy.sh must be run as root."
    exit 1
}

[ -d "$TERMUX_HOME" ] || {
    echo "ERROR: Termux home not found:"
    echo "       $TERMUX_HOME"
    exit 1
}

[ -x "$TAR" ] || {
    echo "ERROR: Termux tar not found:"
    echo "       $TAR"
    exit 1
}

[ -x "$PYTHON" ] || {
    echo "ERROR: Termux Python is required:"
    echo "       $PYTHON"
    exit 1
}

if [ ! -d "$ROOTFS" ]; then
    if [ "$MODE" = framework-only ]; then
        echo "WARNING: Debian-family rootfs missing; installing framework-only payload."
    else
        echo "ERROR: Debian-family rootfs missing:"
        echo "       $ROOTFS"
        echo "       Use framework-only only to collect a capability baseline."
        exit 1
    fi
fi

[ -f "$SELF_DIR/payload/RootStart.tar" ] || {
    echo "ERROR: RootStart payload missing."
    exit 1
}

[ -f "$SELF_DIR/payload/NonRootStart.tar" ] || {
    echo "ERROR: NonRootStart payload missing."
    exit 1
}

###############################################################################
# Verify snapshot integrity.
###############################################################################

if [ -x "$SHA256SUM" ] &&
   [ -f "$SELF_DIR/manifest/PAYLOAD-SHA256SUMS" ]; then

    echo "Verifying payload checksums..."

    (
        cd "$SELF_DIR"
        "$SHA256SUM" -c manifest/PAYLOAD-SHA256SUMS
    ) || {
        echo "ERROR: snapshot checksum verification failed."
        exit 1
    }
fi

###############################################################################
# Refuse to overwrite a running installation.
###############################################################################

if grep -q ' /data/local/linux/' /proc/mounts 2>/dev/null; then
    echo
    echo "ERROR: LSA appears to be running."
    echo "Stop / preflight the existing installation before deployment."
    exit 1
fi

###############################################################################
# Detect target Termux UID/GID.
###############################################################################

TERMUX_UID="$(stat -c %u "$TERMUX_HOME")"
TERMUX_GID="$(stat -c %g "$TERMUX_HOME")"

echo "Termux UID:GID = $TERMUX_UID:$TERMUX_GID"

###############################################################################
# Backup old installation.
###############################################################################

STAMP="$(date +%Y%m%d-%H%M%S)"

if [ -e "$ROOT_DST" ]; then
    BACKUP="/data/local/RootStart.pre-LSA-$STAMP"
    echo "Backing up existing RootStart -> $BACKUP"
    mv "$ROOT_DST" "$BACKUP"
fi

if [ -e "$NONROOT_DST" ]; then
    BACKUP="$TERMUX_HOME/NonRootStart.pre-LSA-$STAMP"
    echo "Backing up existing NonRootStart -> $BACKUP"
    mv "$NONROOT_DST" "$BACKUP"
fi

###############################################################################
# Install COMPLETE project payload.
###############################################################################

echo "Installing RootStart..."
"$TAR" -xf "$SELF_DIR/payload/RootStart.tar" -C /data/local

echo "Installing NonRootStart..."
"$TAR" -xf "$SELF_DIR/payload/NonRootStart.tar" -C "$TERMUX_HOME"

chown -R 0:0 "$ROOT_DST"

# The capability framework is sourced by ModChroot; its command helpers are
# also intentionally executable when the package was created on Windows.
chmod 755 \
    "$ROOT_DST/Services/ModChroot/ModChroot.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Framework/lsectl" \
    "$ROOT_DST/Services/ModChroot/LSA/Framework/quarantine-project-backups.sh" \
    2>/dev/null || true
chown -R "$TERMUX_UID:$TERMUX_GID" "$NONROOT_DST"

###############################################################################
# Fresh HAL state and authentication.
###############################################################################

HAL_STATE="$ROOT_DST/Services/halagent/state"

rm -rf \
    "$HAL_STATE/cam" \
    "$HAL_STATE/rec" \
    "$HAL_STATE/secret"

mkdir -p \
    "$HAL_STATE/cam" \
    "$HAL_STATE/rec" \
    "$HAL_STATE/secret"

chown -R 0:0 "$HAL_STATE"

# The state parent stays traversable for its deliberately shared staging
# children, but is not listable or writable by other local users. The secret
# subtree is private from its first creation; do not briefly publish a token
# and rely on HALAgent to repair it later.
chmod 711 "$HAL_STATE"
chmod 700 "$HAL_STATE/cam" "$HAL_STATE/rec"
chmod 700 "$HAL_STATE/secret"

(
    umask 077
    "$PYTHON" -c 'import secrets; print(secrets.token_hex(32))' \
        > "$HAL_STATE/secret/secret"
)

chown 0:0 "$HAL_STATE/secret/secret"
chmod 600 "$HAL_STATE/secret/secret"

###############################################################################
# Fresh NonRootStart runtime locations.
###############################################################################

rm -rf \
    "$NONROOT_DST/Services/.pids" \
    "$NONROOT_DST/Services/.supervisor"

mkdir -p \
    "$NONROOT_DST/Services/.pids" \
    "$NONROOT_DST/Services/.supervisor"

for svc in \
    HALSensorBus
do
    if [ -d "$NONROOT_DST/Services/$svc" ]; then
        rm -rf \
            "$NONROOT_DST/Services/$svc/run" \
            "$NONROOT_DST/Services/$svc/logs"

        mkdir -p \
            "$NONROOT_DST/Services/$svc/run" \
            "$NONROOT_DST/Services/$svc/logs"
    fi
done

for provider in \
    "$NONROOT_DST/Providers/Android/Audio" \
    "$NONROOT_DST/Providers/Android/GPUBridge"
do
    if [ -d "$provider" ]; then
        rm -rf \
            "$provider/run" \
            "$provider/logs"

        mkdir -p \
            "$provider/run" \
            "$provider/logs"
    fi
done

chown -R "$TERMUX_UID:$TERMUX_GID" "$NONROOT_DST"

###############################################################################
# Fresh RootStart runtime locations.
###############################################################################

for svc in \
    halagent
do
    if [ -d "$ROOT_DST/Services/$svc" ]; then
        rm -rf \
            "$ROOT_DST/Services/$svc/run" \
            "$ROOT_DST/Services/$svc/logs"

        mkdir -p \
            "$ROOT_DST/Services/$svc/run" \
            "$ROOT_DST/Services/$svc/logs"
    fi
done

for provider in \
    "$ROOT_DST/Providers/Android/TermuxX11"
do
    if [ -d "$provider" ]; then
        rm -rf \
            "$provider/run" \
            "$provider/logs"

        mkdir -p \
            "$provider/run" \
            "$provider/logs"
    fi
done

rm -rf "$ROOT_DST/Services/ModChroot/runtime"
mkdir -p "$ROOT_DST/Services/ModChroot/runtime"

chown -R 0:0 "$ROOT_DST"

###############################################################################
# Shared Android storage staging.
###############################################################################

mkdir -p \
    /sdcard/halbridge \
    /sdcard/halbridge/camtmp \
    /sdcard/halbridge/playtmp

###############################################################################
# Install Termux:X11 APK only when absent.
###############################################################################

if [ "$MODE" = framework-only ]; then
    echo "Framework-only mode: skipping Termux:X11 installation."
elif ! pm path com.termux.x11 >/dev/null 2>&1; then
    if [ -f "$SELF_DIR/assets/termux-x11.apk" ]; then
        echo "Installing bundled Termux:X11..."
        pm install -r "$SELF_DIR/assets/termux-x11.apk" || {
            echo "WARNING: automatic Termux:X11 installation failed."
            echo "Install assets/termux-x11.apk manually."
        }
    else
        echo "WARNING: Termux:X11 is not installed and no APK was bundled."
    fi
else
    echo "Termux:X11 already installed."
fi

###############################################################################
# Basic verification of the current full-stack snapshot.
###############################################################################

echo
echo "Running full-stack verification..."

for f in \
    "$ROOT_DST/RST.sh" \
    "$ROOT_DST/Services/ModChroot/ModChroot.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/CoreChroot/implementation/mounts.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/DeviceNamespace/implementation/private-dev.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/DeviceNamespace/implementation/shared-memory.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Storage/implementation/android-shared.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Storage/backends/termux-shared-z.backend" \
    "$ROOT_DST/Services/ModChroot/hooks.d/post-network/64-lsa-sensor-deps.sh" \
    "$ROOT_DST/Services/ModChroot/hooks.d/post-network/65-iio-sensor-proxy.sh" \
    "$ROOT_DST/Services/ModChroot/env.d/50-lsa-sensors.env" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Audio/implementation/lifecycle.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Audio/implementation/inject.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Audio/backends/aaudio-halaudio.backend" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Audio/implementation/rootfs/bin/HALAudio" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Audio/implementation/rootfs/halbridge/HALAudio.py" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Audio/implementation/rootfs/halbridge/HALAudioAutouser.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Sensors/implementation/lifecycle.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Sensors/implementation/inject.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Framework/core.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Framework/architecture.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Framework/lsectl" \
    "$ROOT_DST/Services/ModChroot/LSA/Providers/Android/base.provider" \
    "$ROOT_DST/Services/ModChroot/LSA/Providers/Android/capture.provider" \
    "$ROOT_DST/Services/ModChroot/LSA/Providers/Vendors/MediaTek/venc.provider" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/CoreChroot/backends/core-chroot.backend" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Sensors/backends/fuse-iio.backend" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Camera/backends/android-mjpeg.backend" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Location/backends/android-gpsd.backend" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Display/backends/termux-x11.backend" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Display/implementation/lifecycle.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/DBus/backends/system-bus.backend" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/DBus/implementation/lifecycle.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/FUSE/backends/userspace.backend" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/FUSE/implementation/lifecycle.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/GPU/backends/virgl.backend" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/GPU/implementation/lifecycle.sh" \
    "$ROOT_DST/Providers/Android/TermuxX11/lifecycle.sh" \
    "$ROOT_DST/Providers/Android/TermuxX11/implementation/server.sh" \
    "$ROOT_DST/Providers/Android/TermuxX11/implementation/stop.sh" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Sensors/implementation/src/LSAIIORegistry.py" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Sensors/implementation/src/LSAIIOProxy.py" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Sensors/implementation/src/LSAIIOStreamBroker.py" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Sensors/implementation/src/LSAIIOStateBroker.py" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Sensors/implementation/src/LSAIIOEventBroker.py" \
    "$ROOT_DST/Services/ModChroot/LSA/Modules/Sensors/implementation/src/lsa_iio_eventshim.c" \
    "$NONROOT_DST/NRS.sh" \
    "$NONROOT_DST/Providers/Android/Capture/capture_provider.py" \
    "$NONROOT_DST/Providers/Android/Capture/control.py" \
    "$NONROOT_DST/Providers/Android/Capture/lifecycle.sh" \
    "$NONROOT_DST/Providers/Android/Audio/lifecycle.sh" \
    "$NONROOT_DST/Providers/Android/Audio/implementation/provider.py" \
    "$NONROOT_DST/Providers/Android/Audio/implementation/halaudios/config.py" \
    "$NONROOT_DST/Providers/Android/Audio/implementation/halaudios/server.py" \
    "$NONROOT_DST/Providers/Android/Audio/implementation/halaudios/sink.py" \
    "$NONROOT_DST/Providers/Android/Audio/implementation/halaudios/source.py" \
    "$NONROOT_DST/Providers/Android/GPUBridge/lifecycle.sh" \
    "$NONROOT_DST/Providers/Android/GPUBridge/implementation/server.sh" \
    "$NONROOT_DST/Providers/Android/GPUBridge/implementation/stop.sh" \
    "$NONROOT_DST/Services/HALSensorBus/HALSensorBus.py" \
    "$NONROOT_DST/Services/HALSensorBus/start.sh" \
    "$NONROOT_DST/Services/HALSensorBus/stop.sh"
do
    if [ ! -f "$f" ]; then
        echo "ERROR: expected snapshot file missing:"
        echo "       $f"
        exit 1
    fi
done

"$TERMUX_PREFIX/bin/bash" -n "$ROOT_DST/RST.sh"
"$TERMUX_PREFIX/bin/bash" -n "$ROOT_DST/Services/ModChroot/ModChroot.sh"
"$TERMUX_PREFIX/bin/bash" -n "$ROOT_DST/Services/ModChroot/LSA/Modules/CoreChroot/implementation/mounts.sh"
"$TERMUX_PREFIX/bin/bash" -n "$ROOT_DST/Services/ModChroot/LSA/Modules/DeviceNamespace/implementation/private-dev.sh"
"$TERMUX_PREFIX/bin/bash" -n "$ROOT_DST/Services/ModChroot/LSA/Modules/DeviceNamespace/implementation/shared-memory.sh"
"$TERMUX_PREFIX/bin/bash" -n "$ROOT_DST/Services/ModChroot/LSA/Modules/Storage/implementation/android-shared.sh"
"$TERMUX_PREFIX/bin/bash" -n "$ROOT_DST/Services/ModChroot/LSA/Modules/Audio/implementation/lifecycle.sh"
"$TERMUX_PREFIX/bin/bash" -n "$ROOT_DST/Services/ModChroot/LSA/Modules/Sensors/implementation/lifecycle.sh"
"$TERMUX_PREFIX/bin/bash" -n "$NONROOT_DST/NRS.sh"
"$TERMUX_PREFIX/bin/bash" -n "$NONROOT_DST/Providers/Android/Capture/lifecycle.sh"
"$TERMUX_PREFIX/bin/bash" -n "$NONROOT_DST/Providers/Android/Audio/lifecycle.sh"
"$TERMUX_PREFIX/bin/bash" -n "$NONROOT_DST/Providers/Android/GPUBridge/lifecycle.sh"
"$TERMUX_PREFIX/bin/bash" -n "$NONROOT_DST/Providers/Android/GPUBridge/implementation/server.sh"
"$TERMUX_PREFIX/bin/bash" -n "$NONROOT_DST/Providers/Android/GPUBridge/implementation/stop.sh"
"$TERMUX_PREFIX/bin/bash" -n "$ROOT_DST/Providers/Android/TermuxX11/lifecycle.sh"
"$TERMUX_PREFIX/bin/bash" -n "$ROOT_DST/Providers/Android/TermuxX11/implementation/server.sh"
"$TERMUX_PREFIX/bin/bash" -n "$ROOT_DST/Providers/Android/TermuxX11/implementation/stop.sh"

for f in \
    "$ROOT_DST/Services/ModChroot/LSA/Framework/"*.sh \
    "$ROOT_DST/Services/ModChroot/LSA/Framework/lsectl"
do
    [ -f "$f" ] || continue
    "$TERMUX_PREFIX/bin/bash" -n "$f"
done

find "$ROOT_DST/Services/ModChroot/LSA/Providers" \
     "$ROOT_DST/Services/ModChroot/LSA/Modules" \
     -type f \( -name '*.provider' -o -name '*.backend' \) \
     -exec "$TERMUX_PREFIX/bin/bash" -n {} \;

echo
echo "======================================="
echo " LSA deployment complete"
echo "======================================="
echo
echo "HALBridge secret:"
echo "  $HAL_STATE/secret/secret"
echo
if [ "$MODE" = framework-only ]; then
    echo "Framework-only mode does not start LSA."
    echo "Install a compatible Linux rootfs at $ROOTFS before normal startup."
    echo "The installed framework can still produce a preflight capability report."
else
    echo "Start NonRootStart AS TERMUX USER:"
    echo "  ~/NonRootStart/NRS.sh"
    echo
    echo "Then start RootStart AS ROOT:"
    echo "  /data/local/RootStart/RST.sh"
fi
echo
