# Source Availability

This file identifies source material for the LSADeploy release.  It is release
metadata, not legal advice.

## LSA

The source form of LSA-owned runtime code is the human-readable shell and
Python source in the canonical `LSALIVE/source` tree.  The deployment scripts
are in `LSALIVE/deploy`, and the release builder is in `LSALIVE/tools`.
The installed payloads preserve the executable LSA shell/Python source rather
than replacing it with opaque binaries.  LSA-owned material is Apache-2.0;
see `LICENSE` and `NOTICE`.

## GPL components bundled in LSADeploy

### Termux:API

The exact bundled app identity, version, and APK SHA-256 are recorded in
`manifest/APPS.tsv` and `manifest/SOURCES.tsv`.  Corresponding source is the
immutable upstream `v0.53.0` tag:

    https://github.com/termux/termux-api/tree/v0.53.0

That tag resolves to `6c8eaa223bcc387e6b28146d340acb20712aa3e7`.

### LSA-X11

LSA-X11 is GPL-3.0-only and is derived from Termux:X11.  The maintained
project location is:

    https://github.com/Phsphorus/lsa-x11

Each LSADeploy build also contains a source snapshot in `sources/`, generated
from the designated `Terp/lsa-x11` workspace with build output, caches,
historical Workshop material, local SDK configuration, and Git metadata
excluded.  Checked-out third-party source directories and license notices are
retained.  Its archive path and SHA-256 are recorded in
`manifest/SOURCES.tsv`.

The bundled LSA-X11 APK was rebuilt from the recorded designated workspace.
`manifest/LSA-X11-BUILD.tsv` binds its SHA-256 to the workspace revision and
workspace state used for the build. The release builder verifies that binding
and places an immediately generated source snapshot from that workspace in
the same release. `manifest/SOURCES.tsv` therefore records
`REBUILT_FROM_RECORDED_WORKSPACE`.

This is a build attestation and source-availability record, not a claim of
bit-for-bit reproducibility across all build hosts. The workspace was dirty
when rebuilt, so the same-release source archive is the authoritative source
record for the bundled APK rather than the Git revision alone.

## How to obtain the source in an offline copy

Extract the relevant archive under `sources/` from the same LSADeploy release.
For online source retrieval, use the immutable Termux:API tag above and the
LSA-X11 project location.  Keep this file, `THIRD_PARTY_NOTICES.md`,
`manifest/SOURCES.tsv`, and all applicable license notices with any further
redistribution.
