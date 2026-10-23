#!/bin/sh
set -eu
HAL_DIR="/usr/local/lib/halbridge"
HAL_SCRIPT="$HAL_DIR/HALAudio.py"
PA_HOME="/tmp/pa-home"
PA_RUN="/tmp/pa-run"
CTRL_SOCK_GLOB="/tmp/halaudio*.sock"
AUDIO_TOKEN_SOURCE="/mnt/halbridge/secret/audio-secret"
AUDIO_TOKEN_FILE="$PA_HOME/.lsa-halaudio-token"

AUTO_USER="$(awk -F: '
  $3 >= 1000 && $3 < 60000 &&
  $1 != "nobody" &&
  $1 !~ /^aid_/ &&
  $7 ~ /(bash|sh)$/ &&
  $7 !~ /(nologin|false)$/ { print $1; exit }
' /etc/passwd)"
[ "${AUTO_USER:-}" = "root" ] && AUTO_USER=""

if [ -z "${AUTO_USER:-}" ]; then
  if ! id HALAudio >/dev/null 2>&1; then
    echo "Creating HALAudio user"
    useradd -m -s /bin/bash HALAudio
  fi
  AUTO_USER="HALAudio"
fi

HOME_DIR="$(awk -F: -v u="$AUTO_USER" '$1==u {print $6}' /etc/passwd)"
[ -n "$HOME_DIR" ] || HOME_DIR="/home/$AUTO_USER"
[ -d "$HOME_DIR" ] || HOME_DIR="/tmp"
LOGFILE="$HOME_DIR/HALAudio.log"

mkdir -p "$PA_HOME/.config/pulse" "$PA_RUN"

# Kill stale HALAudio-owned PulseAudio daemons from previous runs.
AUTO_UID="$(id -u "$AUTO_USER")"
for proc in /proc/[0-9]*; do
  [ -r "$proc/status" ] || continue
  [ -r "$proc/environ" ] || continue

  PROC_UID="$(awk '/^Uid:/ {print $2; exit}' "$proc/status" 2>/dev/null || true)"
  [ "$PROC_UID" = "$AUTO_UID" ] || continue

  if tr '\0' '\n' < "$proc/environ" 2>/dev/null |       grep -Fxq "XDG_RUNTIME_DIR=$PA_RUN"; then
    COMM="$(cat "$proc/comm" 2>/dev/null || true)"
    if [ "$COMM" = "pulseaudio" ]; then
      kill -TERM "${proc##*/}" 2>/dev/null || true
    fi
  fi
done

sleep 1
rm -rf "$PA_RUN/pulse"
chown -R "$AUTO_USER:$AUTO_USER" "$PA_HOME" "$PA_RUN"
chmod 700 "$PA_HOME" "$PA_RUN"

# HALAudio runs without root privileges.  Give it a separate 0600 token that
# only grants microphone and Android-sink controls; the HAL master secret
# stays root-only under /mnt/halbridge/secret.
if [ ! -r "$AUDIO_TOKEN_SOURCE" ]; then
  echo "HALAudio audio-control credential is unavailable: $AUDIO_TOKEN_SOURCE" >&2
  exit 1
fi
cp -f "$AUDIO_TOKEN_SOURCE" "$AUDIO_TOKEN_FILE"
chown "$AUTO_USER:$AUTO_USER" "$AUDIO_TOKEN_FILE"
chmod 600 "$AUDIO_TOKEN_FILE"

pkill -u "$AUTO_USER" -f "$HAL_SCRIPT" 2>/dev/null || true
rm -f $CTRL_SOCK_GLOB 2>/dev/null || true

echo "Starting HALAudio as user $AUTO_USER, log $LOGFILE"
echo "Using PA dirs: PA_HOME=$PA_HOME PA_RUN=$PA_RUN"

# Preserve baseline detached startup semantics. ModChroot owns cleanup separately.
su - "$AUTO_USER" -c "
  export HOME='$PA_HOME'
  export XDG_RUNTIME_DIR='$PA_RUN'
  export XDG_CONFIG_HOME='$PA_HOME/.config'
  export LSA_HAL_AUDIO_TOKEN_FILE='$AUDIO_TOKEN_FILE'
  export LSA_AUDIO_BACKEND='${LSA_AUDIO_BACKEND:-aaudio}'
  export LSA_AEC_BACKEND='${LSA_AEC_BACKEND:-auto}'
  cd '$HAL_DIR' || cd '$PA_HOME' || cd /
  python3 '$HAL_SCRIPT' >> '$LOGFILE' 2>&1 &
"
