# Portable deployment artifact

This checkout is the canonical LSA source tree. Build a deployment release from
its root with:

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\build_deploy_package.ps1
```

The builder writes the current release to `../LSADeploy`. It first rebuilds the
two payload archives from `source/`, retains any previous payload and release
under `../tmp/backups`, and leaves its clean-extraction evidence under
`../tmp/package-builds`.
It never relies on an adjacent source checkout at deployment time.

The release contains exact, checksum-pinned Android application assets:

- Termux:API `com.termux.api`, version `0.53.0` / code `1002`
- LSA X11 `com.phsphorus.lsa.x11`, version `1.03.01-0fff278-07.09.26` / code `15`

The LSA X11 artifact is rebuilt from the recorded designated workspace and
retains the prior APK signing certificate. Its checksum, workspace revision,
and source-workspace state are bound in `manifest/LSA-X11-BUILD.tsv`. The
Termux:API artifact was acquired from the known-good target into the temporary
approved-artifact area, verified against its installed package hash, and then
admitted as an explicitly versioned release asset. Neither release asset
contains an LSA device secret.

## Phone operation

Copy or extract `LSADeploy` anywhere reachable by the phone, become Android
root, and invoke its own script:

```sh
cd /any/location/LSADeploy
./deploy.sh
```

`deploy.sh` resolves its own directory before reading payloads, manifests, or
APKs. It is not dependent on the caller's directory.

`./deploy.sh framework-only` performs the initial framework installation and
report only. `./deploy.sh resume-rootfs` requests full deployment while making
an interrupted debootstrap second stage explicit. A normal `./deploy.sh` is
the full path.

The deployment stages are:

1. Validate root, supported Termux identity, dynamic Termux UID/GID, free
   storage, existing payload/rootfs/session state, and all architecture axes.
2. Install RootStart and NonRootStart framework payloads after preserving an
   inactive prior installation. Active RootStart or NonRootStart sessions are
   rejected rather than overwritten.
3. Install generic Termux prerequisites as the actual Termux UID, never as
   Android root.
4. Hash-validate the bundled Android apps and only install/replace when the
   installed package differs. Signature failures remain explicit; the deployer
   does not uninstall an application to bypass Android signature protection.
5. Create a detected-architecture Debian rootfs, retaining state and logs.
   `NOT_PRESENT`, `BOOTSTRAPPING`, `FAILED`, and `COMPLETE` are distinct; an
   incomplete rootfs is never treated as bootable.
6. Regenerate the local HALAgent secret and runtime directories, then restore
   the persistent backend-rejection ledger if a prior installation had one.
7. Produce a framework report before and after rootfs/startup, start
   NonRootStart first, and run lightweight actual health checks.

The deployer maps the active Termux userspace only: `arm64 -> arm64`, `armv7
-> armhf`, `x86_64 -> amd64`, and `x86 -> i386`. Android ABI, kernel, Termux,
rootfs, and individual shipped ELF architecture remain independent recorded
axes. Device model data is diagnostic-only and never installs a provider or
selects a backend.

The release preserves `lsectl reject` policy in the root-owned rejection ledger
and never silently clears it. If a bundled binary cannot run on the detected
axis, the normal framework report records it as `UNSUPPORTED` with its reason;
unrelated modules continue probing and falling back.
