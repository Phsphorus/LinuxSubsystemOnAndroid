write_resolv_to_local_stub() {
  log "dns: writing $CHROOT_DIR/etc/resolv.conf -> $DNS_LOCAL_IP"

  {
    echo "nameserver $DNS_LOCAL_IP"
    echo "options timeout:1 attempts:2"
  } >"$CHROOT_DIR/etc/resolv.conf"

  chmod 644 "$CHROOT_DIR/etc/resolv.conf" 2>/dev/null || true
}
