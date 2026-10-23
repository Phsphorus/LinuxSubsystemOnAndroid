#!/data/data/com.termux/files/usr/bin/python
"""Deliberately unsafe, explicitly leased sudo compatibility for LSA.

This process runs only in RootStart's private *mount* namespace.  It never
remounts Android's host /data filesystem.  A confirmed Debian user can lease a
temporary rootfs clone with suid enabled; closing the lease removes that clone
and exposes the normal nosuid rootfs again.

This is intentionally not a privilege boundary.  The target devices do not
have the user/PID/capability containment required to make generic sudo safe.
It is an opt-in developer escape hatch whose danger is made explicit by the
Debian-side sudo wrapper.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import json
import os
import pty
import re
import select
import shutil
import signal
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# linux/mount.h
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
FRAME_HEADER = struct.Struct("!cI")
MAX_FRAME_BYTES = 65536


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
LIBC.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
LIBC.prctl.restype = ctypes.c_int
LIBC.unshare.argtypes = [ctypes.c_int]
LIBC.unshare.restype = ctypes.c_int

PR_SET_PDEATHSIG = 1


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
    return re.sub(
        r"\\([0-7]{3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )


@dataclass(frozen=True)
class MountRow:
    mount_id: int
    parent_id: int
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
                rows.append(
                    MountRow(
                        mount_id=int(parts[0]),
                        parent_id=int(parts[1]),
                        point=unescape_mount_path(parts[4]),
                        options=parts[5],
                    )
                )
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
    # The rootfs is a directory on Android's /data mount, not a mount point of
    # its own.  MS_REC therefore does not copy these mounts.  Record every
    # visible child mount and clone each one explicitly, shallow to deep.
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
    """A rootfs mount clone that can be safely removed after a sudo command."""

    def __init__(self, rootfs: str, stage_root: str, write_log) -> None:
        self.rootfs = os.path.realpath(rootfs)
        self.stage_root = os.path.realpath(stage_root)
        self.write_log = write_log
        self.child_mounts: list[str] = []
        self.root_options = ""
        self.unlocked = False
        self.faulted = False

    def _stage_is_mounted(self) -> bool:
        return any(row.point == self.stage_root for row in mount_rows())

    def _prepare_stage(self) -> None:
        if self._stage_is_mounted():
            raise RuntimeError(f"refusing stale unsafe-sudo stage mount: {self.stage_root}")
        if os.path.lexists(self.stage_root):
            if not os.path.isdir(self.stage_root):
                raise RuntimeError(f"unsafe-sudo stage is not a directory: {self.stage_root}")
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
        if self.faulted:
            raise RuntimeError("unsafe-sudo lease is faulted; restart the LSA stack")
        if self.unlocked:
            raise RuntimeError("unsafe-sudo lease is already open")

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
                raise RuntimeError("unsafe-sudo rootfs clone remained nosuid")

            mount(self.stage_root, self.rootfs, MS_MOVE)
            moved = True
            if os.statvfs(self.rootfs).f_flag & ST_NOSUID:
                raise RuntimeError("unsafe-sudo moved rootfs remained nosuid")
        except Exception:
            if moved:
                self._lock_overlay_after_failure()
            else:
                self._rollback_stage(created)
            raise

        self.unlocked = True
        self.write_log(
            f"command namespace cloned rootfs={self.rootfs} child_mounts={len(self.child_mounts)}"
        )

    def _lock_overlay_after_failure(self) -> None:
        """Make a partially removed overlay nosuid before reporting failure."""
        try:
            mount(None, self.rootfs, remount_bind_flags(self.root_options, locked=True))
        except OSError as error:
            self.write_log(f"CRITICAL: failed to relock unsafe-sudo overlay: {error}")
        self.faulted = True

    def lock(self) -> None:
        if not self.unlocked:
            return

        try:
            # Every path is a mount we created.  Removing leaves first exposes
            # the original child mount below it without unmounting that original
            # mount, then removing the root clone exposes the Android nosuid
            # rootfs again.
            for source in reversed(self.child_mounts):
                unmount(self._root_target(source))
            unmount(self.rootfs)
        except OSError as error:
            self._lock_overlay_after_failure()
            self.unlocked = False
            self.write_log(f"lease close failed; suid overlay was relocked: {error}")
            raise RuntimeError(f"could not remove unsafe-sudo overlay: {error}") from error

        self.unlocked = False
        self.child_mounts = []
        self.root_options = ""
        self._remove_stage_directory()
        if not (os.statvfs(self.rootfs).f_flag & ST_NOSUID):
            self.faulted = True
            raise RuntimeError("unsafe-sudo rootfs did not return to nosuid")
        self.write_log("command namespace clone closed; rootfs nosuid restored")


class UnsafeSudoDaemon:
    """Run one confirmed sudo command in a disposable mount namespace."""

    def __init__(self, arguments: argparse.Namespace) -> None:
        self.arguments = arguments
        self.stop_event = threading.Event()
        self.listener: socket.socket | None = None
        self.child_pid: int | None = None

    def log(self, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(self.arguments.log_file, "a", encoding="utf-8") as log_file:
            os.fchmod(log_file.fileno(), 0o600)
            log_file.write(f"{timestamp} unsafe-sudo: {message}\n")

    def _write_pid(self) -> None:
        Path(self.arguments.pid_file).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open(self.arguments.pid_file, "w", encoding="ascii") as pid_file:
            os.fchmod(pid_file.fileno(), 0o600)
            pid_file.write(f"{os.getpid()}\n")

    def _prepare_socket(self) -> socket.socket:
        parent = os.path.dirname(self.arguments.socket_path)
        os.makedirs(parent, mode=0o750, exist_ok=True)
        os.chown(parent, 0, self.arguments.allowed_gid)
        os.chmod(parent, 0o750)
        try:
            details = os.lstat(self.arguments.socket_path)
        except FileNotFoundError:
            details = None
        if details is not None:
            if not stat_is_socket(details.st_mode):
                raise RuntimeError(f"refusing non-socket control path: {self.arguments.socket_path}")
            os.unlink(self.arguments.socket_path)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(self.arguments.socket_path)
        os.chown(self.arguments.socket_path, 0, self.arguments.allowed_gid)
        os.chmod(self.arguments.socket_path, 0o660)
        listener.listen(4)
        listener.settimeout(1.0)
        return listener

    def _owner_is_alive(self) -> bool:
        """Verify the ModChroot instance that explicitly owns this daemon.

        A PID alone is not sufficient because Android can reuse it.  The
        start tick from /proc/<pid>/stat identifies the exact ModChroot
        process that requested this daemon.  This permits a controlled module
        restart without accidentally tying the daemon to a short-lived helper
        shell, while still removing the opt-in sudo path when LSA stops.
        """
        try:
            stat = Path(f"/proc/{self.arguments.owner_pid}/stat").read_text(encoding="ascii")
            _prefix, values = stat.rsplit(")", 1)
            fields = values.split()
            state = fields[0]
            start_ticks = int(fields[19])
        except (FileNotFoundError, IndexError, OSError, ValueError):
            return False
        return state != "Z" and start_ticks == self.arguments.owner_start_ticks

    def _read_command(self, connection: socket.socket) -> list[str]:
        connection.settimeout(5.0)
        request = b""
        while not request.endswith(b"\n"):
            block = connection.recv(4096)
            if not block:
                raise RuntimeError("client closed before request")
            request += block
            if len(request) > 16384:
                raise RuntimeError("request is too large")
        if not request.startswith(b"EXEC "):
            raise RuntimeError("unsupported protocol request")
        try:
            arguments = json.loads(request[5:-1].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("invalid command arguments") from error
        if not isinstance(arguments, list) or len(arguments) > 128:
            raise RuntimeError("invalid command argument list")
        if any(not isinstance(value, str) or "\x00" in value for value in arguments):
            raise RuntimeError("invalid command argument")
        if sum(len(value.encode("utf-8")) for value in arguments) > 12000:
            raise RuntimeError("command arguments are too large")
        return arguments

    @staticmethod
    def _send_frame(connection: socket.socket, kind: bytes, payload: bytes) -> None:
        connection.sendall(FRAME_HEADER.pack(kind, len(payload)) + payload)

    @staticmethod
    def _status_code(status: int) -> int:
        if os.WIFEXITED(status):
            return os.WEXITSTATUS(status)
        if os.WIFSIGNALED(status):
            return 128 + os.WTERMSIG(status)
        return 1

    def _peer_working_directory(self, peer_pid: int) -> str:
        """Return the peer's cwd expressed inside the Debian rootfs.

        The Unix-socket peer credential gives us the PID of lsudo-run.py, so
        this does not trust a caller-supplied path.  Read the directory before
        the disposable clone replaces the rootfs mount, and accept it only if
        its resolved host path is inside the configured rootfs.
        """
        rootfs = os.path.realpath(self.arguments.rootfs)
        try:
            peer_cwd = os.path.realpath(os.readlink(f"/proc/{peer_pid}/cwd"))
        except OSError as error:
            self.log(f"could not read peer cwd pid={peer_pid}: {error}; using /")
            return "/"

        if peer_cwd == rootfs:
            return "/"
        prefix = rootfs + os.sep
        if not peer_cwd.startswith(prefix):
            self.log(f"peer cwd is outside Debian rootfs pid={peer_pid}; using /")
            return "/"
        return peer_cwd[len(rootfs) :]

    def _child_exec(self, slave_fd: int, command: list[str], working_directory: str) -> None:
        try:
            if LIBC.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), "PR_SET_PDEATHSIG")
            if LIBC.unshare(CLONE_NEWNS) != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), "CLONE_NEWNS")
            mount(None, "/", MS_REC | MS_PRIVATE)

            # The temporary suid clone exists only in this fork's new mount
            # namespace.  It vanishes automatically when the sudo process
            # exits; the desktop/session namespace remains nosuid throughout.
            lease = RootfsLease(
                self.arguments.rootfs,
                f"{self.arguments.stage_root}.job-{os.getpid()}",
                self.log,
            )
            lease.unlock()
            os.chroot(self.arguments.rootfs)
            try:
                os.chdir(working_directory)
            except OSError as error:
                self.log(f"could not restore peer cwd {working_directory!r}: {error}; using /")
                os.chdir("/")

            os.setsid()
            import fcntl
            import termios

            fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
            for descriptor in (0, 1, 2):
                os.dup2(slave_fd, descriptor)
            if slave_fd > 2:
                os.close(slave_fd)

            os.setgroups(self.arguments.run_groups)
            os.setgid(self.arguments.allowed_gid)
            os.setuid(self.arguments.allowed_uid)
            environment = {
                "HOME": f"/home/{self.arguments.run_user}",
                "LOGNAME": self.arguments.run_user,
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "SHELL": "/bin/bash",
                "TERM": "xterm-256color",
                "USER": self.arguments.run_user,
            }
            # -S lets sudo use the relay PTY for its normal password prompt,
            # rather than requiring the daemon itself to own a terminal.
            os.execve("/usr/bin/sudo", ["/usr/bin/sudo", "-S", *command], environment)
        except BaseException as error:
            try:
                os.write(2, f"sudo: unsafe compatibility launch failed: {error}\n".encode("utf-8", "replace"))
            except OSError:
                pass
            os._exit(127)

    def _run_command(self, connection: socket.socket, command: list[str], working_directory: str) -> None:
        master_fd, slave_fd = pty.openpty()
        child_pid = os.fork()
        if child_pid == 0:
            try:
                connection.close()
                os.close(master_fd)
                self._child_exec(slave_fd, command, working_directory)
            finally:
                os._exit(127)

        os.close(slave_fd)
        self.child_pid = child_pid
        os.set_blocking(master_fd, False)
        connection.settimeout(None)
        receive_buffer = b""
        pending_input = b""
        child_status: int | None = None
        client_open = True
        master_open = True

        try:
            while master_open or child_status is None:
                if self.stop_event.is_set() and child_status is None:
                    try:
                        os.killpg(child_pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass

                readable = [master_fd]
                if client_open:
                    readable.append(connection)
                writable = [master_fd] if pending_input else []
                ready_read, ready_write, _ = select.select(readable, writable, [], 0.2)

                if connection in ready_read:
                    block = connection.recv(MAX_FRAME_BYTES)
                    if not block:
                        client_open = False
                        if child_status is None:
                            try:
                                os.killpg(child_pid, signal.SIGTERM)
                            except ProcessLookupError:
                                pass
                    else:
                        receive_buffer += block
                        while len(receive_buffer) >= FRAME_HEADER.size:
                            kind, length = FRAME_HEADER.unpack(receive_buffer[:FRAME_HEADER.size])
                            if length > MAX_FRAME_BYTES:
                                raise RuntimeError("client frame is too large")
                            frame_end = FRAME_HEADER.size + length
                            if len(receive_buffer) < frame_end:
                                break
                            payload = receive_buffer[FRAME_HEADER.size:frame_end]
                            receive_buffer = receive_buffer[frame_end:]
                            if kind != b"I":
                                raise RuntimeError("unsupported client frame")
                            pending_input += payload

                if master_fd in ready_write and pending_input:
                    try:
                        written = os.write(master_fd, pending_input)
                        pending_input = pending_input[written:]
                    except BlockingIOError:
                        pass

                if master_fd in ready_read:
                    try:
                        output = os.read(master_fd, MAX_FRAME_BYTES)
                    except OSError as error:
                        if error.errno == errno.EIO:
                            output = b""
                        else:
                            raise
                    if output:
                        if client_open:
                            self._send_frame(connection, b"O", output)
                    else:
                        master_open = False

                if child_status is None:
                    finished, status = os.waitpid(child_pid, os.WNOHANG)
                    if finished == child_pid:
                        child_status = status
                if child_status is not None and not master_open:
                    break

            if child_status is None:
                _finished, child_status = os.waitpid(child_pid, 0)
            if client_open:
                self._send_frame(connection, b"X", str(self._status_code(child_status)).encode("ascii"))
        finally:
            self.child_pid = None
            try:
                os.close(master_fd)
            except OSError:
                pass
            if child_status is None:
                try:
                    os.killpg(child_pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(child_pid, 0)
                except ChildProcessError:
                    pass

    def _handle_client(self, connection: socket.socket) -> None:
        with connection:
            try:
                raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
                peer_pid, peer_uid, peer_gid = struct.unpack("3i", raw)
                if peer_uid != self.arguments.allowed_uid or peer_gid != self.arguments.allowed_gid:
                    connection.sendall(b"ERR unauthorized\n")
                    return
                command = self._read_command(connection)
                working_directory = self._peer_working_directory(peer_pid)
                connection.sendall(b"READY\n")
                self.log(
                    f"command started peer_pid={peer_pid} cwd={working_directory!r} "
                    f"arguments={len(command)}"
                )
                self._run_command(connection, command, working_directory)
                self.log("command finished; disposable sudo namespace exited")
            except (ConnectionError, OSError, RuntimeError) as error:
                self.log(f"client command failed: {error}")
                try:
                    connection.sendall(b"ERR command-failed\n")
                except OSError:
                    pass

    def _request_stop(self, _signal_number, _frame) -> None:
        self.stop_event.set()
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass
        if self.child_pid is not None:
            try:
                os.killpg(self.child_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self._request_stop)
        signal.signal(signal.SIGINT, self._request_stop)
        if not self._owner_is_alive():
            raise RuntimeError("unsafe-sudo owner process is not running")
        self.listener = self._prepare_socket()
        self._write_pid()
        self.log(
            "started deliberate unsafe sudo command daemon "
            f"uid={self.arguments.allowed_uid} gid={self.arguments.allowed_gid}"
        )
        try:
            while not self.stop_event.is_set():
                try:
                    connection, _address = self.listener.accept()
                except socket.timeout:
                    if not self._owner_is_alive():
                        self.log("owner process exited; disabling unsafe sudo")
                        break
                    continue
                except OSError:
                    if self.stop_event.is_set():
                        break
                    raise
                self._handle_client(connection)
        finally:
            self.stop_event.set()
            if self.listener is not None:
                try:
                    self.listener.close()
                except OSError:
                    pass
            for path in (self.arguments.socket_path, self.arguments.pid_file):
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
            self.log("stopped")
        return 0

def stat_is_socket(mode: int) -> bool:
    return (mode & 0o170000) == 0o140000


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rootfs", required=True)
    parser.add_argument("--socket", dest="socket_path", required=True)
    parser.add_argument("--pid-file", required=True)
    parser.add_argument("--log-file", required=True)
    parser.add_argument("--stage-root", required=True)
    parser.add_argument("--allowed-uid", type=int, required=True)
    parser.add_argument("--allowed-gid", type=int, required=True)
    parser.add_argument("--run-user", required=True)
    parser.add_argument("--run-groups", required=True)
    parser.add_argument("--owner-pid", type=int, required=True)
    parser.add_argument("--owner-start-ticks", type=int, required=True)
    arguments = parser.parse_args()
    try:
        arguments.run_groups = [int(value) for value in arguments.run_groups.split(",") if value]
    except ValueError as error:
        parser.error(f"invalid --run-groups: {error}")
    if not arguments.run_groups or any(value < 0 for value in arguments.run_groups):
        parser.error("--run-groups must contain one or more nonnegative numeric GIDs")
    if arguments.owner_pid <= 1 or arguments.owner_start_ticks <= 0:
        parser.error("--owner-pid and --owner-start-ticks must identify a live process")
    return arguments


def main() -> int:
    arguments = parse_arguments()
    if os.geteuid() != 0:
        print("unsafe-sudo daemon must run as root", file=sys.stderr)
        return 77
    return UnsafeSudoDaemon(arguments).run()


if __name__ == "__main__":
    raise SystemExit(main())
