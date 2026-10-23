# 1.4.1.8#CoreCompat

`1.4.1.8#CoreCompat` is the first Core Compatibility release after
`1.3.1.7SWC#CoreWireless`.

The Core Wireless release established the capability-driven LSA architecture:
providers publish what Android can actually offer, modules select a backend,
and Linux receives the result through a normal or normal-like interface.

This release applies that architecture to the parts of a Linux desktop that
must work together before the project can be useful as more than a framework:
display, desktop session ownership, audio input and output, camera capture and
recording, location, sensors, storage, private device nodes, D-Bus, graphics,
and safe handling of the Android `nosuid` boundary.

The important change is that the matrix is now result-led. A provider existing
in source, or a backend reaching `RUNNING`, is not recorded as a working feature
until a Linux-facing client has exercised it. A failure is kept in the matrix
instead of being hidden by a lower-tier fallback.

This release was developed and tested on the Blackview N6000 running Android
13 / API 33 / arm64. That is the reference device, not a claim that every
Android 8+ device already behaves the same way.

## Core Compatibility matrix

LSA now ships a compatibility matrix alongside the source. It separates:

- implemented provider/backend pairs;
- framework selection and lifecycle evidence;
- real Linux-facing data-plane evidence; and
- work that remains open.

The current N6000 ledger includes the following witnessed paths:

```text
Audio output       Android AAudio/HALAudio -> Linux Pulse AndroidSink -> speaker
Camera             Android Camera -> Linux V4L2 MJPEG -> ffmpeg
Recording          camera-record -> bounded H.264 MP4
Location           Android location -> GPSD TPV / no-fix TPV
Sensors            Android SensorManager -> FUSE IIO -> Linux IIO clients
Display            Termux:X11 -> LSA Shell on :0
VNC desktop        TigerVNC :1 -> LXDE / Openbox / panel
Storage            Android public-volume export and Debian NTFS ownership path
GPU                Android ANGLE/Mali -> VirGL/virpipe -> Linux OpenGL client
Video encode       N6000 DMA-BUF -> MediaTek V4L2 -> H.264
D-Bus              private suid clone -> system bus -> service activation
```

The full matrix remains the source of truth. It records failed fallback tests,
partial results, and device-specific evidence next to successful paths.

## Display and phone shell

The experimental LSA phone shell has moved out of the isolated development
session and onto the physical Termux:X11 display.

```text
Android-facing display       :0       LSA Shell, running as myuser
VNC development workspace    :1       LXDE, Openbox, and LXPanel
```

The real `:0` session is no longer a temporary LXDE desktop. It starts
`lsa-session`, hands ownership to `myuser`, uses the same LSA GPU, audio,
camera, and sensor environment as a normal application session, and starts
the custom phone-oriented shell.

The VNC desktop remains useful for inspecting a normal desktop environment
without taking over the physical phone display. A fresh `:1` server was tested
with LXDE, Openbox, LXPanel, and an X11 client.

Termux:X11 and TigerVNC do not authenticate the same way. TigerVNC creates a
root Xauthority cookie before its startup script runs. Termux:X11 can expose a
valid no-cookie display. `lsa-session` now transfers a cookie to `myuser` only
when one exists, and otherwise continues with the no-auth Termux:X11 session.
That prevents the old failure where a valid `:0` display could not start the
user shell because there was no root Xauthority entry to copy.


Termux:X11 can briefly report a transitional surface while Android attaches or
rotates the activity. The shell now watches for that size change and recreates
only its own fixed phone windows once the real surface is stable. This keeps the
status bar, home view, and navigator aligned to the physical display without
restarting applications or the rest of the LSA stack.

The shell includes the application library and home-screen pinning work from
this compatibility cycle:

- applications are discovered from standard desktop entries;
- the library shows application icons and names;
- applications can be added to the home screen;
- holding a home-screen application exposes a remove action; and
- the launcher terminal uses Bash so history, arrows, and Tab completion work.

## Audio

The normal audio route is back on the Android AAudio/HALAudio provider:

