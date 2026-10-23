# Linux Subsystem on Android (LSA)

LSADeploy is the installation package for Linux Subsystem on Android.

LSA creates and configures a Debian Linux environment on a rooted Android
device and connects supported Android hardware and services to Linux.

This file covers installing and starting LSA.

# REQUIREMENTS

Before installing LSA, you need:

* A rooted Android device
* Termux installed
* Internet access for the initial installation
* Enough free storage for the Debian rootfs and packages

The currently supported/known-good Termux build is:

Termux 0.118.3

LSADeploy includes the Android-side support applications it needs, including
Termux:API and LSA-X11. The deployer installs or updates these automatically
when required.

# INSTALLATION

## 1. Copy LSADeploy to the phone

Copy the entire extracted `LSADeploy` directory somewhere accessible on the
target device.

For example:

```
/sdcard/Download/LSADeploy
```

The exact location does not matter.

Do not run `deploy.sh` directly from inside the ZIP file. Extract the complete
package first.

## 2. Open a shell

Open Termux or connect to the phone through SSH.

Enter an Android root shell.

LSADeploy must be run as root.

## 3. Go to LSADeploy

For example:

```
cd /sdcard/Download/LSADeploy
```

If `deploy.sh` is not executable, run:

```
chmod +x deploy.sh
```

## 4. Start the installer

Run:

```
./deploy.sh
```

This is the normal installation command.

It is equivalent to:

```
./deploy.sh full
```

The deployer automatically determines where the LSADeploy package is located,
so its internal paths do not depend on the directory from which it was called.

# WHAT THE INSTALLER DOES

A normal full installation will automatically:

1. Detect Android, kernel, Termux, and CPU architecture information.
2. Locate the installed Termux environment.
3. Install required Termux packages.
4. Validate and install the bundled Termux:API application.
5. Validate and install the bundled LSA-X11 application.
6. Detect whether a Debian rootfs already exists.
7. Create or resume the correct Debian rootfs when required.
8. Install the LSA RootStart and NonRootStart components.
9. Detect available device capabilities.
10. Select the best working backend for each LSA subsystem.
11. Start NonRootStart.
12. Start RootStart.
13. Start the Debian environment.
14. Run post-installation checks.

The installer is designed so that an existing valid installation can be
upgraded rather than requiring the user to manually remove it first.

# FIRST INSTALL CAN TAKE A WHILE

The first full installation may need to download and unpack a Debian rootfs
and install packages.

Do not interrupt the installer simply because a step is taking longer on an
older or slower phone.

If the installation is actually interrupted while creating the rootfs, see
the recovery section below.

# INSTALL MODES

## Full install

Normal installation:

```
./deploy.sh
```

or:

```
./deploy.sh full
```

Use this for a normal LSA installation.

## Framework-only

Run:

```
./deploy.sh framework-only
```

This installs and tests the LSA framework without creating a Debian rootfs or
starting the complete Linux environment.

This mode is mainly useful for:

* Compatibility testing
* Device capability detection
* Architecture detection
* Diagnosing a new device

Most users should use the normal full installation instead.

## Resume interrupted rootfs installation

If Debian installation was interrupted, run:

```
./deploy.sh resume-rootfs
```

This tells LSADeploy to inspect the existing partial rootfs and resume it when
it is safe to do so.

Do not manually delete `/data/local/linux` just because a rootfs installation
was interrupted.

# INSTALL LOCATION

The main installed components are placed at:

```
/data/local/RootStart
```

and:

```
/data/data/com.termux/files/home/NonRootStart
```

The Debian rootfs is normally located at:

```
/data/local/linux
```

You do not need to manually copy files into these locations. `deploy.sh`
handles the installation.

# AFTER INSTALLATION

When the installation completes successfully, LSA should have:

* NonRootStart installed
* RootStart installed
* Debian installed
* Device capabilities detected
* Compatible backends selected
* The LSA stack started

You can inspect the platform with:

```
lsectl report --verbose
```

This report is useful for checking which hardware and services LSA was able to
expose on the current phone.

Before treating a phone as safe for generic Linux root operations, run:

```
lsectl containment
```

This is a read-only qualification. `NOT_QUALIFIED` keeps normal LSA hardware
providers available, but means generic `sudo`, package transactions, and
privileged system D-Bus activation must remain disabled.

# BACKEND FALLBACK

LSA automatically chooses the best working implementation available for each
subsystem.

If a specific backend is known to malfunction on your device, you can prevent
LSA from selecting it with:

```
lsectl reject <backend-id>
```

To allow that backend again:

```
lsectl accept <backend-id>
```

The rejection setting is persistent and is preserved when LSA is redeployed.

This feature is primarily intended for troubleshooting and compatibility
testing. Most users should leave backend selection automatic.

# UPGRADING LSA

To install a newer LSADeploy release:

1. Download the new LSADeploy package.
2. Extract it into a new directory.
3. Enter a root shell.
4. Run:

```
./deploy.sh
```

The deployer handles replacement of the installed LSA payload.

Existing installation data that must survive deployment, including persistent
backend rejection policy, is preserved by the deployer.

Do not manually merge old and new RootStart or NonRootStart directories.

# IF INSTALLATION FAILS

First, read the error printed by `deploy.sh`.

LSA tries to report the specific component or capability that failed rather
than treating every unsupported device feature as a complete installation
failure.

Useful checks include:

```
lsectl report --verbose
```

If the failure occurred while creating Debian, try:

```
./deploy.sh resume-rootfs
```

If a particular backend is repeatedly failing while another implementation is
available, it can be rejected with:

```
lsectl reject <backend-id>
```

and LSA will attempt the next compatible backend.

When reporting a problem, include:

* Phone model
* Android version
* Kernel version
* The installer error
* Output from:

```
lsectl report --verbose
```

# IMPORTANT

LSA is experimental low-level system software intended for rooted Android
devices.

Keep backups of important data before experimenting with rooted system
software.

Do not manually remove LSA mounts, runtime files, or Android hardware
interfaces unless you understand their ownership. Use the LSA lifecycle and
deployment tools whenever possible.

# PROJECT

Linux Subsystem on Android:

https://github.com/Phsphorus/LinuxSubsystemOnAndroid

LSA-X11:

https://github.com/Phsphorus/lsa-x11

# LICENSING

LSA-authored software is licensed under Apache-2.0.

Third-party and separately licensed components retain their respective
licenses.

Licensing, source correspondence, checksums, and redistribution information
are available in:

```
LICENSE
NOTICE
THIRD_PARTY_NOTICES.md
SOURCE_AVAILABILITY.md
LICENSES/
manifest/SOURCES.tsv
manifest/LSA-X11-BUILD.tsv
```
