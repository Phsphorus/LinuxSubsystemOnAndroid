# LSA

## Linux Subsystem on Android

LSA is an experimental Linux integration layer for rooted Android devices.

The goal is not simply to run Linux inside a chroot.

LSA attempts to make a conventional Linux userspace behave like part of the Android device by bridging Android hardware, services, graphics, audio, sensors, networking, and device interfaces into forms Linux software already understands.

Instead of requiring every Linux application to know how Android works, LSA tries to make Android resources appear as normal Linux resources.

> **Project status:** Pre-Alpha
> **Current known-good release:**
> `1.2.0.5-PreAlpha-KnownGood-FullStack-TierDComplete-20260901`

---

# Architecture

LSA currently consists of two coordinated service environments:

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
    ├── namespace/device compatibility
    └── root-side hardware services
            │
            ▼
      Debian-family rootfs
      /data/local/linux
```

The intended startup order is:

```text
NonRootStart
     ↓
RootStart
     ↓
ModChroot
     ↓
Linux userspace
```

NonRootStart is intentionally a prerequisite of RootStart.

RootStart does not attempt to start or duplicate services that belong to NonRootStart.

---

# Required Android environment

LSA currently expects a specific Android-side Termux environment.

Do **not** assume an arbitrary Play Store, F-Droid, or differently-versioned Termux installation will behave identically.

The current known-good baseline is:

## Termux

**Termux 0.118.3**

```text
termux-app_v0.118.3+github-debug_arm64-v8a.apk
```

Official release:

https://github.com/termux/termux-app/releases/download/v0.118.3/termux-app_v0.118.3+github-debug_arm64-v8a.apk

---

## Termux:API

**Termux:API 0.53.0**

```text
termux-api-app_v0.53.0+github.debug.apk
```

Official release:

https://github.com/termux/termux-api/releases/download/v0.53.0/termux-api-app_v0.53.0+github.debug.apk

---

## Termux:X11

LSA also uses Termux:X11.

The current LSA deployment snapshot can include the known-good Termux:X11 APK under:

```text
assets/termux-x11.apk
```

The deployment system can install the bundled Termux:X11 APK when it is not already present.

---

# Requirements

Current LSA development assumes:

* rooted Android device
* ARM64 Android device for the current known-good Termux build
* Termux `0.118.3`
* Termux:API `0.53.0`
* Termux:X11
* Python inside Termux
* `tar`
* `sha256sum`
* Debian-family ARM64 rootfs
* root shell access
* enough Android/Linux knowledge to recover the device if development software breaks something

The current known-good environment is a development setup.

Device portability is still under active development.

---

# SELinux

Current development uses the:

```text
SELinux Permissive
```

lane.

SELinux Enforcing support is a future/device-specific target.

Do not currently assume that an arbitrary device will run the complete LSA stack correctly under Enforcing.

---

# Root filesystem

LSA does **not** currently distribute the Debian rootfs as part of the LSA deployment snapshot.

A compatible Debian-family rootfs is expected at:

```text
/data/local/linux
```

LSA-owned modifications to the Linux environment are carried primarily through ModChroot:

* injects
* hooks
* mount modules
* environment configuration
* runtime provisioning

This allows the rootfs itself to remain largely independent from the LSA release.

---

# RootStart

RootStart contains services requiring Android root privileges.

Canonical location:

```text
/data/local/RootStart
```

Current RootStart responsibilities include:

* ModChroot
* HALAgent / HALBridge
* Termux:X11 root-side integration
* root-side namespace management
* hardware-facing compatibility services
* startup validation
* lifecycle management

RootStart is started with:

```sh
/data/local/RootStart/RST.sh
```

It should be started only after NonRootStart is already running.

---

# NonRootStart

NonRootStart contains services that are intentionally run as the normal Termux application user.

Canonical location:

```text
/data/data/com.termux/files/home/NonRootStart
```

Current services include:

* HALAudioS
* GPUBridge
* HALSensorBus
* DNS support
* supporting non-root services

NonRootStart is started from Termux as the Termux user:

```sh
~/NonRootStart/NRS.sh
```

Do not start NonRootStart as root unless specifically debugging something that requires it.

---

# ModChroot

ModChroot is LSA's Linux lifecycle and compatibility layer.

It is responsible for preparing the Linux environment rather than requiring users to maintain a heavily modified Debian image.

Current responsibilities include:

* chroot lifecycle management
* preflight checks
* stale-session cleanup
* mount setup
* mount teardown
* rootfs injection
* environment provisioning
* service hooks
* DNS integration
* GPUBridge integration
* HALBridge integration
* `/dev/shm` provisioning
* Linux-private `/dev`
* Android device exposure through `/dev/.host`
* sensor compatibility
* runtime cleanup
* process management

LSA-owned Debian changes are applied through ModChroot during startup.

---

# Device namespace

Modern LSA does not simply expose Android's `/dev` directly as Debian's `/dev`.

The Linux environment receives its own private device namespace:

```text
/dev
```

Android's original device namespace remains accessible separately at:

```text
/dev/.host
```

Conceptually:

```text
Android /dev
     │
     └──────────────► /dev/.host
                           │
                           │ LSA compatibility
                           ▼
                       Linux /dev
