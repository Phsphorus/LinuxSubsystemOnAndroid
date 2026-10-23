# Compatibility matrix

This is a result ledger for LSA. A backend being present in source or selected by
the framework does not prove that an application can use the device. Each cell
records the strongest evidence actually obtained on the named device.

- **Implemented** means a registered provider/backend pair is in canonical source.
- **Probe/lifecycle** means the framework could select and run it.
- **Witnessed** means a real Linux-facing data path was exercised.
- A pass on one phone is never a portable support claim for every Android device.

## Blackview N6000 — Android 13 / API 33 / arm64

| Module | Provider -> backend | Evidence | Result | Still needed |
|---|---|---|---|---|
| Audio | `android.halaudio` -> `audio.aaudio-halaudio` | Linux Pulse `AndroidSink` tone reached the phone speaker | **PASS** | Route-change and clean-restart tests |
| Audio | `android.opensles` -> `audio.opensles` | Selected and running; normal Linux `AndroidSink` tone via the normal Linux-user client | **FAIL** — no speaker output | Diagnose OpenSL route/playback |
| Audio | `android.sox` -> `audio.sox` | Selected and running; normal Linux `AndroidSink` tone | **PASS** | Route-change and clean-restart tests |
| Audio | `android.pulse-proxy` -> `audio.pulse-proxy` | Selected and running; normal Linux `AndroidSink` tone | **FAIL** — no speaker output | Diagnose proxy route/playback |
| Audio | `android.termux-api-audio` -> `audio.termux-api` | Selected and running; normal Linux tone completed through the buffered Android media-player backend | **FAIL** — no speaker output | Diagnose media-player route/playback |
| Audio AEC | `AndroidSource` + `AndroidSink` -> PulseAudio `module-echo-cancel` (WebRTC) | `LSAAecSource` and `LSAAecSink` were created, selected as Pulse defaults, and an AEC-routed 880 Hz tone completed | **IMPLEMENTED** | Voice-call echo result on real speaker/microphone acoustics |
| Camera | `android.capture` -> `camera.v4l2-mjpeg` | A standard Linux `ffmpeg` V4L2 client captured three distinct 960x1280 MJPEG frames (source PTS 0.000, 2.343, 5.369); `camera-record` wrote decodable 960x1280 VFR H.264 | **PASS** | Native continuous Camera2 capture and wider graphical camera-app testing |
| Camera | `android.capture` -> `camera.android-mjpeg` | Forced fallback returned a 6.6 MB JPEG snapshot and a decodable bounded H.264 MP4 | **PASS** | Restart, route, and broader application tests |
| Location | `android.capture` -> `location.android-gpsd` | Linux GPSD returned a mode-3 TPV while active; an inactive `WATCH` now receives a valid no-fix `TPV` mode 1 instead of silence | **PASS** | Navigation-client and reconnect tests |
| Sensors | `android.sensorbus` -> `sensors.fuse-iio` | Linux IIO devices exposed; accelerometer buffer delivered bytes; the `iio-sensor-proxy` compatibility launcher resolves the installed LSA implementation | **PASS** | Real-device sensor breadth and application tests |
| Display | `android.termux-x11` -> `display.termux-x11` | Linux `xdpyinfo` connected and LSA Shell completed its `myuser` handoff on physical Termux:X11 `:0`; no Xauthority cookie is required by this server. A fresh VNC `:1` server started LXDE, Openbox, and its panel, then accepted an X11 client. | **PASS** | Cold-start and wider desktop-application tests |
| GPU | `android.gpubridge` -> `gpu.virgl` | Linux `glxgears` completed 401 frames in five seconds through the Android ANGLE/Mali-backed VirGL path | **PASS, OpenGL** | Broader OpenGL application coverage |
| GPU | `android.gpubridge` -> `gpu.venus` | The experimental Venus VTEST server reaches a VirtIO ring watchdog (`stuck in ring seqno wait`) on this phone | **NOT IMPLEMENTED** | Fix the server/client protocol path before exposing Vulkan |
| GPU application compatibility | Dolphin Emulator wrapper | Dolphin's VirGL OpenGL path needs `GL_EXT_clip_cull_distance`, which the phone bridge does not expose. The wrapper deliberately selects the Mesa fallback instead of crashing. | **PARTIAL** | A working VirGL extension path or a separate Vulkan solution |
| Video encode | `vendor.mediatek.venc` + `device.blackview.n6000.lsa-video` -> `video.encode.lsa` | 1920x1080 DMA-BUF produced 12,390 H.264 bytes | **PASS, device-specific** | Repeatability, app integration, H.265 scope |
| Wireless | `android.wireless-host` -> `wireless.host-interface` | Linux-visible host interface and controlled temporary interface qualification | **PARTIAL** | AP/P2P owner, peer tests, and any monitor-mode work |
| Wireless | `android.termux` -> `wireless.termux-uplink` | Implemented ultimate sockets fallback | **NOT YET WITNESSED** | Force-select plus socket/restart test |
| Storage | `android.rootfs` -> `storage.android-shared` | Normal shared-storage path selected; Android-rejected `MEOW` NTFS USB (`public:8,49`) mounted read-write only in Debian at `/media/debian/MEOW-50561161561148DC`. Android-owned public-volume export is implemented but not yet witnessed with a mounted removable filesystem. | **PASS** | Android-mounted removable-media and eject/reconnect matrix |
| Device namespace | `android.rootfs` -> `device.private-dev` | Private `/dev`, FUSE, and public `/dev/pts` mounted; `myuser` allocated and reopened `/dev/pts/48` | **PASS** | USB ownership scenarios |
| D-Bus | Linux chroot -> `dbus.system` | The desktop rootfs remains `nosuid`. LSA started the system bus in its own private `suid` rootfs clone; `ListNames` worked and `StartServiceByName(org.freedesktop.PackageKit)` returned `uint32 1`, with the service claiming its name. | **PASS** | Broader service and restart coverage |
| FUSE | `android.fuse` -> `fuse.userspace` | FUSE lifecycle supports the sensor IIO mount | **PASS** | Independent mount and recovery test |

Audio was returned to `audio.aaudio-halaudio` after the fallback tests. The
temporary backend rejections were cleared, so normal automatic selection again
chooses Tier A.

Audio AEC defaults to the Debian PulseAudio WebRTC fallback. Android-native
AEC remains unavailable until the Android capture provider owns an
`AudioRecord` session to which `AcousticEchoCanceler` can attach. The policy is
set in `config/config.sh` as `LSA_AUDIO_AEC_BACKEND`: `auto`, `pulseaudio`,
`android`, or `off`. Explicit `android` currently leaves the raw endpoints in
place rather than claiming an effect that does not exist.

## Recording a new device

Use this sequence on a challenger device:

1. Install and run unmodified generic LSA.
2. Save the framework report, provider/backend diagnostics, and application-level evidence.
3. Record failures with the affected Linux interface and the reason in the logs.
4. Look for a generic adapter before adding a device patch.
5. If a local patch is needed to keep investigating, record it as device-specific rather than presenting it as the generic answer.

A test belongs in this matrix only after it has an observable result. “Installed,”
“selected,” and “running” are useful diagnostics, but they are not application
compatibility claims.
