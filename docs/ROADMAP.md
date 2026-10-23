# LSA roadmap

LSA is meant to make a rooted Android phone usable as a Linux machine without
pretending Android vendor drivers are ordinary Linux drivers. Android already
knows how to talk to its own encrypted vendor blobs, camera HALs, audio HALs,
sensor HALs, GPU stack, and modem. LSA should ask Android for the useful
operation, then present the result at the Linux interface software already
expects: a camera device, an IIO sensor, a Pulse/ALSA device, an X11 display,
a GPSD endpoint, a network interface, and so on.

The target is a useful Linux environment on rooted Android 8 and newer
devices. It is not a promise that every phone exposes every raw hardware
feature. Each capability must be detected, selected, and tested on the device
in front of us. A missing capability should produce a clear `UNSUPPORTED`
result and let the rest of LSA keep working.

## What "done" means

LSA is ready for a public stable release when a new supported device can be
installed without hand-editing device-specific scripts, boots into a usable
Linux desktop or shell, and has a documented result for every major subsystem.
For a feature to count, an ordinary Linux application must exercise it. A
socket, process, or successful compile is not enough.

The core promises are:

- Linux applications use standard Linux-facing interfaces whenever one exists.
- Android-specific code stays behind a provider boundary.
- Device and vendor adapters are optional additions; generic consumers do not
  branch on a phone model.
- A higher-fidelity backend may fail or be unavailable without breaking a
  lower-fidelity usable fallback.
- Hardware claims carry device, Android version, and application evidence.
- LSA never changes a live radio, route, camera, or system service merely to
  make a status report look better.

## Project map

```text
LSA
├── 1. Lifecycle and safety
│   ├── RootStart and NonRootStart ownership
│   ├── Power, sleep, restart, teardown, and recovery
│   ├── Capability selection, diagnostics, and backend policy
│   └── Installer, upgrades, rollback, and security boundaries
├── 2. Linux environment
│   ├── Rootfs, mounts, storage, private /dev, FUSE, and D-Bus
│   ├── Display and desktop session
│   └── Application compatibility and packaging
├── 3. Media
│   ├── Audio output, microphone input, routing, and fallback backends
│   ├── Camera capture, V4L2 compatibility, and recording
│   └── Device-specific hardware video encoding
├── 4. Sensors and position
│   ├── SensorManager to IIO and sensor-proxy compatibility
│   └── Android location to GPSD
├── 5. Graphics and compute
│   ├── Generic Linux rendering
│   ├── Software fallback rendering
│   └── Vendor and device encode/render adapters
├── 6. Networking and radios
│   ├── Normal Linux sockets and host-interface visibility
│   ├── Peer-to-peer and ad-hoc networking
│   ├── Monitor mode and raw frame work
│   └── USB Ethernet and external NICs
├── 7. USB and Bluetooth
│   ├── Linux-owned USB peripherals
│   ├── Android-routed Bluetooth audio
│   └── Bluetooth input and ownership model (on hiatus)
├── 8. Device coverage
│   ├── Generic Android 8+ baseline
│   ├── Challenger-device testing
│   └── Vendor/device adapters where the generic path cannot work
└── 9. Release and collaboration
    ├── Reproducible packages and test evidence
    ├── Hardware support matrix
    ├── Issue templates and contributor guides
    └── Regular tested releases
```

## The work in front of us

### 1. Lifecycle and safety

This is the part that keeps a working phone from becoming a one-off demo.
Every provider needs one owner, a bounded startup, a status check that reflects
reality, and a teardown that only removes resources it created. Android power
management also belongs here: Termux, Termux:API, and Termux:X11 must remain
eligible to run when the screen turns off.

Done means a clean install, restart, screen-off period, provider crash, and
upgrade can all be tested without leaving duplicate services, stale sockets,
or a broken rootfs. Current work includes the bounded SensorBus readiness
wait, a NonRootStart singleton lock, and documented backend rejection.

### 2. Linux environment and ordinary applications

The rootfs, private `/dev`, FUSE, storage, D-Bus, display, and session setup
need to behave predictably before hardware compatibility matters. The goal is
that normal packages can be installed and launched without every application
needing a private LSA command.

