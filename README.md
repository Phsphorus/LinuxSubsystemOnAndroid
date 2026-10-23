# Linux Subsystem on Android (LSA)

LSA makes rooted Android hardware available through the Linux interfaces that
ordinary Linux programs already use. The project uses Android as the hardware
adapter: Android talks to its vendor drivers and LSA publishes the result as
Linux audio, camera, sensor, display, storage, GPU, and related interfaces.

This repository is the public source form of LSA. It is meant to be forked,
reviewed, and packaged. It contains the installer inputs, the Android and
Debian runtime source, deployment scripts, checksums, and the compatibility
ledger for the reference device.

## What is here

- `source/` is the runtime source installed on the phone.
- `deploy/` contains the deployer template.
- `tools/` builds payloads and a deployable `LSADeploy` directory.
- `docs/COMPATIBILITY_MATRIX.md` records real results, including the Blackview
  N6000 reference device. A selected backend is not presented as working until
  an actual Linux-facing path has been tested.
- `assets/`, `manifest/`, `LICENSES/`, and the notices provide the release
  inputs and source correspondence for bundled components.

The current desktop layout uses the LSA phone shell on Termux:X11 display `:0`.
LXDE is kept on VNC display `:1` as an independent desktop workspace.

## Build a release

The current Windows builder uses Cygwin tools and an Android NDK. Set the paths
before building:

```powershell
$env:CYGWIN_ROOT = 'C:\cygwin64'             # optional when Cygwin is here
$env:ANDROID_NDK_ROOT = 'C:\Android\ndk\<version>'
$env:LSA_X11_WORKSPACE = 'C:\path\to\lsa-x11' # optional when it is a sibling checkout
powershell -ExecutionPolicy Bypass -File .\tools\build_deploy_package.ps1
```

The builder writes `LSADeploy` beside this checkout. Read
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) before installing it on a phone.

## Compatibility work

Start with an unmodified generic install on a new phone. Save the framework
report and the application-level failure evidence before adding a device patch.
A device-specific adapter is welcome when it is clearly marked and does not
pretend to be generic support. The full process is in the compatibility matrix.

## Releasing changes

Use the release checklist in [`docs/RELEASING.md`](docs/RELEASING.md). A release
is only called stable for the device and interfaces that have a recorded
witnessed result.

The current release description is in
[`docs/RELEASE_NOTES_1.4.1.8_CoreCompat.md`](docs/RELEASE_NOTES_1.4.1.8_CoreCompat.md).

## License

LSA-authored code is Apache-2.0. Bundled and third-party parts keep their own
licenses; see `LICENSE`, `NOTICE`, `THIRD_PARTY_NOTICES.md`, and `LICENSES/`.
