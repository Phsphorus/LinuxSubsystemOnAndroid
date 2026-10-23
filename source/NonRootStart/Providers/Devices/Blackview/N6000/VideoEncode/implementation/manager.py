#!/data/data/com.termux/files/usr/bin/python
"""Termux-user lifecycle owner for the optional N6000 H.264 GPU-tap mode."""

from __future__ import annotations

import argparse
import hashlib
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
IMPLEMENTATION = BASE / "implementation"
STATE = BASE / "state"
RUN = STATE / "run"
LOGS = STATE / "logs"
# Android's Unix-domain path limit is smaller than the provider's descriptive
# source path. Keep the runtime control endpoint short while retaining all
# generated assets and logs under the provider state directory.
CONTROL_SOCKET = Path("/data/data/com.termux/files/home/.lsa-n6000-video-control.sock")
SOURCE = IMPLEMENTATION / "gpu_tap.c"
LIBRARY = RUN / "libLSAGPUTap.so"
SOURCE_HASH = RUN / "gpu_tap.sha256"
LAUNCHER = IMPLEMENTATION / "virgl-with-video.sh"
GPU_LIFECYCLE = BASE.parents[3] / "Android" / "GPUBridge" / "lifecycle.sh"
GPU_RUN = GPU_LIFECYCLE.parent / "run"
GPU_SOCKET = GPU_RUN / ".virgl_test"
VIDEO_SOCKET = GPU_RUN / ".lsa-video"
GPU_MODE = GPU_RUN / "mode"
CLANG = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr")) / "bin" / "clang"


def message(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stdout + result.stderr).strip().replace("\n", " | ")
    return text[:2048]


def run_gpu(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(GPU_LIFECYCLE), *arguments],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def video_active() -> bool:
    try:
        mode = GPU_MODE.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return mode == "video" and GPU_SOCKET.is_socket() and VIDEO_SOCKET.is_socket()


def build_tap() -> tuple[bool, str]:
    if not SOURCE.is_file():
        return False, f"GPU tap source missing: {SOURCE}"
    if not CLANG.is_file():
        return False, f"Termux clang missing: {CLANG}"
    RUN.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    try:
        installed = SOURCE_HASH.read_text(encoding="utf-8").strip()
    except OSError:
        installed = ""
    if LIBRARY.is_file() and installed == digest:
        return True, "GPU tap library is current"

    candidate = RUN / "libLSAGPUTap.so.new"
    candidate.unlink(missing_ok=True)
    result = subprocess.run(
        [
            str(CLANG),
            "-shared",
            "-fPIC",
            "-O2",
            "-o",
            str(candidate),
            str(SOURCE),
            "-ldl",
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        candidate.unlink(missing_ok=True)
        return False, f"GPU tap build failed: {message(result)}"
    os.replace(candidate, LIBRARY)
    SOURCE_HASH.write_text(digest + "\n", encoding="utf-8")
    os.chmod(LIBRARY, 0o755)
    return True, "GPU tap library built from canonical device-provider source"


def start_video() -> tuple[bool, str]:
    if video_active():
        return True, "N6000 H.264 video mode is already active"
    ok, detail = build_tap()
    if not ok:
        return False, detail
    result = run_gpu("video-start", str(LAUNCHER))
    if result.returncode == 0 and video_active():
        return True, "N6000 H.264 video mode is active"

    # A failed optional activation must not strand the generic provider.
    recovery = run_gpu("start")
    suffix = f"; generic recovery: {message(recovery)}" if recovery.returncode else ""
    return False, f"GPU video mode did not become ready: {message(result)}{suffix}"


def stop_video() -> tuple[bool, str]:
    if not video_active():
        return True, "N6000 H.264 video mode is already stopped"
    result = run_gpu("video-stop")
    if result.returncode:
        return False, f"GPU video mode stop failed: {message(result)}"
    if VIDEO_SOCKET.exists():
        return False, "GPU video-tap socket remains after stop"
    if not GPU_SOCKET.is_socket():
        return False, "generic VirGL socket did not return after video stop"
    return True, "N6000 H.264 video mode stopped; generic VirGL restored"


def status() -> tuple[bool, str]:
    return True, "RUNNING" if video_active() else "STOPPED"


def handle(command: str) -> tuple[bool, str, bool]:
    if command == "start":
        ok, detail = start_video()
        return ok, detail, False
    if command == "stop":
        ok, detail = stop_video()
        return ok, detail, False
    if command == "status":
        ok, detail = status()
        return ok, detail, False
    if command == "shutdown":
        # NonRootStart shutdown owns final provider cleanup. Leave a generic
        # server only long enough for its normal provider stop to run next.
        ok, detail = stop_video()
        return ok, detail, True
    return False, "unsupported control command", False


def serve() -> int:
    RUN.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    CONTROL_SOCKET.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(CONTROL_SOCKET))
    os.chmod(CONTROL_SOCKET, 0o600)
    server.listen(4)
    running = True

    def stop_signal(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False
        server.close()

    signal.signal(signal.SIGTERM, stop_signal)
    signal.signal(signal.SIGINT, stop_signal)
    try:
        while running:
            try:
                connection, _ = server.accept()
            except OSError:
                break
            with connection:
                command = connection.recv(128).decode("utf-8", "replace").strip()
                ok, detail, shutdown = handle(command)
                connection.sendall(("OK " if ok else "ERR ").encode("utf-8") + detail.encode("utf-8", "replace") + b"\n")
                if shutdown:
                    running = False
    finally:
        server.close()
        CONTROL_SOCKET.unlink(missing_ok=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("serve",))
    args = parser.parse_args()
    return serve() if args.command == "serve" else 2


if __name__ == "__main__":
    raise SystemExit(main())
