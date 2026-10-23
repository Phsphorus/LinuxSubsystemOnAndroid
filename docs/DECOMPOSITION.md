# Full decomposition ownership map

Canonical runtime source is `source/`. Runtime payloads are generated from it. Keep local investigation output, device logs, and recoverable copies outside the repository.

## Completed ownership transfers

| Responsibility | Owner now | Classification | Linux-facing result |
|---|---|---|---|
| Rootfs core mounts | `Modules/CoreChroot/implementation/mounts.sh` | Android generic module | Bootable Linux mount namespace |
| Private `/dev`, host read-through, and private shm | `Modules/DeviceNamespace/implementation/` | Android generic module | Linux `/dev`, `/dev/.host`, `/dev/shm` |
| Generic Linux FUSE capability | `Modules/FUSE/implementation/` | Generic Linux module consuming DeviceNamespace's `/dev/fuse` | Standard Linux `/dev/fuse`; individual mounts remain component-owned |
| Linux system D-Bus | `Modules/DBus/implementation/` | Generic Linux module | Standard system-bus socket; only module-owned daemon PIDs are stopped |
| Shared and removable Android storage | `Modules/Storage/implementation/android-shared.sh` | Android generic module | Linux shared-storage mount; vold-owned public volume exports; NTFS-only Debian fallback mount |
| Android SensorManager acquisition | `NonRootStart/Services/HALSensorBus` | Android generic provider; stays Termux-user-owned | SensorBus TCP contract |
| Sensor registry, FUSE IIO overlay, stream/state/event brokers, ioctl shim | `Modules/Sensors/implementation/` | Android generic module | Linux IIO sysfs, device stream, state and event interfaces |
| Android Camera API and Android location acquisition | `NonRootStart/Providers/Android/Capture/` | Android generic provider; Termux-user-owned | Loopback MJPEG/snapshot and GPSD JSON endpoints |
| Camera and location activation | `Modules/Camera/android-mjpeg.backend`, `Modules/Location/android-gpsd.backend` | Android generic module backends | `capability.camera.linux` and `capability.location.linux` |
| Android AAudio acquisition and output sink | `NonRootStart/Providers/Android/Audio/` | Android generic provider; Termux-user-owned | AAudio microphone and negotiated raw-PCM output endpoint |
| Linux audio consumer and rootfs injection | `Modules/Audio/implementation/` | Android generic module | Standard Linux PulseAudio/ALSA endpoint with a negotiated Android sink |
| Generic VirGL/ANGLE bridge | `NonRootStart/Providers/Android/GPUBridge` plus `Modules/GPU/implementation` | Android generic provider/module; provider retains Termux UID ownership | Normal Linux VTEST render socket capability |
| Termux:X11 Android acquisition | `RootStart/Providers/Android/TermuxX11` plus `Modules/Display/implementation` | Android generic root provider/module | Normal Linux X11 socket and `DISPLAY` endpoint |
| MediaTek encoder primitives | `Providers/Vendors/MediaTek` descriptor | Vendor provider | Capability-only encoder primitives |
| Proven N6000 H.264 adapter | `NonRootStart/Providers/Devices/Blackview/N6000/VideoEncode` plus `Modules/VideoEncode/implementation` | Device provider plus generic Linux consumer module | Capability-gated H.264 GPU-tap encode only |

`ModChroot.sh` retains only the fixed dependency order required to construct the initial namespace. It sources component-owned implementation files; the historical `mounts.d` directory is no longer the architecture or a lifecycle owner.

## Explicit non-transfers in this pass

- The known MediaTek/N6000 H.264 route remains isolated and capability-gated. No H.265 capability is advertised.
- `androidctl` remains a control-plane client for lifecycle, modes, and diagnostics. It is not the Camera or Location data API.

## Runtime validation boundary

The live N6000 cycle on 2026-09-05 confirmed the module-owned SensorBus-to-IIO path with two native IIO devices and twenty synthetic devices. It also read a Linux light state value, completed an event-broker handshake, and read 64 bytes from the normal Linux `/dev/iio:device2` stream. The Camera provider served a snapshot and the Location provider returned a mode-3 GPSD TPV without requiring a Linux application to invoke `androidctl`.

The same device accepted a generic Android Audio provider request for `s16le`, two channels, and `44100 Hz`, derived from the actual Linux `AndroidSink` sample specification. The former fixed `48 kHz` command is only a conservative provider fallback when no consumer supplies a negotiated spec.

The N6000 transfer was validated with the module-owned `/usr/local/bin/lsa-h264-encode` consumer and a 1920x1080 Linux VirGL workload. The device provider compiled the transferred GPU tap, published its video socket, and produced a 12,390-byte H.264 stream through the MediaTek V4L2 path. Stopping the backend restored the ordinary generic VirGL socket; no Android-specific command is required by the Linux consumer.
