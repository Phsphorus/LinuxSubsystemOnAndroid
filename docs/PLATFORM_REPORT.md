# LSA Platform Report

Live snapshot: 2026-09-06 11:06 CDT, after the portability-foundation changes, a clean Android-root RootStart restart, and an in-namespace framework refresh on the Blackview N6000. This is a runtime observation, not a portable support claim for every Android device.

```text
Android             13 / API 33
Android ABI         arm64-v8a (arm64)
Kernel architecture aarch64 (arm64)
Termux userspace    aarch64 (arm64)
Linux rootfs        arm64 (arm64)
Kernel              5.10.160-android12-9-00011-g62f5fae173d8-ab9750419
SELinux             Permissive

CoreChroot          TIER A / AVAILABLE / RUNNING  (core.chroot)
DeviceNamespace     TIER B / AVAILABLE / RUNNING  (device.private-dev)
Storage             TIER A / AVAILABLE / RUNNING  (storage.android-shared)
Display             TIER C / AVAILABLE / RUNNING  (display.termux-x11)
FUSE                TIER D / AVAILABLE / RUNNING  (fuse.userspace)
Sensors             TIER D / AVAILABLE / RUNNING  (sensors.fuse-iio)
Camera              TIER C / AVAILABLE / RUNNING  (camera.android-mjpeg)
Location            TIER C / AVAILABLE / RUNNING  (location.android-gpsd)
Audio               TIER A / AVAILABLE / RUNNING  (audio.aaudio-halaudio)
System D-Bus        TIER C / AVAILABLE / RUNNING  (dbus.system)
GPU                 TIER A / AVAILABLE / RUNNING  (gpu.virgl)
VideoEncode         TIER A / AVAILABLE / STOPPED  (video.encode.lsa)
  device provider   device.blackview.n6000.lsa-video
  scope             proven H.264 only
```

Selected provider state: generic Android Capture, Audio, SensorBus, rootfs, Termux:X11, FUSE, HALAgent, and GPUBridge were `AVAILABLE / RUNNING`. The MediaTek/N6000 video providers were supported but stopped after their focused test; neither status nor the proof claims H.265.

Focused data-plane evidence from the same cycle:

- Linux IIO exposed `iio:device0` through `iio:device21`: 2 native devices and 20 synthetic devices.
- The event broker accepted an `iio:device18` client handshake after the restart. A temporary standard IIO buffer enable on `iio:device2` delivered 64 accelerometer bytes and returned buffer/scan attributes to `0` afterward.
- `http://127.0.0.1:8765/snapshot.jpg` returned a non-empty image. The GPSD endpoint returned a mode-3 TPV. These are normal Linux-facing endpoints; Linux clients do not call `androidctl` to acquire the data.
- `AndroidSink` exposed `s16le 2ch 44100Hz` through standard PulseAudio. The Linux consumer requested that exact spec through the control plane; the Termux-user Android Audio provider logged `SINK started ... format=s16le rate=44100 channels=2`. This validates negotiation rather than a fixed 48 kHz path.
- The generic Termux-user GPUBridge provider published its VirGL socket at `NonRootStart/Providers/Android/GPUBridge/run/.virgl_test`; RootStart bind-mounted it at `/mnt/gpubridge`, and `lsectl start GPU` completed through the direct module callback. After the N6000 video test stopped, the provider returned to `mode=generic`, its video socket was absent, and a fresh Linux `glxgears` run completed 401 frames in five seconds (80.115 FPS).
- The generic root TermuxX11 provider published `X0` at the normal Linux `/tmp/.X11-unix/X0` endpoint; `lsectl start Display` completed through the direct module callback, and Linux `xdpyinfo -display :0` connected successfully.
- The generic D-Bus module now starts from the normal backend lifecycle using its exact `D-Bus` module identity. Linux `dbus-send --system` successfully called `org.freedesktop.DBus.ListNames` after the clean restart.
- The generic rejection ledger was exercised by rejecting the available Storage Tier A backend. Tier Z `storage.termux-shared` was selected and ran, including across a controlled restart; Tier A was then explicitly restored and the ledger is empty.
- The architecture inventory recorded 56 capabilities and an arm64 match for the optional N6000 H.264 artifact. That artifact condition is scoped to its device provider; it is not an assumption made by generic modules.
- The canonical N6000 VideoEncode provider compiled its GPU tap, activated video-mode VirGL, and the module-owned Linux `/usr/local/bin/lsa-h264-encode` consumed a 1920x1080 DMA-BUF. The MediaTek V4L2 path emitted 33- and 12,357-byte H.264 chunks (12,390 bytes total) before the backend restored generic GPU mode. The artifact and logs were preserved at `/data/local/RootStart/tmp/evidence/decomposition-video/20260906T1002Z/`.

`STOPPED` is a runtime state, not a support failure. The command below regenerates framework state in the active RootStart namespace:

```sh
/data/local/RootStart/Services/ModChroot/LSA/Framework/lsectl report --verbose
```

The former `camera.legacy-halagent` descriptor is absent from canonical source and was moved from the phone to a recoverable phone-side `tmp/backups` path before this final refresh.
