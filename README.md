# LSA

## Linux Subsystem on Android

LSA is an Android-to-Linux compatibility and capability-brokering layer for rooted Android devices.

The goal is not simply to run Debian inside a chroot.

LSA attempts to make a conventional Linux userspace behave as though the hardware and services of the Android phone are part of the Linux system.

Android remains the host operating system and kernel. LSA discovers what the device can provide, selects the best available implementation for each subsystem, and exposes Android-backed capabilities to Linux through native or native-like Linux interfaces.

Instead of requiring Linux applications to understand Android APIs directly, LSA attempts to make Android resources appear as normal Linux resources.

Examples include:

* audio
* graphics
* displays
* sensors
* storage
* cameras
* location
* device interfaces
* D-Bus
* FUSE
* networking and wireless hardware

> **Project status:** Pre-Alpha

---

# What LSA is

Conceptually:

```text
Linux application
        │
        │ normal Linux API
        ▼
Linux/native-like interface
        │
        ▼
LSA module
        │
        ▼
selected capability backend
        │
        ▼
Android framework / HAL / kernel
        │
        ▼
Phone hardware
```

The application ideally does not need to know that the underlying machine is Android.

LSA is intended to be the platform underneath normal Linux software rather than a collection of Android-specific application APIs.

---

# What LSA is not

LSA is not:

* proot
* a Linux emulator
* a virtual machine
* a normal Termux distro wrapper
* just a Debian chroot
* a desktop launcher
* a collection of isolated Android control scripts

The Debian rootfs is only one part of the system.

The primary project is the compatibility infrastructure surrounding it.

---

# High-level architecture

LSA is divided between Android-side providers, Linux-facing modules, and the Debian userspace.

```text
                         Android
                            │
             ┌──────────────┴──────────────┐
             │                             │
       NonRootStart                    RootStart
             │                             │
   Termux-user providers          Root Android providers
             │                             │
             └──────────────┬──────────────┘
                            │
                       LSA Framework
                            │
                  capability discovery
                            │
                    provider selection
                            │
                     A-Z backends
                            │
                         Modules
                            │
                       ModChroot
                            │
                   Debian userspace
```

The required startup order remains:

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

RootStart does not duplicate services that belong to the Termux-user environment.

---

# Capability-driven Core

LSA does not assign one compatibility grade to an entire phone.

Each module independently discovers what implementations are available and selects its own best backend.

Modules can include areas such as:

* CoreChroot
* DeviceNamespace
* Storage
* Audio
* GPU
* Display
* Sensors
* FUSE
* D-Bus
* Camera
* Location
* Capture
* Wireless
* VideoEncode where available

Each module can have multiple implementations arranged into local compatibility tiers:

```text
A ... Z
```

`A` represents the best available general implementation currently known for that module.

`Z` is reserved for the lowest genuine fallback when one exists.

Tier letters are local to the module.

For example:

```text
Audio               Tier A
DeviceNamespace     Tier B
Display             Tier C
Storage             Tier A
Wireless            Tier A
```

This does **not** mean the phone itself is Tier A, B, or C.

Empty tier letters are valid. LSA does not invent meaningless backends simply to fill the alphabet.

---

# Capability probing

LSA prefers capability detection over compatibility tables based on phone model, Android version, or vendor.

A backend can be:

```text
AVAILABLE
UNSUPPORTED
ERROR
```

Administrative policy is tracked separately.

Where relevant, hardware evidence can also distinguish between:

```text
ADVERTISED
PROBED
OPERATIONALLY_VERIFIED
```

The framework is designed to avoid treating:

```text
"the driver says it supports this"
```

as equivalent to:

```text
"this was tested and actually works"
```

Device/vendor-specific providers are still allowed where they are genuinely necessary to expose hardware behavior, but generic compatibility should not depend on hardcoded phone-model lists.

---

# Backend rejection and fallback

LSA normally chooses the highest-ranked working backend automatically.

A user can deliberately reject a backend:

```sh
lsectl reject <backend-id>
```

