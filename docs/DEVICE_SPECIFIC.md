# Device and vendor boundaries

The proven Blackview N6000/MediaTek video path is now owned in canonical source, rather than by an active external project:

- `source/NonRootStart/Providers/Devices/Blackview/N6000/VideoEncode/` owns the Termux-UID manager, GPU-tap source, video-mode VirGL launcher, and short control endpoint.
- `source/RootStart/Services/ModChroot/LSA/Modules/VideoEncode/implementation/` owns injection and the normal Linux H.264 consumer command, `/usr/local/bin/lsa-h264-encode`.
- `source/RootStart/Services/ModChroot/LSA/Providers/Devices/Blackview/N6000/lsa-video.provider` owns device-specific probing and capability publication.

The module-owned consumer asset is the verified arm64 binary imported from the known-good device implementation because the available historical C source was incomplete. Its canonical SHA-256 is `8d73ecfb25ff21ec7d0143cc7f4cacfadcd1b0e24424d2384c3645b77ee2cdc1`; import evidence is retained under `Terp/tmp/evidence/device-asset-import/`. This preserves the working implementation without representing an incomplete source file as buildable source. The architecture framework registers the artifact and requires both its detected ELF architecture and the target Linux rootfs architecture to be `arm64`; a mismatch or missing asset makes this optional backend `UNSUPPORTED` rather than breaking global startup.

The boundary is deliberately two-stage:

1. `vendor.mediatek.venc` is enabled only by actual V4L2 encoder and MediaTek DMA-heap nodes. It provides vendor primitives, not an application-facing result.
2. `device.blackview.n6000.lsa-video` checks Blackview/N6000 identity, canonical provider assets, and those vendor nodes. Only then does it publish H.264/video-tap capability.

`video.encode.lsa` remains generic and consumes those capabilities. It neither checks `N6000` nor `MediaTek`; it asks the device provider to enter video mode through its control contract. If either provider is unavailable or errors, this backend is not selected and a future generic alternative may be selected.

The N6000 test used a 1920x1080 Linux VirGL workload and the normal Linux consumer. It transported a DMA-BUF through the GPU tap and MediaTek V4L2 encoder, produced 12,390 H.264 bytes, then restored the generic VirGL provider when stopped. This is evidence for H.264 on this device only. It does not claim H.265, generic MediaTek compatibility, all V4L2 encoders, or all Android devices.

The retired external project is preserved, with no current caller, at `/data/local/RootStart/tmp/backups/decomposition-video/20260906T0952Z/lsagpumediatek`. It is a recoverable phone temporary backup, not canonical source or an active runtime dependency.
