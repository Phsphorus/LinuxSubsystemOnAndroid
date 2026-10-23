#!/usr/bin/python3

import json
import os
import select
import signal
import socket
import struct
import threading
import time

from LSAIIOCommon import (
    EVENT_SOCKET,
    RUNTIME_DIR,
    devices_by_role,
    event_code,
    load_registry,
)


STOP = threading.Event()


def read_enabled(path):
    try:
        with open(path) as f:
            return f.read().strip() == "1"
    except Exception:
        return False


class Endpoint:

    def __init__(self, device, host, port):
        self.device = device

        self.dirname = device["dirname"]
        self.bus_id = int(device["bus_id"])
        self.mode = int(
            device.get(
                "reporting_mode",
                0,
            )
        )

        self.event = device["event"]

        self.enable_path = (
            "/sys/bus/iio/devices/"
            f"{self.dirname}/events/"
            f"{self.event['enable_attr']}"
        )

        self.code = event_code(
            self.event
        )

        self.host = host
        self.port = port

        self.clients = set()
        self.clients_lock = threading.Lock()

    def add_client(self, conn):
        with self.clients_lock:
            self.clients.add(conn)

        print(
            "LSAIIOEventBroker: "
            f"{self.dirname} client+",
            flush=True,
        )

    def broadcast(self, payload):
        dead = []

        with self.clients_lock:
            clients = list(self.clients)

        for conn in clients:
            try:
                conn.sendall(payload)
            except OSError:
                dead.append(conn)

        if dead:
            with self.clients_lock:
                for conn in dead:
                    self.clients.discard(
                        conn
                    )

                    try:
                        conn.close()
                    except Exception:
                        pass

    def record(self, timestamp_ns):
        return struct.pack(
            "=Qq",
            self.code,
            int(timestamp_ns),
        )

    def worker(self):
        sock = None
        rx = b""

        while not STOP.is_set():

            enabled = read_enabled(
                self.enable_path
            )

            if not enabled:
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass

                    sock = None
                    rx = b""

                    print(
                        "LSAIIOEventBroker: "
                        f"{self.dirname} DISARMED",
                        flush=True,
                    )

                time.sleep(0.05)
                continue

            if sock is None:
                try:
                    sock = socket.create_connection(
                        (
                            self.host,
                            self.port,
                        ),
                        timeout=3,
                    )

                    sock.setblocking(False)

                    sock.sendall(
                        (
                            f"WATCH "
                            f"{self.bus_id} "
                            "20000\n"
                        ).encode()
                    )

                    rx = b""

                    print(
                        "LSAIIOEventBroker: "
                        f"{self.dirname} "
                        f"ARMED bus_id="
                        f"{self.bus_id}",
                        flush=True,
                    )

                except Exception as e:
                    print(
                        "LSAIIOEventBroker: "
                        f"{self.dirname} "
                        f"arm error: {e}",
                        flush=True,
                    )

                    if sock is not None:
                        try:
                            sock.close()
                        except Exception:
                            pass

                    sock = None
                    time.sleep(1)
                    continue

            try:
                readable, _, exceptional = (
                    select.select(
                        [sock],
                        [],
                        [sock],
                        0.2,
                    )
                )
            except Exception:
                readable = []
                exceptional = [sock]

            if exceptional:
                try:
                    sock.close()
                except Exception:
                    pass

                sock = None
                rx = b""
                continue

            if not readable:
                continue

            try:
                chunk = sock.recv(65536)

            except BlockingIOError:
                continue

            except Exception as e:
                print(
                    "LSAIIOEventBroker: "
                    f"{self.dirname} "
                    f"recv error: {e}",
                    flush=True,
                )

                try:
                    sock.close()
                except Exception:
                    pass

                sock = None
                rx = b""
                continue

            if not chunk:
                try:
                    sock.close()
                except Exception:
                    pass

                sock = None
                rx = b""

                time.sleep(0.05)
                continue

            rx += chunk

            while b"\n" in rx:
                line, rx = rx.split(
                    b"\n",
                    1,
                )

                if not line:
                    continue

                try:
                    msg = json.loads(
                        line.decode()
                    )
                except Exception:
                    continue

                if msg.get("kind") == "watch":
                    continue

                if msg.get("kind") != "event":
                    continue

                timestamp_ns = int(
                    msg.get(
                        "timestamp_ns",
                        time.monotonic_ns(),
                    )
                )

                self.broadcast(
                    self.record(timestamp_ns)
                )

                print(
                    "LSAIIOEventBroker: "
                    f"{self.dirname} "
                    "EVENT "
                    f"id=0x{self.code:016x} "
                    f"ts={timestamp_ns}",
                    flush=True,
                )

                #
                # Android reporting mode 2:
                # reconnect after every consumed one-shot
                # while Linux keeps the event enabled.
                #
                if self.mode == 2:
                    try:
                        sock.close()
                    except Exception:
                        pass

                    sock = None
                    rx = b""

                    time.sleep(0.05)
                    break

        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    def start(self):
        threading.Thread(
            target=self.worker,
            daemon=True,
            name=f"LSAIIOEvent-{self.bus_id}",
        ).start()

    def cleanup(self):
        with self.clients_lock:
            clients = list(self.clients)
            self.clients.clear()

        for conn in clients:
            try:
                conn.close()
            except Exception:
                pass