```

This gives LSA the ability to provide Linux-compatible devices and interfaces without directly altering Android's device namespace.

---

# HALBridge

HALAgent runs on the Android/root side and exposes Android functionality to Linux through HALBridge.

The Debian-side HALBridge interface is exposed at:

```text
/mnt/halbridge
```

The current stack contains infrastructure covering areas including:

* audio
* speaker routing
* microphone
* camera
* GPS
* CPU information
* device information
* video-related interfaces
* Android service dispatch

A fresh authentication secret is generated during deployment.

The authentication secret from the development/source device is intentionally not included in releases.

Persistent HAL state lives under:

```text
/data/local/RootStart/Services/halagent/state
```

Shared Android staging storage is located at:

```text
/sdcard/halbridge
```

---

# Audio

LSA includes the:

```text
HALAudio
HALAudioS
```

audio path.

HALAudioS is part of NonRootStart and therefore comes online before RootStart and ModChroot.

The goal is to provide Android-backed audio while exposing interfaces Linux applications can use conventionally.

Current audio support is functional but remains under active development.

Application and device compatibility may vary.

---

# Graphics

Current graphics infrastructure includes:

* GPUBridge
* VirGL
* Termux:X11
* Android-side GPU access
* Linux-side GPU socket exposure
* experimental direct frame transport work

GPUBridge is exposed inside Linux through:

```text
/mnt/gpubridge
```

Graphics remain one of the most actively developed parts of LSA.

The broader goal is:

```text
Linux application
       │
       ▼
Linux graphics API
       │
       ▼
LSA / VirGL / GPUBridge
       │
       ▼
Android GPU stack
       │
       ▼
Physical GPU
```

LSA is intended to reduce the amount of Android-specific knowledge required by Linux applications.

---

# Sensors

LSA contains a Linux sensor compatibility layer centered around Linux IIO.

Current infrastructure includes:

* HALSensorBus
* Android sensor discovery
* dynamic sensor registry
* synthetic Linux IIO devices
* stream sensors
* state sensors
* event sensors
* FUSE-backed IIO compatibility
* IIO stream broker
* IIO state broker
* IIO event broker
* target-native event `ioctl` shim
* session-scoped transparent event shim environment

The sensor source tree is located at:

```text
/data/local/RootStart/Services/ModChroot/LSA/Sensors
```

Runtime sensor state inside Debian is located at:

```text
/run/lsa-iio
```

Synthetic IIO devices are exposed through:

```text
/sys/bus/iio/devices
```

The goal is for normal Linux applications to interact with Android sensors through interfaces resembling native Linux hardware.

---

# Current release

## `1.2.0.5-PreAlpha-KnownGood-FullStack-TierDComplete-20260901`

This release represents the current known-good full-stack LSA development snapshot.

Typical deployment kit structure:

```text
LSA-1.2.0.5-PreAlpha-KnownGood-FullStack-TierDComplete-20260901-Autodeploy/
│
├── README.txt
├── VERSION
├── deploy.sh
│
├── assets/
│   └── termux-x11.apk
│
├── manifest/
│   ├── PAYLOAD-SHA256SUMS
│   ├── SOURCE_PATHS.txt
│   ├── TREE.txt
│   ├── build-info.txt
│   ├── debian-packages.txt
│   └── termux-packages.txt
│
└── payload/
    ├── RootStart.tar
    └── NonRootStart.tar
