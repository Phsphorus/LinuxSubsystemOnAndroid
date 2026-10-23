#!/data/data/com.termux/files/usr/bin/bash
#
# Android-controlled storage stays Android-controlled. LSA only bind-mounts
# the path that vold already mounted, so Android and Debian see the same
# filesystem without a second raw mount. A volume that vold reports as
# UNMOUNTABLE is deliberately not exported this way. The currently supported
# Debian-owned fallback is NTFS through ntfs-3g, and it is mounted under its
# own root so Android never receives a competing view of it.
#
# This file is sourced by the Storage backends after the private LSA mount
# namespace and rootfs exist. It must not mount a volume in Android's global
# namespace.

: "${LSA_CHROOT_DIR:=${CHROOT_DIR:-/data/local/linux}}"
: "${LSA_START_BASE:=${START_CHROOT_BASE:-/data/local/RootStart/Services/ModChroot}}"
: "${LSA_RUNTIME_DIR:=${RUNTIME_DIR:-$LSA_START_BASE/runtime}/capability-framework}"
: "${LSA_STORAGE_VOLD_ENABLE:=1}"
: "${LSA_STORAGE_WATCH_SECONDS:=3}"
: "${LSA_STORAGE_DEBIAN_USER:=${UNSAFE_SUDO_USER:-myuser}}"

LSA_STORAGE_TARGET="$LSA_CHROOT_DIR/mnt/sdcard"
LSA_STORAGE_ANDROID_ROOT="$LSA_CHROOT_DIR/media/android"
LSA_STORAGE_DEBIAN_ROOT="$LSA_CHROOT_DIR/media/debian"
LSA_STORAGE_STATE_FILE="$LSA_CHROOT_DIR/run/lsa/storage-volumes.tsv"
LSA_STORAGE_WATCH_PID_FILE="${LSA_STORAGE_WATCH_PID_FILE:-$LSA_RUNTIME_DIR/storage-watch.pid}"
LSA_STORAGE_WATCH_LOG_FILE="${LSA_STORAGE_WATCH_LOG_FILE:-$LSA_RUNTIME_DIR/storage-watch.log}"

lsa_storage_log() {
  if declare -F log >/dev/null 2>&1; then
    log "storage: $*"
  else
    printf '%s storage: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
  fi
}

lsa_storage_mount_source() {
  local source_path="$1"
  [ -d "$source_path" ] || return 1
  mkdir -p "$LSA_STORAGE_TARGET"
  if awk -v target="$LSA_STORAGE_TARGET" '$2 == target { found=1 } END { exit !found }' /proc/mounts; then
    return 0
  fi
  mount --bind "$source_path" "$LSA_STORAGE_TARGET"
}

lsa_storage_unmount() {
  awk -v target="$LSA_STORAGE_TARGET" '$2 == target { found=1 } END { exit !found }' /proc/mounts || return 0
  umount "$LSA_STORAGE_TARGET"
}

lsa_storage_android_shared_start() {
  lsa_storage_mount_source /sdcard
}

lsa_storage_termux_shared_start() {
  lsa_storage_mount_source "${LSA_TERMUX_HOME:-/data/data/com.termux/files/home}/storage/shared"
}

lsa_storage_safe_name() {
  # Directory names are display-only. The UUID remains part of every name so
  # equal labels cannot collide and a label never controls a path component.
  local label="$1" uuid="$2" safe_label safe_uuid
  safe_label="$(LC_ALL=C printf '%s' "$label" | LC_ALL=C sed 's/[^A-Za-z0-9._ -]/_/g; s/^[_ ]*//; s/[_ ]*$//')"
  safe_uuid="$(LC_ALL=C printf '%s' "$uuid" | LC_ALL=C sed 's/[^A-Za-z0-9._-]/_/g')"
  [ -n "$safe_label" ] || safe_label=volume
  [ -n "$safe_uuid" ] || safe_uuid=unknown
  printf '%s-%s\n' "$safe_label" "$safe_uuid"
}

lsa_storage_mount_source_at() {
  local source_path="$1" target_path="$2" current_source
  mkdir -p "$target_path"
  current_source="$(awk -v target="$target_path" '$2 == target { print $1; exit }' /proc/mounts)"
  if [ -n "$current_source" ]; then
    [ "$current_source" = "$source_path" ] && return 0
    umount "$target_path" || return 1
  fi
  mount --bind "$source_path" "$target_path" || return 1
  # A Debian process must never propagate a mount operation back into Android.
  # The watcher owns cleanup when vold later removes its source mount.
  mount --make-private "$target_path" 2>/dev/null || true
}

