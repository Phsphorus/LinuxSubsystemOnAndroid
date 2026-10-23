# Debian-family rootfs provisioning.
#
# This library is sourced by ModChroot.sh and therefore runs under Termux bash.

DF_ID="unknown"
DF_ID_LIKE=""
DF_VERSION_ID=""
DF_CODENAME="unknown"
DF_UBUNTU_CODENAME=""
DF_ARCH="unknown"
# Set by debian_family_provision for later post-network hooks.  Optional
# installers must not retry network access after the shared preflight already
# established that the rootfs is offline.
DEBIAN_FAMILY_NETWORK_STATE="UNKNOWN"

debian_family_detect() {
  [ "${DEBIAN_FAMILY_PROVISION_ENABLE:-1}" = "1" ] || return 1

  [ -x "$CHROOT_DIR/usr/bin/dpkg" ] || return 1
  [ -x "$CHROOT_DIR/usr/bin/dpkg-query" ] || return 1
  [ -x "$CHROOT_DIR/usr/bin/apt-get" ] || return 1
  [ -x "$CHROOT_DIR/bin/sh" ] || return 1

  return 0
}

debian_family_safe_component() {
  local value="${1:-unknown}"

  case "$value" in
    ""|*[!A-Za-z0-9._-]*)
      printf '%s\n' "unknown"
      ;;
    *)
      printf '%s\n' "$value"
      ;;
  esac
}

debian_family_read_identity() {
  local ID=""
  local ID_LIKE=""
  local VERSION_ID=""
  local VERSION_CODENAME=""
  local UBUNTU_CODENAME=""

  if [ -r "$CHROOT_DIR/etc/os-release" ]; then
    # shellcheck source=/dev/null
    source "$CHROOT_DIR/etc/os-release"
  fi

  DF_ID="$(debian_family_safe_component "${ID:-unknown}")"
  DF_ID_LIKE="${ID_LIKE:-}"
  DF_VERSION_ID="$(debian_family_safe_component "${VERSION_ID:-unknown}")"
  DF_CODENAME="$(debian_family_safe_component "${VERSION_CODENAME:-unknown}")"
  DF_UBUNTU_CODENAME="$(debian_family_safe_component "${UBUNTU_CODENAME:-}")"

  [ "$DF_UBUNTU_CODENAME" = "unknown" ] &&
    DF_UBUNTU_CODENAME=""

  DF_ARCH="$(
    chroot "$CHROOT_DIR" /usr/bin/dpkg --print-architecture 2>/dev/null ||
      printf '%s\n' unknown
  )"

  DF_ARCH="$(debian_family_safe_component "$DF_ARCH")"

  log "provision: distro id=$DF_ID id_like=${DF_ID_LIKE:-none} version=$DF_VERSION_ID codename=$DF_CODENAME arch=$DF_ARCH"

  if [ -n "$DF_UBUNTU_CODENAME" ]; then
    log "provision: ubuntu base codename=$DF_UBUNTU_CODENAME"
  fi
}

debian_family_package_present() {
  local package="$1"

  chroot "$CHROOT_DIR" \
    /usr/bin/dpkg-query \
      -W \
      -f='${Status}' \
      "$package" \
      2>/dev/null |
    grep -q '^install ok installed$'
}

###############################################################################
# Root-owned setuid package integrity
###############################################################################

debian_family_repair_setuid_ownership() {
  # Android app-UID extraction or copying can leave a small group of Debian
  # setuid tools owned by the Termux app.  They remain unusable on the normal
  # nosuid rootfs, then become actively wrong in a deliberately leased suid
  # namespace: they elevate to the app UID instead of Debian root.
  #
  # Limit repair to package-owned paths whose Debian owner and normal mode are
  # known.  Do not scan-and-chown arbitrary setuid files, and do not alter a
  # root-owned file merely because an administrator intentionally changed its
  # mode.
  local entry path package target uid owner_line
  local manifest='
/usr/bin/chfn passwd
/usr/bin/chsh passwd
/usr/bin/gpasswd passwd
/usr/bin/newgrp login
/usr/bin/passwd passwd
/usr/bin/su util-linux
/usr/bin/mount mount
/usr/bin/umount mount
/usr/bin/fusermount3 fuse3
/usr/bin/ntfs-3g ntfs-3g
'

  while read -r path package; do
    [ -n "${path:-}" ] || continue
    target="$CHROOT_DIR$path"
    [ -f "$target" ] || continue
    [ -u "$target" ] || continue

    uid="$(stat -c '%u' "$target" 2>/dev/null || true)"
    [ "$uid" = 0 ] && continue

    owner_line="$(chroot "$CHROOT_DIR" /usr/bin/dpkg-query -S "$path" 2>/dev/null || true)"
    case "$owner_line" in
      "$package:"*) ;;
      *)
        log "WARNING: rootfs setuid ownership left unchanged path=$path uid=${uid:-unknown} package=${owner_line:-unowned}"
        continue
        ;;
    esac

    if chown 0:0 "$target" && chmod 4755 "$target"; then
      log "rootfs: repaired package setuid ownership path=$path package=$package old_uid=$uid"
    else
      log "WARNING: rootfs could not repair package setuid ownership path=$path"
    fi
  done <<EOF
