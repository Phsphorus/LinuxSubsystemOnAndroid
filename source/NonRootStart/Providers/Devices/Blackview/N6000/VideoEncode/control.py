#!/data/data/com.termux/files/usr/bin/python
"""Root-safe client for the Termux-user N6000 video provider control socket."""

from __future__ import annotations

import argparse
import socket
from pathlib import Path


# Must match the short Termux-user endpoint chosen by manager.py. The caller
# may be RootStart, so deriving this from the caller's HOME would be wrong.
CONTROL_SOCKET = Path("/data/data/com.termux/files/home/.lsa-n6000-video-control.sock")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("start", "stop", "status", "shutdown"))
    args = parser.parse_args()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(20)
            connection.connect(str(CONTROL_SOCKET))
            connection.sendall((args.command + "\n").encode("utf-8"))
            response = connection.recv(4096).decode("utf-8", "replace").strip()
    except OSError as exc:
        print(f"ERR provider unavailable: {exc}")
        return 1
    print(response)
    return 0 if response.startswith("OK ") else 1


if __name__ == "__main__":
    raise SystemExit(main())