The backend can remain technically:

```text
AVAILABLE
```

while also being:

```text
REJECTED BY USER
```

LSA will then attempt the next compatible backend.

To allow it again:

```sh
lsectl accept <backend-id>
```

Backend rejection is persistent and survives normal restart and redeployment.

This is useful both for working around a malfunctioning backend and for testing lower compatibility tiers.

---

# Android environment

LSA currently targets the GitHub Termux environment rather than assuming arbitrary Termux builds are interchangeable.

The current known-good Termux application baseline is:

## Termux

**Termux 0.118.3**

```text
termux-app_v0.118.3+github-debug
```

Official project:

https://github.com/termux/termux-app

---

## Termux:API

**Termux:API 0.53.0**

Official project:

https://github.com/termux/termux-api

The LSA deployment package can include the exact supported Termux:API APK and install it when required.

---

## LSA-X11

LSA uses its own modified Termux:X11 derivative:

```text
LSA-X11
```

Source:

https://github.com/Phsphorus/lsa-x11

LSADeploy can include the corresponding LSA-X11 APK and install/update it automatically when necessary.

LSA-X11 remains separately licensed under GPL-3.0 as a Termux:X11 derivative.

---

# Architecture support

LSA no longer assumes that the entire device is ARM64.

Architecture is detected independently across several layers:

* Android ABI
* Android kernel architecture
* Termux userspace architecture
* Debian/Linux rootfs architecture
* individual bundled executable assets

Current generic Debian architecture mappings include:

```text
arm64      -> arm64
armv7      -> armhf
x86_64     -> amd64
x86        -> i386
```

Architecture normalization handles common Android/Linux naming differences such as:

```text
arm64-v8a
aarch64

armeabi-v7a
armv7l
armv8l
armhf
```

Architecture-specific assets are independently gated so that an incompatible optional binary does not prevent unrelated modules from functioning.

LSA has been tested across both ARM64 and ARMv7 Android userspaces.

---

# Deployment

LSA is distributed through:

```text
LSADeploy
```

The normal installation command is:

```sh
./deploy.sh
```

The deployer locates its own package directory, so the shell's current working directory is not used as the basis for its internal paths.

A normal full deployment can:

1. detect the installed Termux environment
2. determine the Termux UID/GID
3. detect Android, kernel, Termux, and rootfs architecture
4. verify deployment payload hashes
5. preserve an existing installation before replacement
6. preserve persistent backend-rejection policy
7. install required generic Termux packages
8. validate/install bundled Android support applications
9. inspect an existing Debian rootfs
10. bootstrap a Debian rootfs when necessary
11. resume an interrupted rootfs bootstrap when safe
12. deploy RootStart
13. deploy NonRootStart
14. generate fresh device-local authentication state
15. perform framework/capability discovery
16. start NonRootStart
17. start RootStart
18. start the Linux environment
19. perform post-install health checks

The package does **not** contain a prebuilt Debian rootfs.

When required, Debian is provisioned for the target architecture.

---

# Deployment modes

## Full installation

```sh
./deploy.sh
```

or:

```sh
./deploy.sh full
```

This is the normal user installation mode.

---

## Framework-only

```sh
./deploy.sh framework-only
```

Framework-only mode installs and runs the LSA capability framework without provisioning or starting the complete Debian environment.

It is useful for:

* architecture discovery
* provider discovery
* hardware compatibility testing
* backend probing
* framework diagnostics

---

## Resume rootfs

If Debian provisioning was interrupted:

```sh
./deploy.sh resume-rootfs
```

LSA attempts to determine whether the partial rootfs can safely be resumed rather than silently accepting or deleting an incomplete installation.

---

# Canonical installed paths

```text
RootStart
/data/local/RootStart

NonRootStart
/data/data/com.termux/files/home/NonRootStart

Debian rootfs
/data/local/linux

HALAgent persistent state
/data/local/RootStart/Services/halagent/state

Linux private device namespace
/dev

Android host device namespace inside Linux
/dev/.host

HALBridge
/mnt/halbridge

GPUBridge
/mnt/gpubridge

LSA sensor runtime
/run/lsa-iio
```

