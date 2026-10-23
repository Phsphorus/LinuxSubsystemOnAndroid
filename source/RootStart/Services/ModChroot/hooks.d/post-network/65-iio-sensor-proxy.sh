# Provision the optional Linux iio-sensor-proxy compatibility entry while
# respecting the shared Debian-family online/offline decision.  This hook can
# be sourced or executed, so a missing optional package must never `exit` the
# ModChroot lifecycle or delay unrelated modules such as Wireless.

CHROOT_DIR="${CHROOT_DIR:-/data/local/linux}"
IIO_BIN="/usr/libexec/iio-sensor-proxy"

# The dependency hook has already provisioned this optional package.  Do not
# invoke dpkg or apt in the boot path: on the N6000 those calls can block for a
# minute while package state is inspected, delaying every LSA backend.
if [ -x "$CHROOT_DIR$IIO_BIN" ] || [ -x "$CHROOT_DIR$IIO_BIN.lsa-stock" ]; then
  # LSA owns this compatibility entry.  Package upgrades are unusual and the
  # entry is restored on every boot, so do not run dpkg-divert here: on this
  # device it can block the whole ModChroot lifecycle while package state is
  # being inspected.  Keeping the boot path bounded matters more than a
  # persistent diversion for an optional desktop integration.
  cat > "$CHROOT_DIR$IIO_BIN" <<'LAUNCHER'
#!/bin/sh
exec /usr/bin/python3 \
  /usr/local/lib/lsa/sensors/LSASensorProxy.py "$@"
LAUNCHER
  chmod 0755 "$CHROOT_DIR$IIO_BIN"
  log "sensor: LSA iio-sensor-proxy compatibility entry installed"
else
  log "sensor: iio-sensor-proxy is not installed; compatibility entry deferred"
fi