$manifest
EOF
}

###############################################################################
# Persistent rootfs environment
###############################################################################

debian_family_write_pulse_environment() {
  local envfile="$CHROOT_DIR/etc/environment"
  local pulse="${HALAUDIO_PULSE_SERVER:-unix:/tmp/pa-run/pulse/native}"

  mkdir -p "$CHROOT_DIR/etc"
  touch "$envfile"

  sed -i \
    '/^[[:space:]]*PULSE_SERVER[[:space:]]*=/d' \
    "$envfile"

  printf '%s\n' "PULSE_SERVER=$pulse" >> "$envfile"

  log "audio: /etc/environment PULSE_SERVER=$pulse"
}

###############################################################################
# Managed ALSA configuration
###############################################################################

debian_family_remove_asound_block() {
  local file="$CHROOT_DIR/etc/asound.conf"

  [ -f "$file" ] || return 0

  sed -i \
    '/^# BEGIN LSA MODCHROOT AUDIO$/,/^# END LSA MODCHROOT AUDIO$/d' \
    "$file"
}

debian_family_write_asound_block() {
  local file="$CHROOT_DIR/etc/asound.conf"

  mkdir -p "$CHROOT_DIR/etc"
  touch "$file"

  debian_family_remove_asound_block

  cat >> "$file" <<'ASOUNDEOF'

# BEGIN LSA MODCHROOT AUDIO
# Managed by LSA ModChroot.
#
# Applications using ALSA converge on the same PulseAudio boundary used by
# native Pulse clients. Do not edit inside this managed block.
pcm.!default {
    type pulse
}

ctl.!default {
    type pulse
}
# END LSA MODCHROOT AUDIO
ASOUNDEOF

  log "audio: installed managed ALSA -> Pulse default"
}

###############################################################################
# Network preflight
#
# Intentionally tests:
#   1. rootfs DNS resolution
#   2. TCP reachability to google.com:443
#
# It does not require curl/wget/CA certificates.
###############################################################################

debian_family_network_ready() {
  local host="${DEBIAN_FAMILY_PROBE_HOST:-google.com}"

  [ -x "$CHROOT_DIR/bin/bash" ] || return 1

  chroot "$CHROOT_DIR" \
    /usr/bin/env -i \
      HOME=/root \
      PATH="$CHROOT_PATH" \
      LSA_PROBE_HOST="$host" \
      /bin/bash -c '
        command -v getent >/dev/null 2>&1 || exit 10
        command -v timeout >/dev/null 2>&1 || exit 11

        getent ahosts "$LSA_PROBE_HOST" >/dev/null 2>&1 || exit 12

        timeout 6 /bin/bash -c \
          "exec 3<>/dev/tcp/$LSA_PROBE_HOST/443" \
          >/dev/null 2>&1 || exit 13

        exit 0
      '
}

###############################################################################
# Online provisioning
###############################################################################

debian_family_apt_install_required() {
  local packages="${DEBIAN_FAMILY_REQUIRED_PACKAGES:-libasound2-plugins}"
  local timeout="${DEBIAN_FAMILY_APT_TIMEOUT:-12}"

  log "provision: online; installing missing packages from rootfs repositories: $packages"

  chroot "$CHROOT_DIR" \
    /usr/bin/env -i \
      HOME=/root \
      PATH="$CHROOT_PATH" \
      DEBIAN_FRONTEND=noninteractive \
      /bin/sh -c "
        apt-get \
          -o Acquire::Retries=2 \
          -o Acquire::http::Timeout=$timeout \
          -o Acquire::https::Timeout=$timeout \
          update &&
        apt-get \
          -o Acquire::Retries=2 \
          -o Acquire::http::Timeout=$timeout \
          -o Acquire::https::Timeout=$timeout \
          install -y --no-install-recommends $packages
      "
}

###############################################################################
# Offline compatibility packs
#
# Pack layout:
#
# offline/debian-family/
#   debian/trixie/<rootfs-architecture>/*.deb
#   ubuntu/noble/<rootfs-architecture>/*.deb
#   kali/kali-rolling/<rootfs-architecture>/*.deb
#   ...
#
# Exact distro packs are preferred.
# Ubuntu derivatives may inherit an Ubuntu base pack only when
# UBUNTU_CODENAME explicitly identifies that base.
###############################################################################

