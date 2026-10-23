#!/system/bin/sh
set -u

CHROOT_DIR="${CHROOT_DIR:-/data/local/linux}"
CHROOT_PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

echo "ModChroot: sensor: checking LSA sensor dependencies"

chroot "$CHROOT_DIR" \
    /usr/bin/env -i \
    HOME=/root \
    PATH="$CHROOT_PATH" \
    DEBIAN_FRONTEND=noninteractive \
    /bin/sh -s <<'CHROOT'
set -eu

missing=0

for pkg in \
    fuse3 \
    python3-fusepy \
    libiio-utils \
    binutils \
    gcc \
    libc6-dev
do
    if ! dpkg-query \
        -W \
        -f='${Status}' \
        "$pkg" \
        2>/dev/null |
        grep -q '^install ok installed$'
    then
        echo "sensor: missing package: $pkg"
        missing=1
    fi
done

if [ "$missing" -eq 0 ]; then
    echo "sensor: LSA sensor dependencies already installed"
    exit 0
fi

case "${DEBIAN_FAMILY_NETWORK_STATE:-UNKNOWN}" in
    ONLINE)
        ;;
    OFFLINE)
        echo "sensor: package network was already verified unavailable; dependency installation deferred"
        exit 0
        ;;
    *)
        # This hook runs after the shared Debian-family provisioner.  When it
        # did not establish a usable route, do not make a second, potentially
        # slow APT probe a startup dependency for unrelated modules.
        echo "sensor: no verified package network is available; dependency installation deferred"
        exit 0
        ;;
esac

echo "sensor: installing LSA sensor dependencies"

if ! apt-get \
    -o Acquire::Retries=0 \
    -o Acquire::http::Timeout=10 \
    -o Acquire::https::Timeout=10 \
    update
then
    echo "sensor: package network is unavailable; dependency installation deferred"
    exit 0
fi

if ! apt-get install -y \
    fuse3 \
    python3-fusepy \
    libiio-utils \
    binutils \
    gcc \
    libc6-dev
then
    echo "sensor: dependency installation failed; keeping sensor backend unavailable"
    exit 0
fi
CHROOT
