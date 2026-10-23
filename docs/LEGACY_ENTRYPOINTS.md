# Remaining legacy and transitional entrypoints

This is the required ledger for every surviving compatibility boundary in canonical source. A row marked **intentional entrypoint** is retained by design, not by an untraced historical dependency.

| Path | Current caller(s) | Why it remains | Exact removal condition |
|---|---|---|---|
| `source/RootStart/RST.sh` | User/root launcher and deployment lifecycle | **Intentional entrypoint.** Maintains the Android-root process and Termux pseudo-terminal needed by the long-lived chroot session. | Replace only when a root lifecycle supervisor provides the same PTY, signal, service ordering, and teardown semantics. |
| `source/RootStart/Services/ModChroot/ModChroot.sh` | `RST.sh` | Thin root coordinator. It provides the dependency order, hook phases, and interactive chroot ownership; component implementation is no longer in this file. | A component graph supervisor can construct the namespace and own the interactive session with no fixed shell coordinator. |
| `source/RootStart/Services/ModChroot/LSA/Framework/compat.sh` | Framework descriptor callbacks | Small generic PID, mount, and chroot-path query helpers only. The external-lifecycle helpers were removed after all backends gained direct ownership. | Replace the shell descriptor ABI with an equivalent framework utility API and migrate every remaining caller. |
| `source/RootStart/Services/halagent/` | `RST.sh` service scan and `androidctl` control requests | Root Android control service for shared/full mode and remaining audio-side control. Camera and location data responsibility has been removed from canonical source. | Split its remaining control responsibilities into owning providers and remove the service scan entry only after no control-plane command needs it. |
| `source/RootStart/Services/ModChroot/hooks.d/post-network/64-lsa-sensor-deps.sh` and `65-iio-sensor-proxy.sh` | `run_hooks post-network` | Thin rootfs package/provisioning bridge for the Debian compatibility launcher. The actual sensor implementation and lifecycle are module-owned. | Sensors module installation declares the package/diversion itself and no supported rootfs package requires the historical `iio-sensor-proxy` launcher path. |
| `source/RootStart/Services/halagent/androidctl` | Human/operator control-plane use | **Intentional control-plane client.** It starts, stops, configures, and diagnoses; it is no longer a Camera or Location data API. | No planned removal; retain while LSA has lifecycle/mode controls, or replace with an equivalent control-plane client. |
| `source/NonRootStart/Services/HALSensorBus/` | `NRS.sh`; Sensors provider contract | **Not a wrapper.** This is the Termux-UID Android SensorManager acquisition owner and must not be moved into root. | Only replace after a Termux-UID provider owns the same SensorBus protocol and stream/state/event semantics. |

## Retired legacy implementation record

| Path | Current caller(s) | Why it remains | Exact removal condition |
|---|---|---|---|
| `/data/local/RootStart/tmp/backups/decomposition-video/20260906T0952Z/lsagpumediatek` | None; audited before move | Recoverable 38-file historical copy of the former N6000 H.264 project. Its GPU tap, video launcher, and verified consumer asset are now owned by canonical N6000 provider/module paths. | The user elects to remove this phone-side temporary backup after retaining the final H.264 evidence. |

The former Camera HALAgent backend descriptor was removed from canonical source after the Android-generic capture provider was proven on the phone. A recoverable source copy is in `tmp/backups/20260905-205300`, and the deployed phone copy was moved to `/data/local/RootStart/tmp/backups/decomposition-camera/20260905T210200Z/` before the final in-namespace refresh.

The former Audio service locations (`Services/HALAudioS` and `lib/halaudio.sh`) were removed from canonical source after the provider/module transfer and live 44.1 kHz negotiated-sink validation. Recoverable source copies remain under `Terp/tmp/backups/20260905-211000`.

The former GPUBridge service container (`Services/gpubridge`) was removed after the generic Termux-user provider transfer. Its source backup is under `Terp/tmp/backups/20260906-015200`; the phone copy is backed up at `/data/local/RootStart/tmp/backups/decomposition-gpu/20260906T065220Z/`; its intentional historical Workshop content was retained at `source/NonRootStart/Workshop/GPUBridge-legacy-service/` and the corresponding phone Workshop location. The GPU module now has direct Linux-socket lifecycle/status callbacks and does not use the external-lifecycle compatibility helpers.

The former Termux:X11 service container (`RootStart/Services/termux-x11`) was removed after transfer to the Android-generic RootStart provider. A recoverable source copy is under `Terp/tmp/backups/20260906-020300`. The `display.termux-x11` backend now has direct Linux X11-socket lifecycle/status callbacks; only the RootStart provider may launch or stop `app_process`.

The former `/data/local/linux/root/lsagpumediatek` active project was moved only after a phone audit found no active caller or process reference. The canonical N6000 provider owns the Termux-UID manager, GPU tap source, and video-mode launcher; the VideoEncode module owns the injected Linux H.264 consumer. The device path was proven end-to-end before retirement and uses no `lsa_compat_external_*` helper.