```text
Linux application
        ↓
PulseAudio AndroidSink / AndroidSource
        ↓
LSA Android audio provider
        ↓
Android audio routing
        ↓
built-in speaker, microphone, or Android Bluetooth route
```

A Linux Pulse tone reached the phone speaker through the default
`audio.aaudio-halaudio` backend. Firefox playback was also restored through
the Android side of the route. Microphone and output endpoints are visible to
ordinary Linux clients instead of requiring each application to talk to an LSA
command directly.

The release also keeps the fallback work honest. The following backends were
force-selected and given a real speaker test:

```text
android.opensles          -> audio.opensles             selected, no output
android.sox               -> audio.sox                 speaker output passed
android.pulse-proxy       -> audio.pulse-proxy         selected, no output
android.termux-api-audio  -> audio.termux-api           selected, no output
```

Those failures remain failures. The rejections were cleared after testing, so
normal selection returns to the AAudio/HALAudio path.

PulseAudio WebRTC echo cancellation is now wired as an LSA fallback. It creates
`LSAAecSource` and `LSAAecSink` from the normal Android source and sink, and
selects them as the Pulse defaults when the AEC policy is enabled. Android
native `AcousticEchoCanceler` is not claimed yet: it requires an Android-owned
recording session that the present capture provider does not own. A real
speaker/microphone voice-call echo result is still needed.

## Camera, recording, and location

Camera is no longer only a rough Android snapshot helper. The generic Camera
provider exposes an Android capture route in the form Linux software expects:

```text
Android Camera API
        ↓
LSA capture provider
        ↓
MJPEG stream / snapshot endpoint
        ↓
Linux V4L2 compatibility path
        ↓
ffmpeg and normal V4L2 clients
```

A Linux `ffmpeg` V4L2 client captured three distinct `960x1280` MJPEG frames.
The recording path wrote a decodable bounded H.264 MP4 from the same camera
route. The direct Android-MJPEG fallback was also force-tested with a real JPEG
snapshot and decodable MP4.

Location now behaves better when no live fix is available. A GPSD client no
longer connects successfully and then receives silence. Active location
returned a mode-3 TPV. Inactive location returns a valid mode-1 no-fix TPV so
navigation clients can distinguish “no current fix” from a dead provider.

The remaining camera work is continuous native Camera2 capture, restart and
route tests, and broader graphical camera-application testing.

## Sensors and private devices

The SensorBus-to-IIO route is now treated as a normal Linux compatibility
surface rather than a demo service.

```text
Android SensorManager
        ↓
LSA SensorBus
        ↓
FUSE IIO registry and sysfs
        ↓
/dev/iio:* compatibility
        ↓
iio-sensor-proxy and Linux sensor clients
```

Native IIO devices are exposed, an accelerometer buffer delivered real bytes,
and the `iio-sensor-proxy` launcher now points at the installed
`LSASensorProxy.py` location. The previous launcher path referred to the wrong
directory.

The private device namespace also now explicitly preserves public `/dev/pts`.
A `myuser` pseudoterminal was allocated and reopened through the normal Linux
path. This protects the Android host `/dev` from being used as the Debian
namespace while keeping SSH, terminals, and interactive shells functional.

## Storage and removable USB media

Removable storage has an ownership model instead of a single mount rule.

```text
Android-recognized public volume
        ↓
Android / vold owns the filesystem
        ↓
exported into Debian at /media/android
        ↓
visible to both Android and Debian

Android-rejected filesystem, such as NTFS
        ↓
Debian owns the filesystem through ntfs-3g
        ↓
mounted only in Debian at /media/debian
```

The N6000 tested an Android-rejected NTFS USB volume mounted read/write in
Debian at `/media/debian/MEOW-50561161561148DC`. The Android public-volume
export implementation is present, but it remains marked as needing a witnessed
Android-mounted removable-media test and eject/reconnect coverage.

This avoids pretending that Android and Debian can both independently mount
and modify the same filesystem. Android-owned media remains Android-owned;
Debian can still see it through the exported path. A filesystem Android does
not claim can be handled by Debian without trying to teach Android what NTFS
is.

