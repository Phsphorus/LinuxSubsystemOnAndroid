# LSA

### Linux Subsystem on Android

LSA is an experimental Linux integration layer for rooted Android devices.

The goal is not simply to run a Linux chroot on Android. LSA attempts to make the Linux environment behave like part of the device by bridging Android hardware, services, graphics, audio, sensors, networking, and device interfaces into a conventional Linux userspace.

Instead of expecting every Linux application to understand Android, LSA tries to make Android resources appear in forms Linux software already understands.

> **Current status:** Pre-Alpha
> **Current known-good snapshot:** `1.2.0.5-PreAlpha-KnownGood-FullStack-TierDComplete-20260901`

---

## What LSA currently consists of

LSA is split into two coordinated service trees:

```text
Android
│
├── NonRootStart
│   ├── DNS
│   ├── HALAudioS
│   ├── GPUBridge
│   ├── HALSensorBus
│   └── supporting non-root services
│
└── RootStart
    ├── ModChroot
    ├── HALAgent / HALBridge
    ├── Termux:X11 integration
    └── root-side hardware / namespace services
            │
            ▼
      Debian-family rootfs
      /data/local/linux
```

Startup order is intentionally:

```text
NonRootStart
     ↓
RootStart
     ↓
ModChroot
     ↓
Linux userspace
```

NonRootStart services are treated as prerequisites. RootStart does not own or duplicate them.

---

# ModChroot

ModChroot is LSA's chroot lifecycle and compatibility layer.

It is responsible for preparing the Linux environment rather than relying on a heavily modified rootfs image.

Current responsibilities include:

* chroot lifecycle management
* mount setup and teardown
* environment provisioning
* rootfs injection
* startup hooks
* service integration
* DNS integration
* GPUBridge exposure
* HALBridge exposure
* `/dev/shm` provisioning
* private Linux `/dev`
* Android device exposure through `/dev/.host`
* sensor compatibility
* cleanup and stale-session detection

LSA-owned changes to Debian are primarily carried as ModChroot injects and hooks and are applied when the environment is started.

This allows the Debian rootfs itself to remain separate from LSA.

---

# Android hardware integration

LSA currently contains infrastructure for bridging Android functionality into Linux.

## HALBridge

HALAgent runs on the Android/root side and exposes Android functionality to the Linux environment through HALBridge.

The current stack contains support and infrastructure for areas including:

* audio
* speakers
* microphone
* camera
* GPS
* CPU/device information
* video-related interfaces
* Android-side service dispatch

A per-installation authentication secret is generated during deployment rather than distributing the source device's secret.

The Debian-side HALBridge view is exposed at:

```text
/mnt/halbridge
```

---

# Audio

LSA includes the HALAudio / HALAudioS audio path.

This provides an Android-backed audio path for Linux applications while allowing the Linux environment to continue using conventional audio interfaces.

HALAudioS is a NonRootStart service and is started before the root-side LSA stack.

Audio integration is still under active development and compatibility varies by application and device.

---

# Graphics

Current graphics infrastructure includes:

* GPUBridge
* VirGL infrastructure
* Termux:X11 integration
* Linux GPU socket exposure through `/mnt/gpubridge`

Graphics and display integration are still one of the most actively developed parts of LSA.

The long-term objective is to reduce the number of Android-specific assumptions applications need to make and provide a Linux graphics environment backed by the Android device's hardware.

---

# Sensors

LSA contains a Linux sensor compatibility layer designed around Linux IIO interfaces.

The current sensor stack includes:

* HALSensorBus
* dynamic sensor discovery
* dynamic IIO registry generation
* synthetic IIO devices
* stream sensors
* state sensors
* event sensors
* FUSE-backed IIO compatibility
* IIO stream broker
* IIO state broker
* IIO event broker
* target-native event `ioctl` shim
* session-scoped event shim environment

The Linux sensor runtime lives at:

```text
/run/lsa-iio
```

and synthetic devices are exposed through the normal Linux IIO path:

```text
/sys/bus/iio/devices
```

This is intended to allow Linux software to consume Android sensors without requiring application-specific Android code.

---

# Device namespace

Modern LSA does not simply expose Android's `/dev` directly as the Linux `/dev`.

The Debian environment receives its own private device namespace.

```text
/dev
```

is the Linux-facing namespace.

Android's underlying device namespace is available separately at:

```text
/dev/.host
```

This gives LSA room to provide Linux-compatible virtual or translated devices without modifying Android's own `/dev`.

