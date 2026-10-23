# Bundled Android applications

This directory contains exact, checksum-pinned APKs used by LSADeploy.  Their
package identities, versions, and SHA-256 values are in
`../manifest/APPS.tsv` and `../manifest/SOURCES.tsv`.

| APK | Package | License | Source |
| --- | --- | --- | --- |
| `termux-api.apk` | `com.termux.api` | GPL-3.0-only | https://github.com/termux/termux-api/tree/v0.53.0 |
| `lsa-x11.apk` | `com.phsphorus.lsa.x11` | GPL-3.0-only | https://github.com/Phsphorus/lsa-x11 |

`lsa-x11.apk` is an LSA-X11 derivative of Termux:X11.  It is not relicensed
under Apache-2.0 merely because the LSA deployer distributes it beside
Apache-licensed LSA code.  The release includes the GPL-3.0 text and records
source availability in `../SOURCE_AVAILABILITY.md`.

Do not replace, re-sign, or rename either APK without updating `APPS.tsv`,
`manifest/SOURCES.tsv`, the associated source record, and the package
checksums.