lsa_storage_unmount_target() {
  local target_path="$1"
  awk -v target="$target_path" '$2 == target { found=1 } END { exit !found }' /proc/mounts || return 0
  umount "$target_path"
}

lsa_storage_public_device() {
  # public:8,49 -> /dev/block/sdd1, using sysfs rather than assuming an sdX
  # prefix. This is intentionally partition-scoped, never USB-bus-scoped.
  local volume_id="$1" major_minor sys_path node_name
  major_minor="${volume_id#public:}"
  major_minor="${major_minor/,/:}"
  case "$major_minor" in *[!0-9:]*|*:*:*) return 1 ;; esac
  sys_path="$(readlink -f "/sys/dev/block/$major_minor" 2>/dev/null || true)"
  [ -n "$sys_path" ] || return 1
  node_name="${sys_path##*/}"
  [ -b "/dev/block/$node_name" ] || return 1
  printf '/dev/block/%s\n' "$node_name"
}

lsa_storage_debian_identity() {
  local field="$1" value
  value="$(chroot "$LSA_CHROOT_DIR" /usr/bin/id "-$field" "$LSA_STORAGE_DEBIAN_USER" 2>/dev/null || true)"
  case "$value" in ''|*[!0-9]*) return 1 ;; esac
  printf '%s\n' "$value"
}

lsa_storage_ntfs_mount() {
  local volume_id="$1" fs_uuid="$2" fs_label="$3" device target uid gid options
  device="$(lsa_storage_public_device "$volume_id")" || {
    lsa_storage_log "Debian NTFS handoff skipped id=$volume_id: raw partition is absent"
    return 1
  }
  uid="$(lsa_storage_debian_identity u)" || return 1
  gid="$(lsa_storage_debian_identity g)" || return 1
  target="$LSA_STORAGE_DEBIAN_ROOT/$(lsa_storage_safe_name "$fs_label" "$fs_uuid")"
  mkdir -p "$target"
  if awk -v mountpoint="$target" '$2 == mountpoint { found=1 } END { exit !found }' /proc/mounts; then
    return 0
  fi
  options="uid=$uid,gid=$gid,umask=022,big_writes"
  if chroot "$LSA_CHROOT_DIR" /usr/bin/ntfs-3g "/dev/block/${device##*/}" "/media/debian/${target##*/}" -o "$options"; then
    lsa_storage_log "Debian owns NTFS id=$volume_id device=$device target=/media/debian/${target##*/} mode=read-write"
    return 0
  fi
  # A dirty or write-protected filesystem remains useful to Linux as a
  # read-only volume. Do not ever fall back to a raw Android-side mount.
  if chroot "$LSA_CHROOT_DIR" /usr/bin/ntfs-3g "/dev/block/${device##*/}" "/media/debian/${target##*/}" -o "ro,$options"; then
    lsa_storage_log "Debian owns NTFS id=$volume_id device=$device target=/media/debian/${target##*/} mode=read-only"
    return 0
  fi
  lsa_storage_log "Debian NTFS handoff failed id=$volume_id device=$device"
  return 1
}