---

# Current release

## `1.2.0.1-PreAlpha-KnownGood-FullStack-TierDComplete-20260901`

This is a known-good full-stack development snapshot.

The deployment kit contains:

```text
README.txt
VERSION
deploy.sh

assets/
    termux-x11.apk

manifest/
    PAYLOAD-SHA256SUMS
    SOURCE_PATHS.txt
    TREE.txt
    build-info.txt
    debian-packages.txt
    termux-packages.txt

payload/
    RootStart.tar
    NonRootStart.tar
```

### Included

The snapshot contains the complete project-owned:

* `RootStart`
* `NonRootStart`
* ModChroot lifecycle
* ModChroot mount modules
* hooks
* environment modules
* rootfs injects
* HALAgent / HALBridge
* HALAudio / HALAudioS
* DNS service
* GPUBridge
* Termux:X11 integration
* HALSensorBus
* LSA Sensors source/proven trees
* Tier-D private `/dev`
* Tier-D FUSE IIO compatibility
* stream/state/event IIO brokers
* dynamic sensor registry
* native IIO event shim source/build path
* package manifests
* payload manifests
* payload checksums

### Intentionally NOT included

The snapshot does **not** contain:

* a Debian rootfs
* live PID files
* live sockets
* runtime logs
* runtime caches
* captured camera data
* captured microphone/recording data
* the source device's HALBridge authentication secret

---

# Requirements

LSA is currently a development project.

You should expect to need:

* a rooted Android device
* Termux
* Python in Termux
* `tar`
* `sha256sum`
* a Debian-family rootfs
* shell/root access
* familiarity with recovering a rooted Android installation if something breaks

The Debian rootfs is expected at:

```text
/data/local/linux
```

The normal Termux location is expected:

```text
/data/data/com.termux/files/home
```

### SELinux

Current development and known-good testing use the **SELinux Permissive** development lane.

SELinux Enforcing compatibility is a future/device-specific target and should not currently be assumed.

---

# Installation

This release does **not** contain the Debian rootfs itself.

First place a compatible Debian-family rootfs at:

```text
/data/local/linux
```

Then copy/extract the LSA deployment kit onto the Android device.

Run the deployment script as root:

```sh
./deploy.sh
```

The deployer will:

* verify payload checksums
* refuse to overwrite a running LSA installation
* back up an existing RootStart installation
* back up an existing NonRootStart installation
* install the current payload
* adapt NonRootStart ownership to the device's Termux UID/GID
* recreate clean runtime directories
* generate a new HALBridge authentication secret
* prepare shared HALBridge storage
* optionally install the bundled Termux:X11 APK
* verify critical LSA files

---

# Starting LSA

Start **NonRootStart first as the Termux user**:

```sh
~/NonRootStart/NRS.sh
```

Then start **RootStart as root**:

```sh
/data/local/RootStart/RST.sh
```

RootStart assumes NonRootStart services already exist.

---

# Canonical paths

```text
RootStart
/data/local/RootStart

NonRootStart
/data/data/com.termux/files/home/NonRootStart

Debian rootfs
/data/local/linux

HAL persistent state
/data/local/RootStart/Services/halagent/state

LSA sensor source
/data/local/RootStart/Services/ModChroot/LSA/Sensors

LSA sensor runtime
/run/lsa-iio

Linux private device namespace
/dev

Android device namespace inside Linux
/dev/.host

HALBridge
/mnt/halbridge

GPUBridge
/mnt/gpubridge

Shared Android staging
/sdcard/halbridge
```

---

# Project status

LSA is **Pre-Alpha**.

Things working in the development stack should not yet be interpreted as guarantees across arbitrary Android devices.

A lot of the current work is focused on creating compatibility layers at the boundary between Android and Linux rather than modifying individual Linux programs.

Major active areas include:

* graphics/display integration
* GPUBridge
* Termux:X11 integration
* hardware compatibility
* sensor compatibility
* audio compatibility
* ModChroot portability
* device-independent bootstrap/deployment
* reducing device-specific assumptions

---

# Design goal

The end goal of LSA is approximately:

```text
Linux application
       │
       │ normal Linux API
       ▼
Linux-compatible interface
       │
       │ LSA bridge / translation
       ▼
Android kernel / framework / HAL
       │
       ▼
Phone hardware
```

The Linux application ideally should not need to know that it is running on Android.

LSA handles the ugly part.

---

## License

Apache License 2.0

See `LICENSE`.
