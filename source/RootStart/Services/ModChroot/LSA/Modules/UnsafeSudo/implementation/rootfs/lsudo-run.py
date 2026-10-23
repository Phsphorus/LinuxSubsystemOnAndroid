#!/usr/bin/python3
"""Relay one confirmed unsafe sudo command to RootStart over a local socket."""

from __future__ import annotations

import argparse
import json
import os
import selectors
import socket
import struct
import sys
import termios
import tty


FRAME_HEADER = struct.Struct("!cI")
MAX_FRAME_BYTES = 65536


def receive_line(connection: socket.socket) -> str:
    buffer = bytearray()
    while not buffer.endswith(b"\n"):
        block = connection.recv(1)
        if not block:
            raise ConnectionError("unsafe sudo service closed before replying")
        buffer.extend(block)
        if len(buffer) > 256:
            raise ConnectionError("unsafe sudo service returned an invalid reply")
    return buffer.decode("ascii", "replace").strip()


def write_all(descriptor: int, data: bytes) -> None:
    while data:
        written = os.write(descriptor, data)
        data = data[written:]


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--socket", required=True)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    parsed = parser.parse_args()
    command = parsed.arguments
    if command and command[0] == "--":
        command = command[1:]

    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    original_terminal = None
    terminal_fd = sys.stdin.fileno()
    try:
        connection.connect(parsed.socket)
        request = json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        connection.sendall(b"EXEC " + request + b"\n")
        reply = receive_line(connection)
        if reply != "READY":
            print(f"sudo: unsafe sudo compatibility service refused the command: {reply}", file=sys.stderr)
            return 1

        if os.isatty(terminal_fd):
            original_terminal = termios.tcgetattr(terminal_fd)
            tty.setraw(terminal_fd)
        selector = selectors.DefaultSelector()
        selector.register(connection, selectors.EVENT_READ)
        selector.register(sys.stdin.buffer, selectors.EVENT_READ)
        receive_buffer = b""

        while True:
            for key, _events in selector.select():
                if key.fileobj is sys.stdin.buffer:
                    data = os.read(terminal_fd, MAX_FRAME_BYTES)
                    if data:
                        connection.sendall(FRAME_HEADER.pack(b"I", len(data)) + data)
                    continue
                data = connection.recv(MAX_FRAME_BYTES)
                if not data:
                    raise ConnectionError("unsafe sudo command connection closed unexpectedly")
                receive_buffer += data
                while len(receive_buffer) >= FRAME_HEADER.size:
                    kind, length = FRAME_HEADER.unpack(receive_buffer[:FRAME_HEADER.size])
                    if length > MAX_FRAME_BYTES:
                        raise ConnectionError("unsafe sudo service sent an oversized frame")
                    frame_end = FRAME_HEADER.size + length
                    if len(receive_buffer) < frame_end:
                        break
                    payload = receive_buffer[FRAME_HEADER.size:frame_end]
                    receive_buffer = receive_buffer[frame_end:]
                    if kind == b"O":
                        write_all(sys.stdout.fileno(), payload)
                    elif kind == b"X":
                        return int(payload.decode("ascii"))
                    else:
                        raise ConnectionError("unsafe sudo service sent an unsupported frame")
    except (OSError, ValueError, ConnectionError) as error:
        print(f"sudo: unsafe sudo compatibility failure: {error}", file=sys.stderr)
        return 1
    finally:
        if original_terminal is not None:
            termios.tcsetattr(terminal_fd, termios.TCSADRAIN, original_terminal)
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