lsa_storage_vold_records() {
  # Output public volumes as: id<TAB>state<TAB>path<TAB>uuid<TAB>label<TAB>fstype
  # `path` is vold's user-visible path, not /mnt/media_rw's private backing
  # path. Binding it preserves Android's storage policy for Android-owned
  # media.
  dumpsys mount 2>/dev/null | awk '
    function emit() {
      if (id != "" && state != "") {
        gsub(/\t/, " ", label)
        printf "%s\t%s\t%s\t%s\t%s\t%s\n", id, state, path, uuid, label, fstype
      }
    }
    /^[[:space:]]*VolumeInfo\{/ {
      emit()
      id=""
      state=""; path=""; uuid=""; label=""; fstype=""
      if ($0 !~ /^[[:space:]]*VolumeInfo\{public:/) next
      id=$0
      sub(/^[[:space:]]*VolumeInfo\{/, "", id)
      sub(/\}.*/, "", id)
      next
    }
    /^[[:space:]]*type=/ {
      type_line=$0
      if (match(type_line, /state=[^[:space:]]+/)) {
        state=substr(type_line, RSTART + 6, RLENGTH - 6)
      }
      next
    }
    /^[[:space:]]*state=/ {
      state=$0
      sub(/^[[:space:]]*state=/, "", state)
      sub(/[[:space:]].*/, "", state)
      next
    }
    /^[[:space:]]*path=/ {
      path=$0
      sub(/^[[:space:]]*path=/, "", path)
      sub(/[[:space:]].*/, "", path)
      next
    }
    /^[[:space:]]*fsUuid=/ {
      uuid=$0
      sub(/^[[:space:]]*fsUuid=/, "", uuid)
      sub(/[[:space:]].*/, "", uuid)
      next
    }
    /^[[:space:]]*fsLabel=/ {
      label=$0
      sub(/^[[:space:]]*fsLabel=/, "", label)
      sub(/[[:space:]].*/, "", label)
      next
    }
    /^[[:space:]]*fsType=/ {
      fs_line=$0
      if (match(fs_line, /fsType=[^[:space:]]+/)) {
        fstype=substr(fs_line, RSTART + 7, RLENGTH - 7)
      }
      if (match(fs_line, /fsUuid=[^[:space:]]+/)) {
        uuid=substr(fs_line, RSTART + 7, RLENGTH - 7)
      }
      if (match(fs_line, /fsLabel=[^[:space:]]+/)) {
        label=substr(fs_line, RSTART + 8, RLENGTH - 8)
      }
      next
    }
    END { emit() }
  '
}

lsa_storage_publish_state() {
  local state_tmp="$LSA_STORAGE_STATE_FILE.tmp.$$" target
  install -d -m 755 "${LSA_STORAGE_STATE_FILE%/*}"
  {
    printf '# ownership\tvolume_id\tpath\tfilesystem\tdetail\n'
    lsa_storage_vold_records | while IFS="$(printf '\t')" read -r volume_id state path fs_uuid fs_label fstype; do
      case "$state" in
        MOUNTED)
          [ -n "$path" ] && [ "$path" != null ] || continue
          printf 'android\t%s\t/media/android/%s\t%s\tAndroid vold path %s\n' "$volume_id" "$(lsa_storage_safe_name "$fs_label" "$fs_uuid")" "${fstype:-unknown}" "$path"
          ;;
        UNMOUNTABLE)
          target="$LSA_STORAGE_DEBIAN_ROOT/$(lsa_storage_safe_name "$fs_label" "$fs_uuid")"
          if [ "$fstype" = ntfs ] && awk -v mountpoint="$target" '$2 == mountpoint { found=1 } END { exit !found }' /proc/mounts; then
            printf 'debian\t%s\t/media/debian/%s\tntfs\tMounted by the LSA NTFS handoff\n' "$volume_id" "${target##*/}"
          elif [ "$fstype" = ntfs ]; then
            printf 'unhandled\t%s\t-\tntfs\tAndroid rejected the filesystem; LSA NTFS handoff could not mount it\n' "$volume_id"
          else
            printf 'unhandled\t%s\t-\t%s\tAndroid rejected the filesystem; no Debian driver is registered\n' "$volume_id" "${fstype:-unknown}"
          fi
          ;;
      esac
    done
  } >"$state_tmp"
  chmod 644 "$state_tmp"
  mv "$state_tmp" "$LSA_STORAGE_STATE_FILE"
}

