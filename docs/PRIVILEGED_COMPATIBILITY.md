# Privileged compatibility on Android-backed root filesystems

## N6000 finding

The Debian rootfs at `/data/local/linux` is a directory on Android's `/data`
filesystem. Android mounts that backing filesystem with `nosuid`. LSA does not
add `nosuid` to the rootfs itself. Its deliberately private mounts are limited
to `/dev`, shared memory, and Android bridge mounts.

This has two separate effects:

- `/usr/bin/sudo` retains mode `4755` and ownership `root:root`, but cannot
  acquire effective UID 0 for a Linux user.
- `/usr/lib/dbus-1.0/dbus-daemon-launch-helper` retains the required
  `root:messagebus` ownership and `4754` mode, but cannot acquire effective UID
  0 when it runs from the normal system-bus mount namespace. LSA therefore
  starts its fixed-purpose system D-Bus daemon in a separate private mount
  namespace with a `suid` clone of the rootfs and its existing child mounts.
  The normal desktop rootfs remains `nosuid`.

The N6000 first reproduced the D-Bus failure as
`org.freedesktop.DBus.Error.Spawn.PermissionsInvalid`. The private bus clone
then completed `StartServiceByName(org.freedesktop.PackageKit)` with result
`uint32 1`, and PackageKit claimed its service name. `NoNewPrivs` and Seccomp
were zero, so neither is the cause.

## Why ordinary `sudo` remains unsafe

A disposable private mount-namespace probe proved that Android permits a bind
mount of the rootfs to be remounted `suid` without changing the host `/data`
mount. That only establishes technical feasibility; it is not an acceptable
LSA compatibility mode.

LSA currently creates a new *mount* namespace only. It does not create a user
namespace. The N6000 LSA root process retains Android's full capability set,
including `CAP_SETUID`, `CAP_SETGID`, `CAP_SYS_ADMIN`, and `CAP_SYS_CHROOT`.
Making a Debian setuid-root program effective would therefore risk giving an
unprivileged Debian account Android-host root authority. A rootfs-only bind
mount avoids changing Android globally, but does not create the privilege
boundary that would make generic `sudo` safe.

LSA never remounts Android's `/data` filesystem globally. The default desktop
rootfs state remains `nosuid`. A long-lived private `suid` clone is permitted
only for the fixed system D-Bus daemon while LSA owns that daemon; it is removed
when the daemon or its ModChroot owner exits.

## Default supported direction

LSA keeps the default Android `nosuid` boundary. Privileged work has to be
expressed as a narrow LSA operation instead of a generic Unix root shell.

1. LSA-owned privileged services are started by RootStart from a source-owned
   registry. The LSA system D-Bus may also activate registered Debian services
   through its normal policy, but only from its fixed-purpose private clone.
2. A future RootStart privileged-service broker may accept only a fixed service
   identifier and fixed lifecycle action. It must authenticate the local peer,
   reject arbitrary executable paths, arguments, environment values, and users,
   and record every request.
3. A future `lsa-admin` interface may expose similarly allowlisted LSA
   maintenance operations. It is not a replacement `sudo` command and must not
   execute caller-supplied shell text.
4. Generic `sudo` remains unavailable unless `lsectl containment` returns
   `QUALIFIED`. The check requires an actual UID boundary, separate mount and
   PID namespaces, a restricted capability bounding set, no raw host-device or
   writable host mounts, no inherited host descriptors, and a rootfs whose
   `suid` state is only enabled after those boundaries exist.

## Explicit unsafe developer mode

The N6000 configuration can enable `UnsafeSudo` only after the operator has
chosen this risk.  `/usr/local/bin/sudo` prints a warning and requires the
exact interactive acknowledgement `I WILL NOT BE STOPPED`.  It then asks a
RootStart-owned daemon to start the real `/usr/bin/sudo` in a new,
per-command mount namespace and chroot.  That namespace receives a temporary
`suid` clone of the Debian rootfs, including the existing private `/dev`,
`/dev/pts`, bridge, and shared-storage submounts.  The clone disappears with
the command process; the desktop/session namespace remains `nosuid` before,
during, and after the command.

This is **not** true sudo isolation.  A successful setuid transition retains
the Android-root capabilities held by RootStart's mount namespace.  The socket
checks the local Linux UID/GID and accepts a structured `EXEC` argument list,
but the confirmed user can reproduce that protocol without the wrapper's
warning.  It is therefore an accidental-use guard, not a security boundary.
Use an LSA provider for normal hardware or maintenance work.  Enable this mode
only for an operator who understands and deliberately accepts Android-host
root consequences.

## Acceptance checks

- A normal `dbus-send --system ... ListNames` call continues to work as
  `myuser`.
- With a `nosuid` desktop rootfs, the D-Bus module reports `RUNNING` only when
  its LSA-owned daemon is in a private `suid` clone.
- A registered system service can be activated through the standard D-Bus
  policy; on the N6000, `StartServiceByName(org.freedesktop.PackageKit)` must
  return `uint32 1` or `uint32 2`, never `Spawn.PermissionsInvalid`.
- The D-Bus launcher accepts no custom executable, argument, user, or service
  bypass outside the standard system-bus configuration.
- The Android `/data` mount options, the rootfs `statvfs` `ST_NOSUID` flag, and
  the private `/dev` `nosuid` flag are unchanged before and after every test.
- With unsafe developer mode disabled, a direct `sudo -n true` remains
  unavailable to `myuser`.
- With unsafe developer mode enabled, the wrapper rejects noninteractive use,
  accepts only the exact acknowledgement at a terminal, and leaves the normal
  desktop rootfs `ST_NOSUID` plus every private child mount unchanged while
  the disposable command namespace exits.
- `lsectl containment` writes a `NOT_QUALIFIED` result and the exact failing
  mounts or descriptors on every device that does not meet the boundary.