def ensure_placeholder(dirname):
    path = os.path.join(
        "/dev",
        dirname,
    )

    if os.path.lexists(path):
        return

    fd = os.open(
        path,
        os.O_CREAT | os.O_RDWR,
        0o666,
    )

    os.close(fd)

    print(
        "LSAIIOEventBroker: "
        f"placeholder {path}",
        flush=True,
    )


def main():
    registry = load_registry()

    host = registry[
        "sensorbus"
    ]["host"]

    port = int(
        registry[
            "sensorbus"
        ]["port"]
    )

    event_devices = devices_by_role(
        registry,
        "event",
    )

    if not event_devices:
        raise SystemExit(
            "LSAIIOEventBroker: "
            "no event devices in registry"
        )

    os.makedirs(
        RUNTIME_DIR,
        mode=0o755,
        exist_ok=True,
    )

    endpoints = {}

    for device in event_devices:
        ensure_placeholder(
            device["dirname"]
        )

        ep = Endpoint(
            device,
            host,
            port,
        )

        endpoints[
            device["dirname"]
        ] = ep

        ep.start()

        print(
            "LSAIIOEventBroker: "
            f"registered "
            f"{device['dirname']} "
            f"kind={device['kind']} "
            f"bus_id={device['bus_id']}",
            flush=True,
        )

    try:
        os.unlink(EVENT_SOCKET)
    except FileNotFoundError:
        pass

    server = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM,
    )

    server.bind(EVENT_SOCKET)

    os.chmod(
        EVENT_SOCKET,
        0o666,
    )

    server.listen(16)
    server.settimeout(0.2)

    print(
        "LSAIIOEventBroker: "
        f"socket={EVENT_SOCKET}",
        flush=True,
    )

    def stop(*_):
        STOP.set()

    signal.signal(
        signal.SIGTERM,
        stop,
    )

    signal.signal(
        signal.SIGINT,
        stop,
    )

    try:
        while not STOP.is_set():

            try:
                conn, _ = server.accept()

            except socket.timeout:
                continue

            except Exception:
                if STOP.is_set():
                    break
                continue

            try:
                conn.settimeout(2)

                request = conn.recv(
                    128
                ).decode(
                    errors="replace"
                ).strip()

                ep = endpoints.get(
                    request
                )

                if ep is None:
                    conn.sendall(b"ERR\n")
                    conn.close()
                    continue

                #
                # Explicit handshake lets the ioctl shim distinguish
                # an LSA event device from a native/non-event device.
                #
                conn.sendall(b"OK\n")
                conn.settimeout(None)

                ep.add_client(conn)

            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass

    finally:
        STOP.set()

        try:
            server.close()
        except Exception:
            pass

        try:
            os.unlink(EVENT_SOCKET)
        except FileNotFoundError:
            pass

        for ep in endpoints.values():
            ep.cleanup()


if __name__ == "__main__":
    main()
