# RootStart start-chroot configuration.
# This file belongs to Android infrastructure, not to the Debian rootfs.

CHROOT_DIR="/data/local/linux"

CHROOT_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

# Lifecycle/control files live outside the disposable rootfs.
START_CHROOT_BASE="/data/local/RootStart/Services/ModChroot"
RUNTIME_DIR="$START_CHROOT_BASE/runtime"
LOG_FILE="$RUNTIME_DIR/start-chroot.log"
PID_FILE="$RUNTIME_DIR/chroot.pid"
WATCH_PID_FILE="$RUNTIME_DIR/switch-watch.pid"
HALAUDIO_PID_FILE="$RUNTIME_DIR/halaudio.pid"
TEARDOWN_LOCK="$RUNTIME_DIR/.teardown.lock"

# Deliberately unsafe developer compatibility for rooted phones whose Linux
# rootfs inherits Android's nosuid mount.  This is never a generic privilege
# boundary: the sudo wrapper demands an exact interactive acknowledgement and
# the RootStart daemon exposes suid only for that one leased command.
UNSAFE_SUDO_ENABLE=1
UNSAFE_SUDO_USER="myuser"
UNSAFE_SUDO_PID_FILE="$RUNTIME_DIR/unsafe-sudo.pid"
UNSAFE_SUDO_LOG_FILE="$RUNTIME_DIR/unsafe-sudo.log"
UNSAFE_SUDO_STAGE_ROOT="$RUNTIME_DIR/unsafe-sudo-stage"
UNSAFE_SUDO_SOCKET="$CHROOT_DIR/run/lsa/unsafe-sudo.sock"

# Keep the familiar switch inside the rootfs for now.
SWITCH_FILE="$CHROOT_DIR/SWITCH"

# Android/Termux resources.
HALBRIDGE="/data/local/RootStart/Services/halagent/state"
SECRET_DIR="$HALBRIDGE/secret"

GPUBRIDGE_RUN="/data/data/com.termux/files/home/NonRootStart/Providers/Android/GPUBridge/run"

# DNS is provided by the RootStart DNS service on standard loopback port 53.
# ModChroot points the disposable Linux rootfs at that resolver.
DNS_LOCAL_IP="127.0.0.1"

# Termux:X11.
TERMUX_X11_ENABLE=1
TERMUX_X11_DISPLAY=":0"
CHROOT_DISPLAY=":0.0"

# Desktop autostart.
# Termux:X11 is LSA's real phone display.  Launch the experimental LSA shell
# there on :0; LXDE remains available as the independent VNC workspace on :1.
# Set to "none" to boot only the shell.
DESKTOP_AUTOSTART=1
DESKTOP_COMMAND="/usr/local/bin/lsa-session"

# HALAudio inside the chroot.
HALAUDIO_ENABLE=1
HALAUDIO_AUTOSTART="/usr/local/lib/halbridge/HALAudioAutouser.sh"
HALAUDIO_SCRIPT="/usr/local/lib/halbridge/HALAudio.py"

# Microphone echo cancellation policy.  `auto` uses Debian PulseAudio's
# WebRTC module until an Android AudioRecord/AcousticEchoCanceler provider is
# available.  Other accepted values: pulseaudio, android, off.
LSA_AUDIO_AEC_BACKEND="auto"

# Removable storage ownership. Android-mounted public volumes are exported to
# Debian from vold's visible path at /media/android. Android-rejected NTFS
# volumes are mounted only in Debian at /media/debian through ntfs-3g.
LSA_STORAGE_VOLD_ENABLE=1
LSA_STORAGE_WATCH_SECONDS=3
LSA_STORAGE_DEBIAN_USER="${UNSAFE_SUDO_USER:-myuser}"

# Canonical Linux-side PulseAudio endpoint.
# This is the single source of truth used by both the live chroot environment
# and persistent Debian-family rootfs integration.
HALAUDIO_PULSE_SERVER="unix:/tmp/pa-run/pulse/native"

# Debian-family rootfs provisioning.
#
# Runtime policy:
#   - configuration injection is always local/offline
#   - missing distro packages prefer the rootfs's own APT repositories
#   - online provisioning requires working DNS + google.com:443 reachability
#   - if offline, use only an exact matching shipped compatibility pack
#   - network/package failure must never prevent LSA boot
DEBIAN_FAMILY_PROVISION_ENABLE=1
DEBIAN_FAMILY_PROBE_HOST="google.com"
DEBIAN_FAMILY_REQUIRED_PACKAGES="libasound2-plugins"
DEBIAN_FAMILY_APT_TIMEOUT="12"
DEBIAN_FAMILY_OFFLINE_ROOT="$START_CHROOT_BASE/offline/debian-family"

# VNC is the independent LXDE workspace.  It runs at phone resolution so
# desktop applications can still be inspected without taking over :0.
VNC_ENABLE=1
VNC_DISPLAY=":1"
# Keep the VNC design surface at the physical Termux:X11 phone resolution.
# This lets the custom shell be tuned in portrait without changing :0.
VNC_GEOMETRY="536x1068"
VNC_LOCALHOST="no"
