# Architecture and unknown-device portability

LSA chooses implementations from detected primitives and capabilities, never from a phone model except when enabling an explicitly device-scoped optional provider.

## Independent architecture axes

The framework detects and records all of the following separately:

| Axis | Source | Why it matters |
|---|---|---|
| Android ABI | `ro.product.cpu.abi` and ABI list | Android libraries and app-side provider compatibility |
| Kernel architecture | `uname -m` | kernel interfaces and native tooling |
| Termux userspace | Termux `dpkg --print-architecture` | Termux executable and package compatibility |
| Linux rootfs | rootfs `dpkg --print-architecture` | chroot executables and injected Linux artifacts |
| Shipped binary | `readelf`/`file` inspection | whether one specific prebuilt artifact can run |

The normalization vocabulary is `arm64`, `armv7`, `x86`, and `x86_64`; it accepts normal source spellings such as `aarch64`, `arm64-v8a`, `armv8l`, `armv7l`, `armeabi-v7a`, Debian `armhf`/`armel`, and `amd64`. `armv8l` remains the 32-bit ARM userspace path; it is not treated as arm64.

`architecture.tsv` and `binaries.tsv` are regenerated runtime evidence. They let a provider reject an incompatible optional binary as `UNSUPPORTED` while keeping the rest of LSA able to select fallbacks. Architecture detection is not device identity detection.

## Tier Z baseline

Tier Z is reserved for actual lowest-common-denominator implementations, not for complete-letter decoration. The first implemented baseline is `storage.termux-shared`: when conventional Android shared-storage mounting is unavailable or rejected, it exposes normal Termux shared storage through the module-owned Linux mount. It requires Termux shared storage to be set up; otherwise its probe truthfully reports `UNSUPPORTED` with the setup diagnostic.

Higher tiers keep their own performance and fidelity requirements. A Z backend may be slower or less native, but it must still expose a real useful contract and must never weaken an available higher-tier backend.

## Challenger-phone procedure

The challenger must use the unmodified generic framework:

1. Deploy the canonical package without a device provider for that phone.
2. Start NonRootStart as the Termux user, then RootStart under Android root.
3. Collect `lsectl report --verbose`, `architecture.tsv`, `binaries.tsv`, provider state, and lifecycle logs.
4. Treat absent prerequisites as `UNSUPPORTED` or `ERROR`, retain diagnostics, and let selection continue.
5. Exercise a real Tier-Z candidate where appropriate and verify at least one generic module selects above Z.
6. Use backend rejection to force a lower accepted candidate, then clear it and validate restart/teardown behavior.

No challenger-phone model/manufacturer branch, device directory, or kernel workaround is permitted.

## Challenger baseline, 2026-09-06

The first generic challenger preflight was performed against an otherwise unknown rooted Android 9 device with an `armeabi-v7a` Android ABI, an `armv8l` kernel, and an `arm` Termux userspace. The framework correctly normalized all three applicable axes to `armv7`; it did not infer arm64 from the kernel spelling and did not use device identity to do so.

The device had no Linux rootfs and no Termux API/capture services installed. The deployed framework therefore completed a verbose report without starting services, selected no false backend, and reported the chroot-dependent modules as `UNSUPPORTED` with their missing-capability diagnostics. This is a valid preflight outcome, not a global startup failure. It cannot establish the required above-Z runtime selection until a compatible Linux rootfs and the relevant generic provider prerequisites are present.

That deployment also exposed a generic package-verification defect: several lifecycle scripts declared Bash but were syntax-checked with Android's POSIX shell. The verifier now uses the installed Termux Bash interpreter for every shipped shell script. No challenger-specific change was made.

The device was then bootstrapped with a minimal generic Debian `armhf` rootfs. The framework recorded the rootfs axis as `armhf`/`armv7`, rejected the bundled arm64-only N6000 H.264 consumer as `UNSUPPORTED`, and selected the generic CoreChroot Tier A, Audio Tier A, DeviceNamespace Tier B, and Storage Tier A candidates. A controlled RootStart run reached real CoreChroot mounts, the private `/dev` namespace, and module-owned Audio/Sensor/Video injection before optional offline dependencies were deferred.

NonRootStart now discovers vendor/device lifecycle providers by scope and requires their own `probe` action before starting them. On the challenger, generic Capture, Audio, and SensorBus services ran; GPUBridge reported `ERROR`; and the existing N6000 provider self-reported `UNSUPPORTED` without starting its device process. The same generic flow was regression-checked on the N6000, where all of those services and the N6000 video provider reported `RUNNING`.

The challenger has not granted normal Termux shared storage, so the real `storage.termux-shared` Z backend remains unavailable with its prerequisite diagnostic. It is intentionally not fabricated. A temporary persistent rejection of Storage Tier A was recorded and then cleared through the generic policy ledger. Missing Termux:X11, DNS, capture/location API, GPU, and FUSE prerequisites are reported as `UNSUPPORTED` or `ERROR`; they no longer abort the selected generic rootfs lifecycle.
