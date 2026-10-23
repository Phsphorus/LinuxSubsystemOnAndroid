# Capability registry

The registry lives at runtime under `RootStart/Services/ModChroot/runtime/capability-framework/`. It writes `capabilities.tsv`, `providers.tsv`, `backends.tsv`, and `state.tsv` after post-mount and post-network refreshes, then rewrites runtime state after pre-enter services are ready without reprobing candidates.

Primitive probes include `capability.host.root`, `capability.chroot.rootfs`, `capability.mount`, `capability.device.host`, `capability.fuse.kernel`, and `capability.android.properties`.

Architecture is a detected capability, not a model property. Every refresh records the raw and normalized Android ABI, kernel architecture, Termux userspace architecture, and Linux-rootfs architecture. It adds `capability.architecture.detected`, `capability.arch.{android,kernel,termux,rootfs}.known`, and axis-specific capabilities such as `capability.arch.rootfs.arm64`. Supported normalizations are `arm64`, `armv7`, `x86`, and `x86_64`.

| Provider | Provides |
|---|---|
| `android.rootfs` | root, bootable chroot rootfs, mount, host-device primitives |
| `android.termux` | Termux execution context, Unix sockets |
| `android.fuse` | FUSE mounting |
| `android.sensorbus` | `capability.sensorbus` |
| `android.halaudio` | Termux-user AAudio microphone/output provider and Pulse compatibility input |
| `android.capture` | Android Camera API, loopback MJPEG/snapshot, Android Location API, GPSD |
| `android.halagent` | HALAgent and Android control-plane capability |
| `android.gpubridge` | VirGL rendering and shared memory |
| `android.termux-x11` | Termux:X11 display endpoint |
| `vendor.mediatek.venc` | MediaTek V4L2 VENC and multimedia DMA heap primitives |
| `device.blackview.n6000.lsa-video` | H.264 encoding, video tap, device optimization marker |

Examples of consumer independence:

- `sensors.fuse-iio` requires sensor bus, private devices, FUSE, sockets, and a chroot. It never tests model, vendor, or DeviceNamespace backend ID.
- `video.encode.lsa` requires H.264 encode and video-tap capabilities. It has no N6000 or MediaTek condition.
- `gpu.virgl` requires rendering and shared-memory capabilities, not a phone identity.
- `camera.android-mjpeg` and `location.android-gpsd` require generic Capture capabilities, not HALAgent, Android model, vendor, or device identity.
- `audio.aaudio-halaudio` requires generic AAudio/Pulse capabilities and publishes Linux Pulse/ALSA plus `capability.audio.spec-negotiated`; it never tests N6000 or MediaTek identity.

Providers may use device identity only to enable a candidate. The N6000 provider additionally requires the MediaTek primitive provider and probes its canonical GPU-tap source, video launcher, control client, and device nodes before publishing its capabilities. The generic VideoEncode module then consumes only H.264/video-tap capabilities.

The framework writes `architecture.tsv` and `binaries.tsv` beside the other runtime reports. A registered prebuilt artifact is marked `AVAILABLE` only when its detected ELF architecture matches its declared expected architecture and the relevant target userspace. A missing or mismatched artifact makes that backend `UNSUPPORTED`; it does not abort global startup. The N6000 H.264 asset is therefore explicitly an arm64/rootfs-arm64 device-provider requirement, not a global ARM64 assumption.

`lsectl containment [candidate-pid]` is a separate security qualification, not
a backend selector. It records whether a candidate runtime can safely offer
generic Linux root operations. Its `containment.tsv` summary is accompanied by
the exact mounts and inherited descriptors in `containment-mounts.tsv` and
`containment-fds.tsv`. A failed qualification never disables ordinary LSA
providers; it prevents a device from being described as safe for generic
`sudo`, package transactions, or privileged D-Bus activation.