---

# RootStart

RootStart owns services that require Android root privileges.

Canonical location:

```text
/data/local/RootStart
```

Responsibilities include:

* ModChroot
* root-side capability providers
* HALAgent / HALBridge
* namespace management
* device compatibility
* lifecycle management
* capability framework integration
* hardware-facing root services

RootStart participates in the normal deployment/startup lifecycle.

Users should normally allow LSADeploy to manage startup rather than manually reconstructing the sequence.

---

# NonRootStart

NonRootStart contains services that intentionally run as the Termux application user.

Canonical location:

```text
/data/data/com.termux/files/home/NonRootStart
```

Responsibilities include Termux-user Android providers and services such as:

* audio transport
* GPUBridge
* sensor transport
* supporting Android/Termux integration

NonRootStart is intentionally started before RootStart.

---

# ModChroot

ModChroot manages the Linux environment and the compatibility layers surrounding the Debian rootfs.

Responsibilities include:

* chroot lifecycle
* preflight
* stale-session cleanup
* mount setup
* mount teardown
* rootfs provisioning
* runtime injections
* startup hooks
* environment configuration
* namespace setup
* service integration
* `/dev/shm`
* private Linux `/dev`
* host Android `/dev` exposure
* synthetic Linux interfaces
* runtime cleanup
* process ownership

The rootfs is intentionally kept as independent from LSA as practical.

LSA-owned Linux changes are applied dynamically through the ModChroot lifecycle.

---

# Device namespace

LSA does not use Android's `/dev` directly as Debian's normal `/dev`.

The Linux environment receives a private device namespace:

```text
/dev
```

The Android host device namespace is exposed separately at:

```text
/dev/.host
```

Conceptually:

```text
Android /dev
     │
     └──────────────► Linux /dev/.host
                             │
                             │ capability-specific exposure
                             ▼
                         Linux /dev
```

This allows LSA to provide Linux-compatible virtual devices, mappings, and proxies without directly modifying Android's host device namespace.

---

# HALAgent / HALBridge

HALAgent provides a root-side Android capability boundary used by HALBridge and related providers.

Linux-facing HALBridge state is exposed through:

```text
/mnt/halbridge
```

Authentication state is generated locally for each target installation.

A live authentication secret from a development device is never intended to be included in a release package.

Current generated authentication state uses restricted filesystem permissions and avoids logging raw authentication material.

---

# Audio

LSA exposes Android-backed audio through the normal Audio module and Android provider stack.

Supported paths can include:

* speaker output
* Bluetooth-routed output
* microphone capture
* negotiated Android audio formats
* Linux PulseAudio-facing behavior

The implementation no longer assumes that all output must use a fixed 48 kHz format.

The selected Linux and Android sides negotiate the available audio path instead.

Conceptually:

```text
Linux application
        ↓
Linux audio interface
        ↓
LSA Audio
        ↓
Android audio provider
        ↓
Android audio stack
        ↓
speaker / Bluetooth / microphone
```

---

# Graphics

LSA graphics currently use the GPU module and Android GPU provider infrastructure.

The generic graphics path includes:

```text
Linux application
        ↓
Mesa / VirGL / virpipe
        ↓
LSA GPU
        ↓
GPUBridge
        ↓
Android GPU stack
        ↓
physical GPU
```

GPUBridge is provided to the Linux environment through the LSA runtime rather than being treated as an unrelated external service.

Optional device-specific acceleration/video paths can coexist with the generic graphics path where capability probing proves them usable.

---

# Display

Display integration uses LSA-X11.

The Android-facing display provider owns the display lifecycle while the Linux module consumes the resulting Linux-facing X11 interface.

This keeps display integration inside normal LSA provider/module ownership.

---

# Sensors

LSA provides Android sensors to Linux through a Linux IIO compatibility stack.

Conceptually:

