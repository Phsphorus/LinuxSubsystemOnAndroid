#!/usr/bin/python3

import errno
import json
import os
import pty
import signal
import socket
import stat
import struct
import termios
import threading
import time
import tty

from LSAIIOCommon import (
    STATE_SOCKET,
    devices_by_role,
    load_registry,
)


HOST = "127.0.0.1"
PORT = 8560

DEVROOT = "/dev"
CONTROL_SOCKET = STATE_SOCKET

STOP = threading.Event()


STATE_CONFIGS = {
    "light": {
        "encoding": "light",
    },

    "proximity": {
        "encoding": "proximity",
    },

    "steps": {
        "encoding": "steps",
    },
}


class StateDevice:

    def __init__(
        self,
        dirname,
        config,
        sensor,
    ):
        self.dirname = dirname
        self.config = config
        self.sensor = sensor

        self.devlink = os.path.join(
            DEVROOT,
            dirname,
        )

        self.bus_id = int(
            sensor["bus_id"]
        )

        self.master_fd = None
        self.slave_fd = None
        self.slave_path = None

        self.latest = None
        self.active = False

        self.lock = threading.Lock()
        self.ready = threading.Event()

        self.thread = None

    def setup_pty(self):
        master, slave = pty.openpty()

        tty.setraw(slave)
        os.set_blocking(master, False)

        path = os.ttyname(slave)

        if not stat.S_ISCHR(
            os.stat(path).st_mode
        ):
            raise RuntimeError(
                f"{path} is not a char device"
            )

        if os.path.lexists(self.devlink):
            if not os.path.islink(
                self.devlink
            ):
                raise RuntimeError(
                    f"refusing to replace "
                    f"{self.devlink}"
                )

            os.unlink(self.devlink)

        os.symlink(
            path,
            self.devlink,
        )

        self.master_fd = master
        self.slave_fd = slave
        self.slave_path = path

        print(
            f"LSAIIOStateBroker: "
            f"{self.dirname} "
            f"bus_id={self.bus_id} "
            f"-> {path}",
            flush=True,
        )

    def encode_event(self, msg):
        encoding = self.config[
            "encoding"
        ]

        values = msg.get("values")

        if not isinstance(values, list):
            values = []

        #
        # Android light value is lux.
        #
        if encoding == "light":
            if not values:
                return None

            value = int(
                round(float(values[0]))
            )

            return max(
                0,
                min(0xffffffff, value),
            )

        #
        # Android proximity is distance in cm.
        #
        # IIO raw ABI used by our proxy:
        #     1 = near
        #     0 = far
        #
        if encoding == "proximity":
            if not values:
                return None

            distance = float(values[0])

            max_range = float(
                self.sensor.get(
                    "max_range",
                    self.sensor.get(
                        "maxRange",
                        0,
                    ),
                )
                or 0
            )

            if max_range > 0:
                near = (
                    1
                    if distance < max_range
                    else 0
                )

            else:
                #
                # Common binary Android proximity
                # fallback: zero means near.
                #
                near = (
                    1
                    if distance <= 0
                    else 0
                )

            return near

        #
        # HALSensorBus preserves the Android
        # uint64 step counter explicitly.
        #
        if encoding == "steps":
            if "step_counter" in msg:
                return int(
                    msg["step_counter"]
                )

            if values:
                return int(
                    round(float(values[0]))
                )

            return None

        return None

    def pack(self, value):
        encoding = self.config[
            "encoding"
        ]

        if encoding in (
            "light",
            "proximity",
        ):
            return struct.pack(
                "<I",
                value,
            )

        if encoding == "steps":
            return struct.pack(
                "<Q",
                value,
            )

        raise RuntimeError(
            f"unknown encoding {encoding}"
        )

    def emit(self, value):
        payload = self.pack(value)

        try:
            os.write(
                self.master_fd,
                payload,
            )

        except BlockingIOError:
            pass

        except OSError as e:
            if e.errno not in (
                errno.EAGAIN,
                errno.EWOULDBLOCK,
                errno.EIO,
            ):
                raise

    def set_control(
        self,
        enable,
        scan,
    ):
        scan_name = {
            "light":
                "in_illuminance",

            "proximity":
                "in_proximity",

            "steps":
                "in_steps",
        }[
            self.config["encoding"]
        ]

        selected = bool(
            scan.get(
                scan_name,
                0,
            )
        )

        new_active = bool(
            enable and selected
        )

        with self.lock:
            old_active = self.active
            self.active = new_active

            if (
                new_active
                and not old_active
            ):
                #
                # New libiio reader:
                # throw away stale queued bytes.
                #
                try:
                    termios.tcflush(
                        self.slave_fd,
                        termios.TCIFLUSH,
                    )
                except Exception:
                    pass

                if self.latest is not None:
                    self.emit(
                        self.latest
                    )

                    print(
                        f"LSAIIOStateBroker: "
                        f"{self.dirname} "
                        f"buffer=ON "
                        f"initial={self.latest}",
                        flush=True,
                    )

                else:
                    print(
                        f"LSAIIOStateBroker: "
                        f"{self.dirname} "
                        f"buffer=ON "
                        f"waiting-for-cache",
                        flush=True,
                    )

            elif (
                not new_active
                and old_active
            ):
                print(
                    f"LSAIIOStateBroker: "
                    f"{self.dirname} "
                    f"buffer=OFF",
                    flush=True,
                )

    def watch_worker(self):
        while not STOP.is_set():
            sock = None

            try:
                sock = socket.create_connection(
                    (HOST, PORT),
                    timeout=3,
                )

                sock.settimeout(None)

                sock.sendall(
                    (
                        f"WATCH "
                        f"{self.bus_id} "
                        f"20000\n"
                    ).encode()
                )

                stream = sock.makefile(
                    "r",
                    encoding="utf-8",
                )

                for line in stream:
                    if STOP.is_set():
                        return

                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue

                    if msg.get("kind") != "event":
                        continue

                    value = self.encode_event(
                        msg
                    )

                    if value is None:
                        continue

                    with self.lock:
                        first = (
                            self.latest is None
                        )

                        changed = (
                            self.latest is not None
                            and value != self.latest
                        )

                        self.latest = value
                        active = self.active

                        if first:
                            self.ready.set()

                            print(
                                f"LSAIIOStateBroker: "
                                f"{self.dirname} "
                                f"cache={value}",
                                flush=True,
                            )

                        #
                        # If the reader enabled before the
                        # initial Android event arrived,
                        # this first event satisfies it.
                        #
                        if active and (
                            first or changed
                        ):
                            self.emit(value)

                            if not first:
                                print(
                                    f"LSAIIOStateBroker: "
                                    f"{self.dirname} "
                                    f"changed={value}",
                                    flush=True,
                                )

                raise RuntimeError(
                    "HALSensorBus stream closed"
                )

            except Exception as e:
                if not STOP.is_set():
                    print(
                        f"LSAIIOStateBroker: "
                        f"{self.dirname} "
                        f"WATCH error: {e}",
                        flush=True,
                    )

                    time.sleep(1)

            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass

    def start(self):
        self.setup_pty()

        self.thread = threading.Thread(
            target=self.watch_worker,
            daemon=True,
            name=self.dirname,
        )

        self.thread.start()

    def cleanup(self):
        try:
            if (
                os.path.islink(
                    self.devlink
                )
                and os.readlink(
                    self.devlink
                ) == self.slave_path
            ):
                os.unlink(
                    self.devlink
                )
        except Exception:
            pass

        for fd in (
            self.master_fd,
            self.slave_fd,
        ):
            if fd is None:
                continue

            try:
                os.close(fd)
            except Exception:
                pass