The immediate work is a small application test suite: terminal tools, an X11
program, a browser, a file chooser, an audio player, a recorder, a V4L2 camera
client, an IIO client, and a GPSD client. A failure should identify the
missing Linux contract rather than being filed as "app does not work."

### 3. Audio

Audio output currently has AAudio/HALAudio as the preferred backend and four
registered fallback backends: OpenSL ES, SoX, Pulse proxy, and Termux:API.
The next step is not to invent more names. It is to force-select each backend
on real phones and test speaker output, wired/Bluetooth route changes, process
restart, and an ordinary Pulse/ALSA client.

Microphone input needs its own completion track. The test is a real Linux
recording device that Discord, a browser call, or `arecord` can open, followed
by a recorded-file and live-call check. Output sound does not prove input.

### 4. Camera and recording

The current generic camera route is Android snapshots exposed as loopback
MJPEG. The Tier B compatibility backend makes that visible through V4L2 read
and mmap calls at `/dev/video0`; the Tier C MJPEG backend remains the lower
fallback. Recording writes variable-frame-rate H.264 MP4 so snapshot timing
is not falsely represented as 25 FPS.

The next milestone is an application compatibility matrix. Test `v4l2-ctl`,
FFmpeg, a simple V4L2 viewer, and one desktop camera application with the LSA
environment. Record each supported ioctl, format, and failure. A native
Android Camera2 continuous stream is a separate future provider; it should not
be confused with the current snapshot-compatible path.

### 5. Sensors and location

The Android SensorManager to FUSE-IIO route is working and exposes synthetic
IIO devices plus stream and event services. It still needs broad client
testing, correct `iio-sensor-proxy` compatibility, suspend/resume tests, and a
test matrix for accelerometer, gyro, magnetometer, light, proximity, and
orientation sensors.

Location is currently Android location exposed through GPSD. Test it with
`gpspipe`, a mapping client, permission denial, no-fix conditions, and a
screen-off period. Location does not need a vendor-specific provider unless
the Android API cannot provide the required contract.

### 6. GPU and video

Generic rendering uses the VirGL bridge. The Blackview N6000 has an optional
MediaTek/N6000 H.264 adapter that has produced a real H.264 stream. Keep that
adapter isolated: the generic VideoEncode module only asks for H.264 encode
and video-tap capabilities.

The next work is a generic graphics fallback and a proper rendering test
matrix: Mesa software rendering, VirGL/ANGLE rendering, desktop compositing,
and recovery when the GPU provider stops. For the N6000 encoder, validate
repeated frames, duration, stop/start, and a real capture session. H.265 and
portable MediaTek claims stay out of scope until separately proven.

### 7. Networking and radios

Normal Linux sockets and the Android host interface are the baseline. The
Termux uplink is the lower fallback. That is useful networking, but it is not
ad-hoc Wi-Fi, Wi-Fi Direct data transport, NAN, mesh, IBSS, monitor mode, or
raw-frame networking.

Those are separate projects because the necessary driver primitives differ by
phone. Each one needs its own probe, owned-resource cleanup, peer-visible
test, receive path, and throughput/reliability result. Never call a radio
feature supported because Android advertises a mode or because one frame was
submitted successfully.

### 7. USB and Bluetooth

USB is a useful proven boundary: when Android does not claim a peripheral,
Linux can use the enumerated USB device directly. An RTL-SDR is the working
example: Android saw the USB device without taking ownership of its protocol,
and Linux was able to use the SDR normally. Keyboards and other ordinary USB
peripherals belong in this same Linux-owned USB track. The first job is to
document what the private device namespace exposes and test plug, unplug,
permissions, and reconnect behavior. It is not necessary to write an Android
adapter for a USB device that Linux can already operate directly.

Bluetooth is deliberately on hiatus. Android-routed Bluetooth audio already
works: when a Linux Firefox video plays through LSA's audio output, Android
can route it to an already-connected Bluetooth device. That does not answer
who owns pairing, profiles, reconnects, HID input, or a controller such as a
Wii Remote. We should not add Bluetooth-control code until there is a clear
ownership model that avoids Android and Linux fighting over the same adapter.