```text
Android SensorManager
        ↓
Android sensor provider
        ↓
LSA Sensors
        ↓
dynamic sensor registry
        ↓
synthetic Linux IIO sysfs
        ↓
private Linux /dev compatibility
        ↓
Linux sensor applications
```

Current capabilities include:

* Android sensor discovery
* dynamic registry generation
* stream sensors
* state sensors
* event sensors
* FUSE-backed IIO interfaces
* synthetic `/sys/bus/iio/devices`
* Linux `/dev/iio:*` compatibility
* event ioctl compatibility
* actual sensor sample transport

Runtime state is kept under:

```text
/run/lsa-iio
```

The goal is to allow Linux sensor-facing software to interact with Android hardware without directly implementing Android SensorManager APIs.

---

# FUSE

FUSE is managed through normal LSA module ownership.

The DeviceNamespace module is responsible for publishing relevant Linux device access, while consumers such as Sensors own their own FUSE mounts and runtime state.

This keeps cleanup and lifecycle ownership explicit.

---

# D-Bus

LSA provides a normal Linux system D-Bus inside the environment.

D-Bus lifecycle is module-owned and is included in normal automatic startup.

The Linux environment can use conventional D-Bus interfaces rather than relying on LSA-specific IPC for normal Linux software.

---

# Storage

Storage uses capability-based backend selection.

The highest-quality available Android/Linux shared-storage path is selected automatically.

Lower compatibility mechanisms can be used as fallbacks where available.

Actual create/read/delete operations are used during validation rather than treating path existence alone as proof of functionality.

---

# Wireless

Wireless is a baseline LSA module.

Its goal is broader than merely giving Debian Internet access.

LSA attempts to inspect and expose the phone's wireless hardware and peer-networking capabilities to Linux through native Linux networking interfaces wherever possible.

Current and developing capability areas include:

* Linux-visible wireless interfaces
* managed Wi-Fi
* AP mode
* monitor mode
* interface concurrency
* channel concurrency
* 802.11s
* IBSS
* Wi-Fi Direct / P2P
* NAN / Wi-Fi Aware
* remain-on-channel
* management/action-frame TX/RX
* wireless metrics

Capability reporting distinguishes driver advertisement from actual operational verification.

Conceptually:

```text
Android Wi-Fi hardware
        ↓
Android framework / HAL / driver / kernel
        ↓
LSA Wireless
        ↓
selected backend
        ↓
Linux network interface
        ↓
normal Linux networking
```

Where the kernel can expose a real interface, LSA prefers that.

Where Android must own the control plane, LSA attempts to keep the resulting Linux data plane conventional.

Wireless qualification can perform aggressive first-run capability testing and persist the results so disruptive hardware probing does not need to be repeated on every startup.

---

# Linux-native presentation

A central LSA design rule is:

> If Linux already has an established interface for a capability, prefer exposing that interface rather than creating an LSA-specific application API.

Examples include:

```text
/sys
/dev
IIO
network interfaces
sockets
D-Bus
FUSE
X11
PulseAudio
rtnetlink
nl80211
```

Translation layers are used when Android cannot directly expose the native Linux mechanism.

---

# SELinux

LSA historically developed primarily under SELinux Permissive because early development prioritized discovering and validating hardware integration paths.

SELinux Enforcing is now a security-hardening target.

The intended direction is:

```text
Rooted Android
SELinux Enforcing
        ↓
minimal LSA privilege boundary
        ↓
capability providers
        ↓
selected module backends
        ↓
Linux userspace
```

LSA should not automatically disable global SELinux enforcement merely because an optional backend cannot operate.

Where Enforcing support requires policy changes, those permissions should be minimized and tied to actual required operations rather than generated as broad allow rules.

Permissive remains useful as an explicit development/debugging lane.

---

# Security model

LSA operates across unusually privileged Android/Linux boundaries and therefore treats security as part of the platform architecture.

Current hardening includes or targets:

