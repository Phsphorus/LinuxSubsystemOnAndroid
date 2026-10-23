# Backend policy

Backend IDs are stable. Public tiers are module-local presentation; priorities choose candidates. `AVAILABLE`, `UNSUPPORTED`, and `ERROR` are support states. `STOPPED`, `STARTING`, `RUNNING`, `DEGRADED`, and `FAILED` are runtime states.

Per-device, witnessed results are recorded in [Compatibility matrix](COMPATIBILITY_MATRIX.md).

Selection policy is a separate axis. An administrator can reject a backend whose probe is still `AVAILABLE`; it is reported as `REJECTED BY USER`, never relabeled `UNSUPPORTED`. The selector then considers the next accepted candidate. Rejections are durable normal-runtime configuration in `RootStart/Services/ModChroot/state/backend-rejections.tsv` (directory mode `0700`, ledger mode `0600`) and survive ordinary LSA restarts.

| Module | Backend ID | Tier | Priority | Implementation ownership |
|---|---|---:|---:|---|
| CoreChroot | `core.chroot` | A | 90000 | `Modules/CoreChroot/implementation` |
| DeviceNamespace | `device.private-dev` | B | 89000 | `Modules/DeviceNamespace/implementation` |
| Storage | `storage.android-shared` | A | 88000 | Android shared-storage bind plus vold-controlled Android/Debian removable-volume handoff in `Modules/Storage/implementation` |
| Storage | `storage.termux-shared` | Z | 0 | Direct module-owned bind of normal Termux shared storage; only selected when accepted higher candidates are unavailable or rejected |
| D-Bus | `dbus.system` | C | 81000 | Direct `Modules/DBus/implementation` system-bus lifecycle; on `nosuid` rootfses, its fixed-purpose launcher uses a private `suid` clone while external buses are never stopped |
| Display | `display.termux-x11` | C | 80000 | `RootStart/Providers/Android/TermuxX11` plus direct `Modules/Display/implementation` Linux-socket lifecycle |
| GPU | `gpu.virgl` | A | 90000 | `Providers/Android/GPUBridge` Termux-user provider plus direct `Modules/GPU/implementation` Linux-socket lifecycle |
| VideoEncode | `video.encode.lsa` | A | 100000 | Direct `Modules/VideoEncode/implementation` Linux H.264 consumer; N6000 provider owns Termux-UID video-mode activation |
| Audio | `audio.aaudio-halaudio` | A | 90000 | `Providers/Android/Audio` plus direct `Modules/Audio/implementation` lifecycle |
| Audio | `audio.opensles` | B | 80000 | `Providers/Android/Audio` OpenSL ES sink bridge plus the module-owned Linux Pulse/ALSA consumer |
| Audio | `audio.sox` | C | 70000 | `Providers/Android/Audio` Termux SoX raw-PCM bridge plus the module-owned Linux Pulse/ALSA consumer |
| Audio | `audio.pulse-proxy` | D | 60000 | `Providers/Android/Audio` Termux PulseAudio proxy bridge plus the module-owned Linux Pulse/ALSA consumer |
| Audio | `audio.termux-api` | Z | 0 | `Providers/Android/Audio` buffered Termux:API media-player bridge plus the module-owned Linux Pulse/ALSA consumer |
| Camera | `camera.v4l2-mjpeg` | B | 95000 | `Providers/Android/Capture` plus the module-owned `/dev/video0` and V4L2 compatibility layer |
| Camera | `camera.android-mjpeg` | C | 90000 | Android Capture loopback MJPEG fallback |
| Location | `location.android-gpsd` | C | 90000 | `Providers/Android/Capture` plus direct Location backend callback |
| Sensors | `sensors.fuse-iio` | D | 7000 | `Modules/Sensors/implementation` plus direct lifecycle callback |
| FUSE | `fuse.userspace` | D | 6000 | Direct `Modules/FUSE/implementation` Linux `/dev/fuse` lifecycle; individual FUSE mounts remain their module owners |
| Wireless | `wireless.host-interface` | A | 90000 | Direct `Modules/Wireless/implementation` lifecycle over a safe Linux-visible Android host interface |
| Wireless | `wireless.termux-uplink` | Z | 0 | Direct `Modules/Wireless/implementation` Termux-compatible Android uplink fallback for normal Linux sockets |

The selector evaluates requires/provides capabilities, never another module's tier. A candidate returning `ERROR` or `UNSUPPORTED` allows the next lower-priority candidate to be considered. No letter tier is invented to fill a gap.

## Administrative backend policy

Run `lsectl` inside the active ModChroot mount namespace. Its generic controls apply to every registered backend ID:

```sh
lsectl report --verbose
lsectl reject storage.android-shared "exercise Termux Z fallback"
lsectl accept storage.android-shared
lsectl rejections
```

`disable` is an alias for `reject`; `enable` is an alias for `accept`. If the rejected backend was running, `lsectl` stops it, refreshes selection, and starts the selected replacement. Rejecting an optional stopped backend changes policy without unexpectedly starting hardware work. A rejected high-tier candidate remains diagnostically visible as `AVAILABLE` plus `REJECTED BY USER` in the verbose report.

The N6000 validation rejected `storage.android-shared`, selected and ran `storage.termux-shared` at Tier Z, then restored Tier A. The same rejection survived a controlled RootStart restart before being explicitly cleared.

No backend uses an external-lifecycle compatibility callback. Audio, Display, D-Bus, FUSE, GPU, VideoEncode, Camera, Location, Sensors, CoreChroot, DeviceNamespace, and Storage all have direct module/provider lifecycle ownership.

The D-Bus lifecycle validates the package-owned launch helper before it uses an
existing or newly started bus. If Android-side rootfs handling changed that
helper's ownership, it restores Debian's `root:messagebus` mode `4754`. When
the normal Android-backed rootfs is `nosuid`, the lifecycle runs only the fixed
`dbus-daemon --system --nofork --nopidfile` process in a private `suid` clone
that copies the same rootfs child mounts. The normal desktop rootfs remains
`nosuid`; standard D-Bus policy still decides which registered service may be
activated, and this is not a caller-controlled command launcher.

The private-device lifecycle mounts host `devpts` again at public `/dev/pts`
after it covers `/dev` with its private tmpfs. The host read-through remains at
`/dev/.host`; normal Linux programs receive the conventional public pty path.

The selected Camera Tier B backend supports V4L2 read and mmap capture through
the Android MJPEG endpoint.  Its next-frame endpoint makes each V4L2 dequeue
wait for a newer Android capture generation, rather than returning a tight loop
of stale JPEGs.  Android acquisition currently uses `termux-camera-photo`, so
it is snapshot-based. `camera-record output.mp4` writes variable-frame-rate
H.264 with arrival timestamps rather than claiming a fixed camera FPS. It is a
compatibility path, not a claim of a native Android Camera2 continuous-capture
driver.
Set `LSA_CAMERA_RECORD_SECONDS` to a positive duration when a bounded recording
should be finalized without relying on an external signal.
The provider caps each source JPEG's long edge at 1280 pixels by default before
it reaches Linux. Recordings cap their long edge at 1920 pixels by default and
never upscale a smaller source; set `LSA_CAMERA_RECORD_MAX_DIMENSION` to change
that recording limit.