```

---

# Included in the release

The full-stack deployment snapshot includes the complete current project-owned:

* RootStart tree
* NonRootStart tree
* ModChroot
* ModChroot lifecycle implementation
* mount modules
* environment modules
* startup hooks
* rootfs injects
* HALAgent
* HALBridge
* HALAudio
* HALAudioS
* DNS support
* GPUBridge
* Termux:X11 RootStart integration
* HALSensorBus
* LSA Sensors source tree
* LSA Sensors proven tree
* Tier-D private `/dev`
* Tier-D FUSE IIO compatibility
* IIO stream broker
* IIO state broker
* IIO event broker
* dynamic IIO registry
* target-native event ioctl shim source/build path
* transparent event shim environment
* Termux package manifest
* Debian package manifest
* source-tree manifest
* payload SHA-256 checksums
* current Termux:X11 APK when available

---

# Not included

The deployment snapshot intentionally does **not** include:

* `/data/local/linux` Debian rootfs
* live process IDs
* live sockets
* runtime logs
* runtime caches
* captured camera data
* captured microphone data
* recording runtime data
* the development device's HALBridge authentication secret

These are either system-specific, volatile, private, or too large to belong in the portable LSA snapshot.

---

# Deployment behavior

The auto-deployer currently:

1. verifies the bundled payload checksums
2. checks that it is running as root
3. verifies the expected Termux environment
4. verifies that a Debian-family rootfs exists
5. refuses to overwrite a running ModChroot session
6. detects the target Termux UID and GID
7. backs up the existing RootStart tree
8. backs up the existing NonRootStart tree
9. extracts the complete RootStart payload
10. extracts the complete NonRootStart payload
11. applies the correct Termux ownership
12. creates fresh runtime directories
13. generates a fresh HALBridge authentication secret
14. prepares shared HALBridge storage
15. optionally installs the bundled Termux:X11 APK
16. verifies critical LSA / Tier-D files

---

# Installation

## 1. Install the required Android applications

Install the current known-good Termux build:

```text
Termux 0.118.3
termux-app_v0.118.3+github-debug_arm64-v8a.apk
```

Install the current known-good Termux:API build:

```text
Termux:API 0.53.0
termux-api-app_v0.53.0+github.debug.apk
```

Install or allow LSA to install the required Termux:X11 build.

---

## 2. Prepare Termux

LSA expects Termux at its normal Android location:

```text
/data/data/com.termux/files
```

The Termux home directory should therefore be:

```text
/data/data/com.termux/files/home
```

Required Termux-side tools include at minimum:

```text
python
tar
sha256sum
```

Additional package requirements can be determined from the included:

```text
manifest/termux-packages.txt
```

---

## 3. Prepare Debian

Place the compatible Debian-family rootfs at:

```text
/data/local/linux
```

Package information from the known-good development rootfs is included in:

```text
manifest/debian-packages.txt
```

The rootfs itself is not included with LSA.

---

## 4. Deploy LSA

Copy or extract the LSA deployment kit onto the Android device.

Run:

```sh
./deploy.sh
```

as root.

The deployment system will install RootStart and NonRootStart and prepare the target environment.

---

# Starting LSA

## Step 1 — NonRootStart

Open normal Termux.

Run as the Termux user:

```sh
~/NonRootStart/NRS.sh
```

NonRootStart should remain active.

---

## Step 2 — RootStart

Enter a root shell.

Run:

```sh
/data/local/RootStart/RST.sh
```

RootStart assumes the required NonRootStart services are already available.

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

Android device namespace exposed inside Linux
/dev/.host

HALBridge
/mnt/halbridge

GPUBridge
/mnt/gpubridge

Shared Android HAL staging
/sdcard/halbridge
```

---

# Project design

The basic LSA philosophy is:

```text
Linux application
       │
       │ normal Linux API
       ▼
Linux-compatible interface
       │
       │ LSA translation / bridge
       ▼
Android kernel / framework / HAL
       │
       ▼
Phone hardware
```

The application ideally should not need to know that the underlying machine is Android.

For example:

```text
Linux sensor application
        │
        ▼
/sys/bus/iio/devices
        │
        ▼
LSA synthetic IIO stack
        │
        ▼
HALSensorBus
        │
        ▼
Android sensors
```

or:

```text
Linux graphics application
        │
        ▼
Linux graphics stack
        │
        ▼
VirGL / GPUBridge
        │
        ▼
Android GPU
```

or:

```text
Linux device access
        │
        ▼
/dev
        │
        ▼
LSA private device namespace
        │
        ├── Linux-compatible virtual devices
        │
        └── /dev/.host
                │
                ▼
           Android devices
```

LSA handles the translation layer between the two operating environments.

---

# What LSA is not

LSA is not:

* a normal Termux distro wrapper
* proot
* a Linux emulator
* a virtual machine
* just a Debian chroot
* a desktop launcher
* a collection of isolated Android control scripts

The chroot is only one component.

LSA's purpose is the compatibility infrastructure surrounding it.

---

# Current status

LSA is still **Pre-Alpha**.

The current release is a known-good development snapshot, not a universal stable release.

Known-good functionality does not yet imply compatibility across arbitrary:

* phones
* Android versions
* kernels
* vendors
* SoCs
* GPU drivers
* sensor HAL implementations

Current major development areas include:

* graphics and display integration
* direct frame transport
* GPUBridge
* Termux:X11 integration
* hardware abstraction
* Android/Linux device translation
* Linux sensor compatibility
* audio compatibility
* rootfs portability
* ModChroot portability
* automated bootstrap
* reducing device-specific assumptions
* eventually supporting SELinux Enforcing configurations

---

# Development model

LSA development currently follows known-good snapshots.

A snapshot represents a stack that has been tested together:

```text
Android environment
+
Termux environment
+
NonRootStart
+
RootStart
+
ModChroot
+
Linux rootfs
+
LSA compatibility layers
```

This is important because many parts of LSA interact with boundaries Android normally does not expose as traditional Linux interfaces.

The current known-good release is:

```text
1.2.0.5-PreAlpha-KnownGood-FullStack-TierDComplete-20260901
```

---

# Warning

LSA runs with root privileges and modifies the runtime environment of a rooted Android device.

This is development software.

It can break.

Do not test LSA on a device you cannot recover.

You should be comfortable with:

* ADB
* root shells
* Android filesystem layout
* Linux mounts
* process management
* recovering boot/runtime problems

before treating the current Pre-Alpha builds as anything other than development software.

---

# License

Apache License 2.0

See:

```text
LICENSE
```