lsa_storage_sync_android_owned() {
  local seen_file="$LSA_RUNTIME_DIR/storage-android-seen.$$" volume_id state path fs_uuid fs_label fstype target
  : >"$seen_file" || return 1
  while IFS="$(printf '\t')" read -r volume_id state path fs_uuid fs_label fstype; do
    [ "$state" = MOUNTED ] || continue
    [ -n "$path" ] && [ "$path" != null ] || continue
    [ -d "$path" ] || {
      lsa_storage_log "Android volume id=$volume_id says MOUNTED but path is unavailable: $path"
      continue
    }
    target="$LSA_STORAGE_ANDROID_ROOT/$(lsa_storage_safe_name "$fs_label" "$fs_uuid")"
    if lsa_storage_mount_source_at "$path" "$target"; then
      printf '%s\n' "$target" >>"$seen_file"
    else
      lsa_storage_log "Android volume export failed id=$volume_id source=$path"
    fi
  done < <(lsa_storage_vold_records)

  # Only remove mounts below the module-owned Android export root. The root
  # itself, user folders, and every unrelated mount remain untouched.
  while IFS= read -r target; do
    case "$target" in "$LSA_STORAGE_ANDROID_ROOT"/*) ;; *) continue ;; esac
    grep -Fqx "$target" "$seen_file" && continue
    lsa_storage_unmount_target "$target" || lsa_storage_log "stale Android export could not unmount: $target"
  done < <(awk -v prefix="$LSA_STORAGE_ANDROID_ROOT/" '$2 ~ "^" prefix { print $2 }' /proc/mounts)
  rm -f "$seen_file"
}

lsa_storage_sync_debian_owned() {
  local seen_file="$LSA_RUNTIME_DIR/storage-debian-seen.$$" volume_id state path fs_uuid fs_label fstype target
  : >"$seen_file" || return 1
  while IFS="$(printf '\t')" read -r volume_id state path fs_uuid fs_label fstype; do
    [ "$state" = UNMOUNTABLE ] || continue
    [ "$fstype" = ntfs ] || continue
    target="$LSA_STORAGE_DEBIAN_ROOT/$(lsa_storage_safe_name "$fs_label" "$fs_uuid")"
    if lsa_storage_ntfs_mount "$volume_id" "$fs_uuid" "$fs_label"; then
      printf '%s\n' "$target" >>"$seen_file"
    fi
  done < <(lsa_storage_vold_records)
  while IFS= read -r target; do
    case "$target" in "$LSA_STORAGE_DEBIAN_ROOT"/*) ;; *) continue ;; esac
    grep -Fqx "$target" "$seen_file" && continue
    lsa_storage_unmount_target "$target" || lsa_storage_log "stale Debian export could not unmount: $target"
  done < <(awk -v prefix="$LSA_STORAGE_DEBIAN_ROOT/" '$2 ~ "^" prefix { print $2 }' /proc/mounts)
  rm -f "$seen_file"
}

lsa_storage_prepare_user_paths() {
  local home="$LSA_CHROOT_DIR/home/$LSA_STORAGE_DEBIAN_USER" uid gid
  install -d -m 755 "$LSA_STORAGE_ANDROID_ROOT" "$LSA_STORAGE_DEBIAN_ROOT" "${LSA_STORAGE_STATE_FILE%/*}"
  [ -d "$home" ] || return 0
  uid="$(lsa_storage_debian_identity u 2>/dev/null || true)"
  gid="$(lsa_storage_debian_identity g 2>/dev/null || true)"
  ln -sfn /media/android "$home/Android Storage"
  ln -sfn /media/debian "$home/Debian Storage"
  case "$uid:$gid" in *[!0-9:]*|:) ;; *) chown -h "$uid:$gid" "$home/Android Storage" "$home/Debian Storage" 2>/dev/null || true ;; esac
}

lsa_storage_external_sync() {
  [ "$LSA_STORAGE_VOLD_ENABLE" = 1 ] || return 0
  lsa_storage_prepare_user_paths || return 1
  lsa_storage_sync_android_owned
  lsa_storage_sync_debian_owned
  lsa_storage_publish_state
}

lsa_storage_external_watcher_running() {
  local pid
  [ -r "$LSA_STORAGE_WATCH_PID_FILE" ] || return 1
  pid="$(cat "$LSA_STORAGE_WATCH_PID_FILE" 2>/dev/null || true)"
  case "$pid" in ''|*[!0-9]*) return 1 ;; esac
  kill -0 "$pid" 2>/dev/null
}

lsa_storage_external_start() {
  [ "$LSA_STORAGE_VOLD_ENABLE" = 1 ] || return 0
  mkdir -p "$LSA_RUNTIME_DIR"
  lsa_storage_external_sync || lsa_storage_log 'initial removable-storage sync had failures'
  if lsa_storage_external_watcher_running; then
    return 0
  fi
  rm -f "$LSA_STORAGE_WATCH_PID_FILE"
  (
    while :; do
      lsa_storage_external_sync || lsa_storage_log 'removable-storage sync had failures'
      sleep "$LSA_STORAGE_WATCH_SECONDS"
    done
  ) >>"$LSA_STORAGE_WATCH_LOG_FILE" 2>&1 &
  printf '%s\n' "$!" >"$LSA_STORAGE_WATCH_PID_FILE"
  lsa_storage_log "removable-storage watcher started pid=$! interval=${LSA_STORAGE_WATCH_SECONDS}s"
}

lsa_storage_external_stop() {
  local pid target
  if [ -r "$LSA_STORAGE_WATCH_PID_FILE" ]; then
    pid="$(cat "$LSA_STORAGE_WATCH_PID_FILE" 2>/dev/null || true)"
    case "$pid" in *[!0-9]*|'') ;; *) kill "$pid" 2>/dev/null || true ;; esac
  fi
  rm -f "$LSA_STORAGE_WATCH_PID_FILE"
  for target in "$LSA_STORAGE_ANDROID_ROOT"/* "$LSA_STORAGE_DEBIAN_ROOT"/*; do
    [ -e "$target" ] || continue
    lsa_storage_unmount_target "$target" || true
  done
}
