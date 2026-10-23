LSA Debian-family offline compatibility packs
=============================================

Purpose
-------

When ModChroot cannot prove that both DNS and google.com:443 are reachable,
APT and all other Internet-dependent provisioning are skipped.

A matching package pack may then be installed entirely offline.

Directory format
----------------

  <distro-id>/<base-codename>/<dpkg-architecture>/*.deb

Examples:

  debian/trixie/arm64/
  debian/bookworm/arm64/
  ubuntu/noble/arm64/
  ubuntu/jammy/arm64/
  kali/kali-rolling/arm64/

Rules
-----

1. Packs must be built for the exact compatible distro/base release.

2. Ubuntu derivatives may use an Ubuntu pack when /etc/os-release exposes
   UBUNTU_CODENAME.

3. Unknown Debian derivatives do NOT automatically consume Debian binary
   packages merely because ID_LIKE contains "debian".

4. A pack must contain its complete required dependency set for the intended
   target. ModChroot will never run "apt -f install" while offline.

5. Package installation failure is non-fatal. LSA continues booting.

6. Third-party binaries added here must have their redistribution/license
   obligations recorded in the release's third-party manifest before a
   formal release is published.

Current universal offline behavior
----------------------------------

LSA-owned configuration and integration files remain fully offline.

Third-party distro binary packages are installed only when an exact matching
pack exists.

Default release policy
----------------------

LSA does not bundle Debian/Ubuntu/Kali/Mint or other distribution packages
by default.

This directory is intentionally only an extension point.

Third-party binary packages should be added only when a specific integration
requirement cannot reasonably be satisfied from the target rootfs's own APT
repositories or by LSA-owned software.

An empty compatibility-pack tree is therefore the normal expected state.
