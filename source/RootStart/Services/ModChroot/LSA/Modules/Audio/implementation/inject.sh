#!/system/bin/sh
set -eu

BASE="${START_CHROOT_BASE:-/data/local/RootStart/Services/ModChroot}"
CHROOT_DIR="${CHROOT_DIR:-/data/local/linux}"
SRC="$BASE/LSA/Modules/Audio/implementation/rootfs"

if [ ! -d "$SRC" ]; then
  echo "ModChroot: audio: module rootfs source missing: $SRC" >&2
  return 1
fi

# Debian commonly exposes /bin as an absolute symlink to /usr/bin.  Do not
# apply this module as a rootfs-wide overlay: a source `bin/` directory would
# cause cp to chase that link from the host mount namespace.  The Audio module
# owns exactly these two Linux-facing locations, so install them explicitly.
mkdir -p \
  "$CHROOT_DIR/usr/local/bin" \
  "$CHROOT_DIR/usr/local/lib/halbridge"
chown 0:0 "$CHROOT_DIR/usr/local/bin" "$CHROOT_DIR/usr/local/lib" "$CHROOT_DIR/usr/local/lib/halbridge"
chmod 755 "$CHROOT_DIR/usr/local/bin" "$CHROOT_DIR/usr/local/lib" "$CHROOT_DIR/usr/local/lib/halbridge"

# Do not preserve source-tree directory metadata here.  RootStart's release
# tree is intentionally private (umask 077), whereas HALAudio executes as an
# ordinary Linux user and must traverse this module's package directories.
find "$SRC/halbridge" -type d | while IFS= read -r source_dir; do
  relative="${source_dir#"$SRC/halbridge"}"
  target_dir="$CHROOT_DIR/usr/local/lib/halbridge$relative"
  mkdir -p "$target_dir"
  chown 0:0 "$target_dir"
  chmod 755 "$target_dir"
done
find "$SRC/halbridge" -type f | while IFS= read -r source_file; do
  relative="${source_file#"$SRC/halbridge/"}"
  target_file="$CHROOT_DIR/usr/local/lib/halbridge/$relative"
  cp -f "$source_file" "$target_file"
  chown 0:0 "$target_file"
  chmod 644 "$target_file"
done
install -m 755 "$SRC/bin/HALAudio" "$CHROOT_DIR/usr/local/bin/HALAudio"
chmod 755 "$CHROOT_DIR/usr/local/bin/HALAudio" 2>/dev/null || true
chmod 755 "$CHROOT_DIR/usr/local/lib/halbridge/HALAudio.py" 2>/dev/null || true
chmod 755 "$CHROOT_DIR/usr/local/lib/halbridge/HALAudioAutouser.sh" 2>/dev/null || true

if command -v log >/dev/null 2>&1; then
  log "audio: injected module-owned Linux Pulse/ALSA implementation"
else
  echo "ModChroot: audio: injected module-owned Linux Pulse/ALSA implementation"
fi