* device-local authentication secrets
* restricted secret permissions
* removal of raw authentication material from logs
* explicit runtime ownership
* private Linux device namespace
* capability-specific hardware exposure
* controlled IPC permissions
* bounded provider operations
* package checksum verification
* APK identity/provenance validation
* source correspondence records
* secure deployment replacement
* persistent user policy
* SELinux Enforcing compatibility

LSA runs with root privileges where hardware integration requires them, but the design goal is not to make every component universally privileged.

---

# Diagnostics

The primary framework diagnostic command is:

```sh
lsectl report --verbose
```

The report can include:

* architecture information
* providers
* capabilities
* modules
* selected backends
* compatibility tiers
* backend health
* fallback reasons
* unsupported functionality
* runtime state

Unsupported optional hardware should normally remain local to that module rather than causing unrelated parts of LSA to fail.

---

# Portability philosophy

LSA should not require an explicit compatibility entry for every phone.

The intended process for an unknown device is:

```text
discover architecture
        ↓
discover providers
        ↓
probe capabilities
        ↓
select usable backends
        ↓
construct Linux-facing interfaces
        ↓
report unsupported capabilities truthfully
```

Old and unusual devices are useful development targets because they expose assumptions hidden by the primary development hardware.

Compatibility fixes discovered on one device should be made generic whenever the underlying issue is generic.

---

# Deployment package contents

A public LSADeploy package can contain:

```text
deploy.sh
VERSION
README.txt

apps/
payload/
sources/
manifest/
LICENSES/

LICENSE
NOTICE
THIRD_PARTY_NOTICES.md
SOURCE_AVAILABILITY.md
```

The release intentionally excludes live/device-specific state such as:

* preconfigured Debian rootfs
* PID files
* sockets
* runtime logs
* runtime caches
* camera captures
* microphone captures
* Python bytecode
* source-device authentication secrets

Existing LSA installations are preserved before normal payload replacement.

---

# Source and licensing

LSA-authored code is licensed under:

```text
Apache License 2.0
```

See:

```text
LICENSE
NOTICE
```

Separately distributed software retains its own license.

LSA-X11 is derived from Termux:X11 and is distributed under GPL-3.0.

Bundled Termux:API components also retain their respective upstream licensing.

Release packages include source/provenance and third-party licensing information where applicable.

---

# Project repositories

LSA:

https://github.com/Phsphorus/LinuxSubsystemOnAndroid

LSA-X11:

https://github.com/Phsphorus/lsa-x11

---

# Current status

LSA remains **Pre-Alpha**.

That label reflects the maturity and stability of the project, not the absence of working functionality.

The stack already performs real Android-to-Linux hardware integration across multiple subsystems and architectures, but major areas remain under active development and compatibility across arbitrary Android hardware is not guaranteed.

Major development areas include:

* completing the Wireless hardware stack
* SELinux Enforcing support
* security hardening
* broader device portability
* additional A-Z compatibility backends
* reducing remaining vendor assumptions
* Linux-native hardware presentation
* graphics/display integration
* device namespace refinement
* automated deployment and recovery

---

# Development model

LSA development is capability-driven.

A working implementation should prove more than the existence of a socket, device node, or framework API.

Where practical, validation should exercise the actual data path.

Examples include:

```text
Audio
    actual playback/capture

GPU
    actual rendered workload

Sensors
    actual sensor samples/events

Storage
    create/read/delete

D-Bus
    actual message round trip

Wireless
    actual packet transfer
```

The framework should distinguish between hardware that is absent, hardware that advertises support but fails operationally, and hardware that has been genuinely tested.

---

# Warning

LSA is low-level rooted Android system software.

It interacts with:

* root processes
* Android services
* mount namespaces
* device nodes
* kernel interfaces
* Wi-Fi hardware
* graphics hardware
* audio hardware
* SELinux
* Linux system services

Development and hardware qualification can intentionally disrupt individual Android services while probing what a device actually supports.

Do not test LSA on a device you cannot recover.

Developers and early users should be comfortable with:

* ADB
* Android root shells
* Linux shells
* mount namespaces
* process management
* Android filesystem layout
* recovering failed runtime state

before treating Pre-Alpha builds as production software.
