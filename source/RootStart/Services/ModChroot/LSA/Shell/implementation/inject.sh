#!/data/data/com.termux/files/usr/bin/bash

# The disposable Debian rootfs receives the canonical shell on every start.
lsa_shell_install_rootfs() {
  local source destination root
  root="${CHROOT_DIR:-/data/local/linux}"
  source="$BASE/LSA/Shell/implementation/rootfs"
  destination="$root/usr/local/lib/lsa/shell"

  [ -d "$source" ] || {
    log "shell: source directory missing: $source"
    return 1
  }

  install -d -m 755 -o 0 -g 0 "$destination" "$destination/assets" "$root/usr/local/bin" "$root/root/.config/tigervnc"
  install -m 755 -o 0 -g 0 "$source/lsa-shell.py" "$destination/lsa-shell.py"
  install -m 755 -o 0 -g 0 "$source/lsa-session" "$root/usr/local/bin/lsa-session"
  install -m 755 -o 0 -g 0 "$source/lsa-record-video" "$root/usr/local/bin/lsa-record-video"
  install -m 755 -o 0 -g 0 "$source/lsa-vnc-xstartup" "$root/root/.config/tigervnc/xstartup"
  install -m 644 -o 0 -g 0 "$source/assets/lsa-wallpaper-v1.png" "$destination/assets/lsa-wallpaper-v1.png"
  install -m 644 -o 0 -g 0 "$source/openbox-rc.xml" "$destination/openbox-rc.xml"
  log "shell: injected Debian X11 phone shell and VNC xstartup"
}
