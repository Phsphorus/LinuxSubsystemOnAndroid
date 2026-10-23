#!/data/data/com.termux/files/usr/bin/python
"""Run LSA's system D-Bus in a private mount namespace with a suid rootfs clone.

This exists for Android kernels where the Debian rootfs inherits Android's
``nosuid`` /data mount.  The regular desktop keeps that mount nosuid.  Only
the LSA-owned system D-Bus process and the services it activates see a cloned
rootfs with the inherited child mounts and setuid enabled.

It is deliberately a fixed-purpose launcher: callers cannot choose an
executable, user, or command line.  It is not a generic privilege interface.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
import re
import shutil
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

MS_RDONLY = 1
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MS_REMOUNT = 32
MS_NOATIME = 1024
MS_NODIRATIME = 2048
MS_BIND = 4096
MS_MOVE = 8192
MS_REC = 16384
MS_PRIVATE = 1 << 18
MS_RELATIME = 2_097_152
ST_NOSUID = 2
CLONE_NEWNS = 0x00020000
PR_SET_PDEATHSIG = 1

LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.mount.argtypes = [
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_ulong,
    ctypes.c_char_p,
]
LIBC.mount.restype = ctypes.c_int
LIBC.umount2.argtypes = [ctypes.c_char_p, ctypes.c_int]
LIBC.umount2.restype = ctypes.c_int
LIBC.unshare.argtypes = [ctypes.c_int]
LIBC.unshare.restype = ctypes.c_int
LIBC.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
LIBC.prctl.restype = ctypes.c_int


def _bytes(value: str | None) -> bytes | None:
    return None if value is None else os.fsencode(value)


def mount(source: str | None, target: str, flags: int) -> None:
    if LIBC.mount(_bytes(source), _bytes(target), None, flags, None) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), target)


def unmount(target: str) -> None:
    if LIBC.umount2(_bytes(target), 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), target)


def unescape_mount_path(value: str) -> str:
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


@dataclass(frozen=True)
class MountRow:
    mount_id: int
    point: str
    options: str


def mount_rows() -> list[MountRow]:
    rows: list[MountRow] = []
    with open("/proc/self/mountinfo", encoding="utf-8") as mountinfo:
        for line in mountinfo:
            parts = line.split()
            if len(parts) < 6:
                continue
            try:
                rows.append(MountRow(int(parts[0]), unescape_mount_path(parts[4]), parts[5]))
            except ValueError:
                continue
    return rows


def top_mount(path: str) -> MountRow:
    candidates = [row for row in mount_rows() if row.point == path]
    if not candidates:
        raise RuntimeError(f"mount point is missing: {path}")
    return max(candidates, key=lambda row: row.mount_id)


def rootfs_child_mounts(rootfs: str) -> list[str]:
    prefix = rootfs.rstrip("/") + "/"
    children = {row.point for row in mount_rows() if row.point.startswith(prefix)}
    return sorted(children, key=lambda path: (path.count("/"), path))


def remount_bind_flags(options: str, locked: bool) -> int:
    option_set = set(options.split(","))
    flags = MS_REMOUNT | MS_BIND
    for name, flag in (
        ("ro", MS_RDONLY),
        ("nodev", MS_NODEV),
        ("noexec", MS_NOEXEC),
        ("noatime", MS_NOATIME),
        ("nodiratime", MS_NODIRATIME),
        ("relatime", MS_RELATIME),
    ):
        if name in option_set:
            flags |= flag
    if locked:
        flags |= MS_NOSUID
    return flags


class RootfsLease:
    """Clone a rootfs plus its mounted children, then restore it on close."""

    def __init__(self, rootfs: str, stage_root: str, write_log) -> None:
        self.rootfs = os.path.realpath(rootfs)
        self.stage_root = os.path.realpath(stage_root)
        self.write_log = write_log
        self.child_mounts: list[str] = []
        self.root_options = ""
        self.unlocked = False

    def _stage_is_mounted(self) -> bool:
        return any(row.point == self.stage_root for row in mount_rows())

    def _prepare_stage(self) -> None:
        if self._stage_is_mounted():
            raise RuntimeError(f"stale D-Bus stage mount: {self.stage_root}")
        if os.path.lexists(self.stage_root):
            if not os.path.isdir(self.stage_root):
                raise RuntimeError(f"D-Bus stage is not a directory: {self.stage_root}")
            shutil.rmtree(self.stage_root)
        os.makedirs(self.stage_root, mode=0o700)
        os.chmod(self.stage_root, 0o700)

    def _remove_stage_directory(self) -> None:
        if os.path.isdir(self.stage_root) and not self._stage_is_mounted():
            shutil.rmtree(self.stage_root, ignore_errors=True)

    def _stage_target(self, source: str) -> str:
        return self.stage_root + source[len(self.rootfs) :]

    def _root_target(self, source: str) -> str:
        return self.rootfs + source[len(self.rootfs) :]

    def _rollback_stage(self, created: Iterable[str]) -> None:
        for target in sorted(created, key=lambda path: (path.count("/"), path), reverse=True):
            try:
                unmount(target)
            except OSError:
                pass
        self._remove_stage_directory()

    def unlock(self) -> None:
        self._prepare_stage()
        created = [self.stage_root]
        moved = False
        self.child_mounts = rootfs_child_mounts(self.rootfs)
        try:
            mount(self.rootfs, self.stage_root, MS_BIND)
            for source in self.child_mounts:
                target = self._stage_target(source)
                os.makedirs(target, mode=0o755, exist_ok=True)
                mount(source, target, MS_BIND)
                created.append(target)
            self.root_options = top_mount(self.stage_root).options
            mount(None, self.stage_root, remount_bind_flags(self.root_options, locked=False))
            if os.statvfs(self.stage_root).f_flag & ST_NOSUID:
                raise RuntimeError("D-Bus rootfs clone remained nosuid")
            mount(self.stage_root, self.rootfs, MS_MOVE)
            moved = True
            if os.statvfs(self.rootfs).f_flag & ST_NOSUID:
                raise RuntimeError("D-Bus rootfs clone remained nosuid after move")
        except Exception:
            if moved:
                self.relock_after_failure()
            else:
                self._rollback_stage(created)
            raise
        self.unlocked = True
        self.write_log(f"started private suid rootfs clone; child_mounts={len(self.child_mounts)}")

    def relock_after_failure(self) -> None:
        try:
            mount(None, self.rootfs, remount_bind_flags(self.root_options, locked=True))
        except OSError as error:
            self.write_log(f"CRITICAL: unable to relock private rootfs clone: {error}")

    def lock(self) -> None:
        if not self.unlocked:
            return
        try:
            for source in reversed(self.child_mounts):
                unmount(self._root_target(source))
            unmount(self.rootfs)
        except OSError as error:
            self.relock_after_failure()
            raise RuntimeError(f"could not close D-Bus rootfs clone: {error}") from error
        finally:
            self.unlocked = False
        self.child_mounts = []
        self.root_options = ""
        self._remove_stage_directory()
        if not (os.statvfs(self.rootfs).f_flag & ST_NOSUID):
            raise RuntimeError("D-Bus rootfs did not return to nosuid")
        self.write_log("closed private suid rootfs clone; normal rootfs remains nosuid")


class SystemBusLauncher:
    def __init__(self, arguments: argparse.Namespace) -> None:
        self.arguments = arguments
        self.stop_requested = False
        self.child_pid: int | None = None
        self.lease: RootfsLease | None = None

    def log(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"{timestamp} lsa-system-dbus: {message}", file=sys.stderr, flush=True)

    def request_stop(self, signal_number, _frame) -> None:
        self.stop_requested = True
        self.log(f"received signal {signal_number}; stopping system bus")
        if self.child_pid is not None:
            try:
                os.killpg(self.child_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def _start_child(self) -> int:
        child_pid = os.fork()
        if child_pid != 0:
            return child_pid
        try:
            os.setsid()
            os.chroot(self.arguments.rootfs)
            os.chdir("/")
            environment = {
                "HOME": "/",
                "LANG": "C.UTF-8",
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            }
            os.execve(
                "/usr/bin/dbus-daemon",
                ["/usr/bin/dbus-daemon", "--system", "--nofork", "--nopidfile"],
                environment,
            )
        except BaseException as error:
            try:
                os.write(2, f"lsa-system-dbus: launch failed: {error}\n".encode("utf-8", "replace"))
            except OSError:
                pass
        os._exit(127)

    @staticmethod
    def _process_start_time(pid: int) -> str | None:
        try:
            stat_line = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
            # comm may contain spaces and parentheses. Everything after the
            # final closing parenthesis starts at field 3; starttime is field 22.
            fields = stat_line.rsplit(")", 1)[1].split()
            return fields[19]
        except (FileNotFoundError, IndexError, ValueError):
            return None

    def _wait_for_child(self, owner_start_time: str) -> int:
        assert self.child_pid is not None
        while True:
            try:
                finished, status = os.waitpid(self.child_pid, os.WNOHANG)
            except ChildProcessError:
                return 1
            if finished == self.child_pid:
                if os.WIFEXITED(status):
                    return os.WEXITSTATUS(status)
                if os.WIFSIGNALED(status):
                    return 128 + os.WTERMSIG(status)
                return 1
            if self._process_start_time(self.arguments.owner_pid) != owner_start_time:
                self.log("owning ModChroot supervisor exited; stopping system bus")
                self.request_stop(signal.SIGTERM, None)
            time.sleep(0.1)

    def run(self) -> int:
        if os.geteuid() != 0:
            self.log("must be started by RootStart as Android root")
            return 77
        owner_start_time = self._process_start_time(self.arguments.owner_pid)
        if owner_start_time is None:
            self.log(f"owning ModChroot supervisor is unavailable: {self.arguments.owner_pid}")
            return 78
        # During normal boot this launcher is a direct child of ModChroot, so
        # the kernel can stop it immediately. A live repair may enter the same
        # mount namespace through a transient shell; the explicit owner watch
        # below preserves the same lifecycle without binding it to that shell.
        if os.getppid() == self.arguments.owner_pid:
            if LIBC.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), "PR_SET_PDEATHSIG")
        if LIBC.unshare(CLONE_NEWNS) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), "CLONE_NEWNS")
        mount(None, "/", MS_REC | MS_PRIVATE)
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        self.lease = RootfsLease(self.arguments.rootfs, self.arguments.stage_root, self.log)
        try:
            self.lease.unlock()
            self.child_pid = self._start_child()
            self.log(f"system D-Bus started pid={self.child_pid}")
            status = self._wait_for_child(owner_start_time)
            self.log(f"system D-Bus exited status={status}")
            return status
        finally:
            if self.child_pid is not None:
                try:
                    os.killpg(self.child_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(self.child_pid, 0)
                except ChildProcessError:
                    pass
            if self.lease is not None:
                self.lease.lock()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs", required=True)
    parser.add_argument("--stage-root", required=True)
    parser.add_argument("--owner-pid", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    return SystemBusLauncher(parse_arguments()).run()


if __name__ == "__main__":
    raise SystemExit(main())
