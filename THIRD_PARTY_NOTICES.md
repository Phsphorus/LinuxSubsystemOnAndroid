# Third-Party Notices for LSA and LSADeploy

LSADeploy is a distribution aggregate.  The license for an included component
continues to apply to that component; conveying an APK beside Apache-licensed
LSA scripts does not change either component's license.

## LSA original material

Copyright 2026 Phsphorus.

Unless a file carries a different license notice, LSA-authored source,
documentation, deployment scripts, and generated LSA payloads are licensed
under Apache License 2.0.  See `LICENSE`, `NOTICE`, and
`LICENSES/Apache-2.0.txt`.

## Termux:API

`apps/termux-api.apk` is the Termux:API Android add-on, package
`com.termux.api`, version `0.53.0` (version code `1002`).  It is distributed
under GNU GPL version 3.  Its license text is included at
`LICENSES/GPL-3.0.txt`.

Upstream source and notices: <https://github.com/termux/termux-api/tree/v0.53.0>
(upstream tag commit `6c8eaa223bcc387e6b28146d340acb20712aa3e7`).

Termux:API is a separate Android application.  LSA invokes its documented
Android/Termux interfaces; it is not relicensed by LSA.

## LSA-X11

`apps/lsa-x11.apk` is LSA-X11, package `com.phsphorus.lsa.x11`, version
`1.03.01-0fff278-07.09.26` (version code `15`).  LSA-X11 is a GPL-3.0-only
derivative of Termux:X11.  It retains GPL-3.0 licensing, and the complete
license text is included at `LICENSES/GPL-3.0.txt`.

Project source location: <https://github.com/Phsphorus/lsa-x11>.
Termux:X11 upstream: <https://github.com/termux/termux-x11>.

The release builder also places the designated LSA-X11 workspace source
snapshot in `sources/` and records its hash, workspace revision, and
correspondence status in `manifest/SOURCES.tsv`. The APK build attestation is
included as `manifest/LSA-X11-BUILD.tsv`. See
`SOURCE_AVAILABILITY.md` before redistributing a prebuilt LSA-X11 APK.

## Additional notices

The LSA-X11 source snapshot contains additional third-party source trees and
their own copyright and license notices.  They remain in that source snapshot
and must be retained when redistributing a derivative.  Android, Termux, and
Debian packages installed later by a target device are not redistributed as
part of the LSADeploy payload; their package-manager and upstream licenses
apply independently.
