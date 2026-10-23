# LSA security boundary

LSA targets rooted Android with SELinux **Enforcing**.  `RootStart` never
executes `setenforce 0`; a host that is already Permissive is reported as such
and remains an explicit development condition, not an LSA fallback.

## Release invariants

- HALAgent state is `0711`; its secret directory is `0700`; its secret is
  `0600` from creation and is corrected at service start.
- No device secret, runtime socket, PID, log, or Python bytecode is included
  in a release payload.
- HALAgent does not log unauthenticated request text.  It bounds requests to
  4096 bytes, applies a five-second client timeout, and limits concurrent
  unauthenticated clients to 16.
- Root launchers use an explicit command path and clear inherited linker and
  Python overrides before starting privileged components.
- LSA's root-private state directories are owner-only.  Android shared media
  staging is distinct from the HAL state tree.
- The release builder rejects an automatic SELinux downgrade, the historical
  world-readable secret mode, raw pre-auth request logging, traversal archive
  members, and runtime artifacts in payloads.

## SELinux policy

LSA first prefers normal Unix ownership, a narrower provider, Android's
framework/HAL, or a fallback backend.  Policy extension is considered only
after an AVC denial has been tied to a necessary operation.  A generated
`audit2allow` rule is never production policy by itself; broad allow rules and
domain-wide permissive settings are prohibited.

`lsectl report` includes the current host SELinux mode.  Detailed AVC evidence
belongs in device diagnostics, together with source context, target context,
class, permission, operation, and the chosen remediation.

## Generic-root containment

`sudo` and arbitrary package-maintainer scripts are not baseline LSA
features. They are enabled only in a runtime that passes `lsectl containment
[candidate-pid]`.

The LSA-owned system D-Bus is different: it is a fixed-purpose launcher for
`dbus-daemon` and registered system services, with the standard D-Bus policy
as its authorization boundary. On an Android-backed `nosuid` rootfs it runs in
its own private `suid` clone; the desktop and normal Linux-user processes keep
their `nosuid` rootfs. It never accepts a caller-provided executable, user,
or argument list.

The command is read-only. It writes `containment.tsv`, `containment-mounts.tsv`,
and `containment-fds.tsv` beside the normal framework state. The candidate must
have a user namespace distinct from Android init, map its UID 0 to a nonzero
host UID, use separate mount and PID namespaces, omit host-escape capabilities
from its capability bounding set, hide raw Android `/dev`, keep sysfs read-only
or absent, avoid inherited host descriptors, and expose a `suid` rootfs only
after those checks pass.

If any check fails, the result is `NOT_QUALIFIED`. That device remains in the
safe LSA mode: Linux applications use LSA hardware interfaces as `myuser`, and
RootStart performs only source-owned, allowlisted privileged operations.

## Unsafe sudo developer escape hatch

Some rooted phones, including the N6000, cannot provide generic Linux root
without exposing Android-host root.  `UnsafeSudo` is an operator-approved
exception for development, not a release invariant or a provider.  It is off
unless `UNSAFE_SUDO_ENABLE=1` is set in ModChroot configuration.

When enabled, `sudo` requires the exact terminal acknowledgement `I WILL NOT
BE STOPPED`.  RootStart then starts the real sudo command in a new disposable
mount namespace and chroot.  Only that command namespace receives the
temporary `suid` rootfs clone.  The daemon copies all visible rootfs child
mounts so the normal private `/dev`, `/dev/pts`, GPU/HAL bridge mounts, and
shared storage remain usable; all of those mounts disappear with the command
process.  The normal desktop namespace remains `nosuid`.

This makes generic setuid programs functional only inside that command
namespace.  It does not protect Android from the resulting root process.  The
confirmation text, local socket UID/GID check, and structured protocol prevent
accidental use; a local process running as the confirmed Linux user can still
reproduce the protocol, so they do not form a containment boundary.  Do not
enable it for users or devices that require LSA's normal safety model.
