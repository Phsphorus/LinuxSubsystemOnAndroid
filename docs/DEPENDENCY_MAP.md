# Dependency map

```text
Android rootfs/mount/device primitives -> core.chroot -> device.private-dev
                                             |              |
Termux shared storage ----------------------> storage.termux-shared (Tier Z fallback)
Android SensorManager -> android.sensorbus --+--------------+-> sensors.fuse-iio -> Linux IIO
kernel FUSE -> android.fuse -----------------+              |

Termux AAudio -> android.halaudio -> audio.aaudio-halaudio -> Linux Pulse/ALSA
                                            -> negotiated format/rate/channels -> Android raw PCM sink
Termux VirGL/ANGLE -> android.gpubridge -> gpu.virgl -> Linux render

Android Camera API -> android.capture -> camera.v4l2-mjpeg -> Linux V4L2 MJPEG/read/mmap
                                          -> camera.android-mjpeg -> Linux MJPEG/snapshot fallback
Android Location API -> android.capture -> location.android-gpsd -> Linux GPSD

MediaTek nodes -> vendor.mediatek.venc -> N6000 Termux video provider -> module-owned Linux H.264 consumer
RootStart TermuxX11 provider -> android.termux-x11 -> display.termux-x11 -> Linux X11 socket / DISPLAY
HALAgent -> android.halagent -> Android control plane
Detected Android/kernel/Termux/rootfs architecture -> optional artifact/provider eligibility
```

Edges use provided capability names in descriptors, not backend or tier labels. The generic framework evaluates requirements, records unmet dependencies as `UNSUPPORTED`, records callback defects as `ERROR`, and preserves diagnostic reasons in `backends.tsv`.

Administrative policy is orthogonal to these edges: a user-rejected `AVAILABLE` backend remains visible as such, but its capability is not selected and a lower accepted candidate may provide the same contract.