debian_family_find_offline_pack() {
  local root="${DEBIAN_FAMILY_OFFLINE_ROOT:-$START_CHROOT_BASE/offline/debian-family}"
  local candidate
  local -a candidates=()

  candidates+=(
    "$root/$DF_ID/$DF_CODENAME/$DF_ARCH"
  )

  if [ -n "$DF_UBUNTU_CODENAME" ]; then
    candidates+=(
      "$root/ubuntu/$DF_UBUNTU_CODENAME/$DF_ARCH"
    )
  fi

  if [ "$DF_ID" = "ubuntu" ]; then
    candidates+=(
      "$root/ubuntu/$DF_CODENAME/$DF_ARCH"
    )
  fi

  if [ "$DF_ID" = "debian" ]; then
    candidates+=(
      "$root/debian/$DF_CODENAME/$DF_ARCH"
    )
  fi

  for candidate in "${candidates[@]}"; do
    [ -d "$candidate" ] || continue

    if compgen -G "$candidate/*.deb" >/dev/null; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  return 1
}

debian_family_install_offline_pack() {
  local pack="$1"
  local stage="$CHROOT_DIR/tmp/lsa-offline-debs"
  local deb

  log "provision: offline compatibility pack=$pack"

  rm -rf "$stage"
  mkdir -p "$stage"

  for deb in "$pack"/*.deb; do
    [ -f "$deb" ] || continue
    cp -f "$deb" "$stage/"
  done

  if ! compgen -G "$stage/*.deb" >/dev/null; then
    log "WARNING: provision: selected offline pack contains no .deb files"
    rm -rf "$stage"
    return 1
  fi

  if chroot "$CHROOT_DIR" \
      /usr/bin/env -i \
        HOME=/root \
        PATH="$CHROOT_PATH" \
        DEBIAN_FRONTEND=noninteractive \
        /bin/sh -c '
          dpkg -i /tmp/lsa-offline-debs/*.deb
        '
  then
    rm -rf "$stage"
    return 0
  fi

  log "WARNING: provision: offline dpkg transaction failed"
  log "WARNING: provision: apt repair intentionally skipped while offline"

  rm -rf "$stage"
  return 1
}

###############################################################################
# Provisioning entry point
###############################################################################

debian_family_provision() {
  local plugin="libasound2-plugins"
  local offline_pack=""

  if ! debian_family_detect; then
    log "provision: rootfs is not a supported dpkg+apt Debian-family environment; skipped"
    return 0
  fi

  debian_family_read_identity
  debian_family_repair_setuid_ownership

  # This value is useful to every Pulse-native application even if the
  # optional ALSA Pulse plugin is not yet available.
  debian_family_write_pulse_environment

  if debian_family_package_present "$plugin"; then
    log "audio: $plugin already installed"
    debian_family_write_asound_block
    return 0
  fi

  log "audio: $plugin missing"

  if debian_family_network_ready; then
    DEBIAN_FAMILY_NETWORK_STATE="ONLINE"
    log "provision: network preflight PASS (DNS + ${DEBIAN_FAMILY_PROBE_HOST:-google.com}:443)"

    if ! debian_family_apt_install_required; then
      log "WARNING: provision: online APT provisioning failed"
    fi
  else
    DEBIAN_FAMILY_NETWORK_STATE="OFFLINE"
    log "provision: network preflight FAIL"
    log "provision: offline mode; all Internet/APT operations skipped"

    if offline_pack="$(debian_family_find_offline_pack)"; then
      debian_family_install_offline_pack "$offline_pack" || true
    else
      log "WARNING: provision: no exact matching offline binary compatibility pack shipped"
    fi
  fi

  if debian_family_package_present "$plugin"; then
    log "audio: $plugin ready"
    debian_family_write_asound_block
  else
    # Never leave our own ALSA config pointing at an unavailable plugin.
    debian_family_remove_asound_block

    log "WARNING: audio: ALSA Pulse plugin unavailable"
    log "WARNING: audio: native Pulse applications remain configured through PULSE_SERVER"
  fi

  return 0
}

###############################################################################
# Non-fatal runtime sanity check.
###############################################################################

debian_family_audio_preflight() {
  local pulse="${HALAUDIO_PULSE_SERVER:-unix:/tmp/pa-run/pulse/native}"
  local envfile="$CHROOT_DIR/etc/environment"
  local asound="$CHROOT_DIR/etc/asound.conf"

  debian_family_detect || return 0

  if grep -Fxq "PULSE_SERVER=$pulse" "$envfile" 2>/dev/null; then
    log "audio-preflight: persistent PULSE_SERVER OK"
  else
    log "WARNING: audio-preflight: persistent PULSE_SERVER missing/wrong"
  fi

  if debian_family_package_present libasound2-plugins; then
    if grep -q '^# BEGIN LSA MODCHROOT AUDIO$' "$asound" 2>/dev/null; then
      log "audio-preflight: ALSA Pulse default OK"
    else
      log "WARNING: audio-preflight: ALSA Pulse plugin exists but managed default missing"
    fi
  else
    log "WARNING: audio-preflight: libasound2-plugins missing"
  fi

  if [ -S "$CHROOT_DIR/tmp/pa-run/pulse/native" ]; then
    log "audio-preflight: HALAudio Pulse socket READY"
  else
    log "WARNING: audio-preflight: HALAudio Pulse socket unavailable"
  fi

  return 0
}