For now, record Bluetooth audio routing as tested, keep Bluetooth input and
pairing unclaimed, and do not promise controller support. A future Bluetooth
owner must define the boundary for audio, HID, serial, BLE, pairing, and
disconnect recovery before implementing a backend.

### 8. Device coverage

Every new phone starts as a challenger device. Install and run the unchanged
generic package first. The point of that first pass is to learn exactly what
works, what does not, and why. Collect the capability report, lifecycle logs,
architecture report, selected backend state, and a small application test
matrix before changing the device's LSA source.

When a feature is missing, log the failed Linux contract and its diagnostic.
The preferred next step is to find or build a generic Android adapter for that
contract, so the next challenger benefits too. A contributor is still free to
patch their own phone while investigating; that is useful exploration. It does
not become the generic answer until the failure is understood and the patch is
shown to belong behind a generic capability boundary or an explicitly scoped
vendor/device adapter.

The N6000 H.264 route is the model: device-specific acquisition on one side,
generic capability consumer on the other.

The support matrix must record Android release, ABI, kernel, rootfs
architecture, root method, SELinux state, Termux version, selected backend,
and actual application tests. "Booted once" is not device support.

## Work that can be handed to other people

These areas are independent enough to be owned by different contributors once
they agree to preserve the capability boundary and provide reproducible test
evidence.

| Area | Good owner profile | First useful deliverable |
|---|---|---|
| Audio fallback validation and microphone input | Android audio and Pulse/ALSA developer | A backend-by-backend test plan, route-change evidence, and one working Linux microphone path |
| Camera and recording | V4L2, FFmpeg, or Android Camera2 developer | Compatibility results for real Linux camera apps; a proposed Camera2 streaming provider if snapshots are insufficient |
| Sensors | IIO and Linux sensor-stack developer | Repair `iio-sensor-proxy`, test events/buffers, and document supported sensor classes |
| GPU and video | Mesa, EGL, VirGL, DMA-BUF, or MediaTek multimedia developer | Repeatable rendering tests or a sustained N6000 H.264 test with clean teardown |
| Networking | nl80211, Wi-Fi Direct, mesh, or embedded-networking developer | One narrowly scoped peer transport with peer-visible send/receive evidence and owned cleanup |
| USB peripherals | Linux USB, HID, SDR, or serial-device developer | Plug/unplug and reconnect results for Linux-owned USB devices without an Android protocol owner |
| Bluetooth | Bluetooth-stack and Android-profile developer | An ownership design for pairing, audio, HID, BLE, and reconnects before code is accepted |
| Display and desktop | X11/Wayland and Termux:X11 developer | Application compatibility tests and a recovery path when the display app is stopped |
| New-device testing | Rooted Android user with a spare device | An unmodified-install challenger report, logs for each missing contract, and an application test matrix; personal patches are welcome after evidence collection |
| Packaging, security, and release work | Linux release engineer | Reproducible build checks, upgrade/rollback tests, documentation, and issue templates |

## Rules for contributions

- Start with a small issue that names the Linux interface to expose and the
  application that will prove it works.
- Keep Android, vendor, and device-specific code inside a provider or adapter.
- Keep generic modules free of model checks.
- Include a stop path before asking to merge a start path.
- Mark unproven work as unverified. Logs, sockets, and compilation are useful
  evidence, but they are not end-to-end proof.
- Do not take down the user's active network, audio route, display, or storage
  merely to test a feature. Test resources must be LSA-owned and cleaned up.

## The next public milestones

1. Publish the generic Android 8+ challenger procedure and a hardware support
   matrix.
2. Finish the audio fallback and microphone-input test matrix.
3. Finish the camera application compatibility matrix and decide whether a
   Camera2 streaming provider is needed next.
4. Repair SensorProxy compatibility and test sensor suspend/resume.
5. Add graphics recovery and software-rendering fallback tests.
6. Keep networking at the ordinary-sockets baseline until one peer transport
   can be tested end to end without risking a user's active connection.
7. Document Linux-owned USB peripheral behavior. Keep Bluetooth pairing and
   input work paused until an ownership model is agreed.

This gives contributors a place to start without requiring them to understand
every Android vendor driver. The project grows by making one real Linux
contract dependable at a time.