def main():
    global HOST, PORT

    registry = load_registry()

    HOST = registry["sensorbus"]["host"]
    PORT = int(
        registry["sensorbus"]["port"]
    )

    devices = {}

    try:
        os.unlink(
            CONTROL_SOCKET
        )
    except FileNotFoundError:
        pass

    control = socket.socket(
        socket.AF_UNIX,
        socket.SOCK_DGRAM,
    )

    control.bind(
        CONTROL_SOCKET
    )

    os.chmod(
        CONTROL_SOCKET,
        0o666,
    )

    control.settimeout(0.2)

    for entry in devices_by_role(
        registry,
        "state",
    ):
        dirname = entry["dirname"]
        kind = entry["kind"]

        config = STATE_CONFIGS.get(
            kind
        )

        if config is None:
            print(
                "LSAIIOStateBroker: "
                f"{dirname}: "
                f"unsupported state kind={kind}",
                flush=True,
            )
            continue

        sensor = entry["sensor"]

        device = StateDevice(
            dirname,
            config,
            sensor,
        )

        device.start()
        devices[dirname] = device

        print(
            "LSAIIOStateBroker: "
            f"registered {dirname} "
            f"kind={kind} "
            f"bus_id={entry['bus_id']}",
            flush=True,
        )

    print(
        f"LSAIIOStateBroker: "
        f"control={CONTROL_SOCKET}",
        flush=True,
    )

    #
    # Give Android on-change sensors a short chance
    # to publish their initial state before announcing
    # cache readiness.
    #
    deadline = time.monotonic() + 2.0

    for device in devices.values():
        remaining = (
            deadline - time.monotonic()
        )

        if remaining > 0:
            device.ready.wait(
                remaining
            )

    for dirname, device in devices.items():
        with device.lock:
            print(
                f"LSAIIOStateBroker: "
                f"{dirname} "
                f"ready="
                f"{device.latest is not None} "
                f"value={device.latest}",
                flush=True,
            )

    def stop(
        signum=None,
        frame=None,
    ):
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
                data = control.recv(
                    4096
                )

            except socket.timeout:
                continue

            try:
                msg = json.loads(
                    data.decode()
                )

                device = devices.get(
                    msg.get("device")
                )

                if device is None:
                    continue

                device.set_control(
                    int(
                        msg.get(
                            "enable",
                            0,
                        )
                    ),
                    msg.get(
                        "scan",
                        {},
                    ),
                )

            except Exception as e:
                print(
                    f"LSAIIOStateBroker: "
                    f"control error: {e}",
                    flush=True,
                )

    finally:
        STOP.set()
        control.close()

        try:
            os.unlink(
                CONTROL_SOCKET
            )
        except FileNotFoundError:
            pass

        for device in devices.values():
            device.cleanup()


if __name__ == "__main__":
    main()
