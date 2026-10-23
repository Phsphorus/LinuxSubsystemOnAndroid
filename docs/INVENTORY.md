# LSA inventory and classification

Audit basis: canonical source in `LSALIVE`, the retained first-pass evidence under `Terp\tmp`, and a controlled Blackview N6000 lifecycle capture on 2026-09-05.

| Area | Actual implementation owner | Classification | Capability boundary |
|---|---|---|---|
| `RootStart/RST.sh` | Root session coordinator | Runtime | Android-root lifecycle and Termux PTY only; see legacy ledger. |
| `Modules/CoreChroot/implementation` | Core rootfs bind/proc/sys mounts | ANDROID_GENERIC | `capability.linux.chroot` |
| `Modules/DeviceNamespace/implementation` | private tmpfs `/dev`, Android read-through, private shm | ANDROID_GENERIC | `capability.device.private`, `capability.device.host-view` |
| `Modules/FUSE/implementation` | generic Linux FUSE endpoint lifecycle, independent of a particular mount | GENERIC module | `capability.linux.fuse` |
| `Modules/DBus/implementation` | generic Linux system D-Bus lifecycle with owned-PID protection | GENERIC module | `capability.dbus.system` |
| `Modules/Storage/implementation` | Android shared-storage bind, Android public-volume export, and NTFS-only Debian ownership handoff; plus Termux shared-storage baseline | ANDROID_GENERIC module with GENERIC Tier Z fallback | `capability.storage.shared` |
| `Framework/architecture.sh` | Android ABI, kernel, Termux userspace, rootfs, and artifact-ELF detection | GENERIC framework | `capability.architecture.detected` and per-axis architecture capabilities |
| `NonRootStart/Services/HALSensorBus` | Termux-user Android SensorManager bridge | ANDROID_GENERIC provider | `capability.sensorbus`; it remains Termux-owned. |
| `Modules/Sensors/implementation` | registry, FUSE IIO overlay, stream/state/event brokers, scoped ioctl shim | ANDROID_GENERIC module | `capability.linux.iio`, `capability.linux.iio-events`, `capability.linux.sensorproxy` |
| `NonRootStart/Providers/Android/Capture` | Termux-user Camera API and Location API acquisition | ANDROID_GENERIC provider | Camera MJPEG/snapshot and GPSD; not an `androidctl` data API. |
| `Modules/Camera` and `Modules/Location` | Linux-facing activation of Capture endpoints | ANDROID_GENERIC modules | `capability.camera.linux`, `capability.location.linux` |
| `NonRootStart/Providers/Android/Audio` plus `Modules/Audio/implementation` | Termux-user AAudio microphone/output provider and Linux Pulse/ALSA consumer | ANDROID_GENERIC provider/module | `capability.audio.linux`, `capability.audio.alsa-pulse`, `capability.audio.spec-negotiated` |
| `NonRootStart/Providers/Android/GPUBridge` plus `Modules/GPU/implementation` | Termux-user VirGL server over ANGLE/Vulkan and Linux mounted-socket consumer | ANDROID_GENERIC provider/module | `capability.gpu.render.virgl`, `capability.gpu.shared-memory`, `capability.gpu.linux-render` |
| `RootStart/Providers/Android/TermuxX11` plus `Modules/Display/implementation` | Android app-process X server and Linux X11-socket consumer | ANDROID_GENERIC root provider/module | `capability.display.termux-x11`, `capability.display.linux` |
| `RootStart/Services/halagent` | Root Android control and remaining audio staging | ANDROID_GENERIC, transitional control plane | `capability.android.control`; no canonical camera/location data code remains. |
| MediaTek V4L2/DMA primitives | `Providers/Vendors/MediaTek` | VENDOR_SPECIFIC | `capability.vendor.mediatek.*` |
| Proven N6000 H.264 adapter | `NonRootStart/Providers/Devices/Blackview/N6000/VideoEncode` plus `Modules/VideoEncode/implementation` | DEVICE_SPECIFIC provider plus GENERIC consumer module | Capability-gated H.264 only; no H.265 claim. |
| rootfs `/usr/local/lib/lsa`, runtime sockets, generated shim | Injector and running providers | GENERATED or RUNTIME | Not canonical source. |
| `Workshop/` trees | Historical workspace | DEVELOPMENT/TEST | Intentionally untouched. |

The live N6000 was Android 13/API 33, Android ABI `arm64-v8a`, kernel/Termux `aarch64`, rootfs `arm64`, kernel `5.10.160-android12-9-00011-g62f5fae173d8-ab9750419`, SELinux permissive. The current controlled cycle selected the generic Camera, Location, and Sensors backends; N6000/MediaTek specialization remains confined to the optional H.264 provider path. The generic architecture detector does not infer any of these choices from the phone model.