## GPU, Vulkan, and video encode

The generic graphics route is still OpenGL through the Android GPU bridge:

```text
Linux OpenGL client
        ↓
Mesa virpipe / VirGL
        ↓
VTEST socket
        ↓
Android ANGLE / Mali
```

`glxgears` completed through the bridge. The GPU policy is injected into normal
Linux sessions, so an application aimed at display `:0` inherits the intended
VirGL environment instead of depending on which terminal launched it.

Vulkan is deliberately not advertised. The experimental Venus VTEST route
reaches a VirtIO ring watchdog on the N6000:

```text
MESA-VIRTIO: stuck in ring seqno wait
```

It is not enabled as a backend. It needs a real client/server protocol fix,
not a release note that calls a stalled renderer “Vulkan support.”

Dolphin Emulator exposed a separate OpenGL limitation. Its VirGL path requires
`GL_EXT_clip_cull_distance`, which the current phone bridge does not expose.
The installed wrapper falls back to Mesa rather than leaving `DISPLAY=:0
dolphin-emu` to crash. That is a compatibility guard, not hardware-accelerated
Dolphin support.

The N6000-specific MediaTek encoder remains a separate optional provider. A
`1920x1080` DMA-BUF workload produced `12,390` H.264 bytes through the device
route. It is still explicitly device-specific and does not imply generic
MediaTek, generic Android H.264, or H.265 support.

## D-Bus, sudo, and the Android nosuid boundary

Android-backed Debian rootfs mounts commonly inherit `nosuid`. That makes a
root-owned mode-4755 `/usr/bin/sudo` look correct but fail to gain an effective
UID of zero. The same condition breaks D-Bus setuid activation helpers.

LSA now treats those as two different problems.

System D-Bus runs in its own fixed-purpose private `suid` rootfs clone. The
normal desktop remains `nosuid`. A system bus round trip and PackageKit service
activation completed through that clone.

Generic sudo cannot be made safe merely by remounting the whole Android-backed
rootfs `suid`. On phones without usable user namespaces, doing that could allow
a normal Debian user to become Android-host root. CoreCompat does not weaken the
normal desktop mount to make `sudo` look familiar.

An explicit development escape hatch exists for operators who knowingly accept
that risk. The `sudo` wrapper displays the warning and requires the exact
acknowledgement:

```text
I WILL NOT BE STOPPED
```

Only the approved command receives a temporary disposable `suid` clone. The
normal desktop rootfs remains `nosuid`. This makes package work possible on
restricted devices, but it is not a containment boundary and is not described
as safe sudo isolation. LSA providers remain the preferred path for normal
hardware operations.

## Packaging, source, and release evidence

LSADeploy is now versioned as:

```text
1.4.1.8#CoreCompat
```

The package contains the current RootStart and NonRootStart payloads, Android
support applications, architecture helpers, hashes, ownership policy, source
provenance, and corresponding LSA-X11 source material.

A public source tree accompanies this release. It contains the canonical LSA
source, payload inputs, compatibility matrix, release checklist, and build
notes. Local SSH/deployment helpers, workstation paths, runtime files, logs,
sockets, caches, and device credentials are not part of the public tree.

The release builder still creates Debian for the target architecture with
debootstrap instead of shipping one prebuilt rootfs. Normal deployment remains:

```sh
./deploy.sh
```

Framework-only probing remains available with:

```sh
./deploy.sh framework-only
```

And interrupted rootfs provisioning can be resumed with:

```sh
./deploy.sh resume-rootfs
```

## What this release does not claim

CoreCompat does not claim that Android 8+ hardware is solved universally. It
does not claim working Venus/Vulkan, hardware-accelerated Dolphin, native
Android AEC, generic USB ownership coverage, every camera application, or the
advanced wireless work from the roadmap.

The direction is still the same: install generic LSA on a challenger device,
record the actual provider and application failures, then turn repeated
problems into generic adapters where possible. A one-phone patch is useful for
investigation, but it is not the project’s definition of compatibility.
