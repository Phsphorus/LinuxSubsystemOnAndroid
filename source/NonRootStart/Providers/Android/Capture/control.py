#!/data/data/com.termux/files/usr/bin/python
"""Control-plane client for the Termux-user Android capture provider."""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path


BASE = Path(__file__).resolve().parent
SECRET_FILE = BASE / "state" / "secret"
CONTROL_ADDRESS = ("127.0.0.1", 8766)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=("status", "camera", "location"))
    parser.add_argument("action", nargs="?", choices=("start", "stop", "status"))
    args = parser.parse_args()
    if args.target != "status" and not args.action:
        parser.error("camera and location require start, stop, or status")
    try:
        secret = SECRET_FILE.read_text(encoding="utf-8").strip()
        command = args.target if args.target == "status" else f"{args.target} {args.action}"
        with socket.create_connection(CONTROL_ADDRESS, timeout=5) as connection:
            connection.sendall(f"{secret} {command}\n".encode("utf-8"))
            response = connection.recv(8192).decode("utf-8", "replace").strip()
    except OSError as exc:
        print(f"ERR provider unavailable: {exc}")
        return 1
    print(response)
    return 0 if response.startswith("OK ") else 1


if __name__ == "__main__":
    raise SystemExit(main())
