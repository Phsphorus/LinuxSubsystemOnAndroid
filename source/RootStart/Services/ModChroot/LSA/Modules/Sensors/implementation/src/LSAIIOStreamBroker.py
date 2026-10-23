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
    devices_by_role,
    load_registry,
)


SYSROOT = "/sys/bus/iio/devices"
DEVROOT = "/dev"


STREAM_CONFIGS = {
    "accel": {
        "fallback_resolution": 0.001,
        "channels": [
            ("in_accel_x", 0),
            ("in_accel_y", 1),
            ("in_accel_z", 2),
        ],
    },

    "gyro": {
        "fallback_resolution": 0.0001,
        "channels": [
            ("in_anglvel_x", 0),
            ("in_anglvel_y", 1),
            ("in_anglvel_z", 2),
        ],
    },

    "magn": {
        "fallback_resolution": 0.01,
        "channels": [
            ("in_magn_x", 0),
            ("in_magn_y", 1),
            ("in_magn_z", 2),
        ],
    },

    "pressure": {
        "fallback_resolution": 0.01,
        "channels": [
            ("in_pressure", 0),
        ],
    },

    "accel_uncal": {
        "fallback_resolution": 0.001,
        "channels": [
            ("in_accel_x", 0),
            ("in_accel_y", 1),
            ("in_accel_z", 2),
        ],
    },

    "gyro_uncal": {
        "fallback_resolution": 0.0001,
        "channels": [
            ("in_anglvel_x", 0),
            ("in_anglvel_y", 1),
            ("in_anglvel_z", 2),
        ],
    },

    "magn_uncal": {
        "fallback_resolution": 0.01,
        "channels": [
            ("in_magn_x", 0),
            ("in_magn_y", 1),
            ("in_magn_z", 2),
        ],
    },

    "gravity": {
        "fallback_resolution": 0.001,
        "channels": [
            ("in_gravity_x", 0),
            ("in_gravity_y", 1),
            ("in_gravity_z", 2),
        ],
    },

    "linear": {
        "fallback_resolution": 0.001,
        "channels": [
            ("in_accel_x-g", 0),
            ("in_accel_y-g", 1),
            ("in_accel_z-g", 2),
        ],
    },

    "rotation": {
        "encoding": "q30_quaternion",
        "channels": [
            ("in_rot_quaternion", 0),
        ],
    },

    "game_rotation": {
        "encoding": "q30_quaternion",
        "channels": [
            ("in_rot_quaternion", 0),
        ],
    },

    "geomagnetic_rotation": {
        "encoding": "q30_quaternion",
        "channels": [
            ("in_rot_quaternion", 0),
        ],
    },

    "orientation": {
        "encoding": "millidegrees",
        "channels": [
            ("in_rot_yaw", 0),
            ("in_rot_pitch", 1),
            ("in_rot_roll", 2),
        ],
    },
}


STOP = threading.Event()


def read_text(path):
    with open(path, "r") as f:
        return f.read().strip()


def read_int(path, default=0):
    try:
        return int(read_text(path))
    except Exception:
        return default


class StreamDevice:

    def __init__(
        self,
        dirname,
        name,
        config,
        sensor,
        host,
        port,
    ):
        self.dirname = dirname
        self.name = name
        self.config = config
        self.sensor = sensor
        self.host = host
        self.port = int(port)

        self.sysbase = os.path.join(
            SYSROOT,
            dirname,
        )

        self.devlink = os.path.join(
            DEVROOT,
            dirname,
        )

        self.bus_id = int(sensor["bus_id"])

        self.resolution = float(
            sensor.get("resolution", 0) or 0
        )

        if self.resolution <= 0:
            self.resolution = float(
                config.get(
                    "fallback_resolution",
                    1.0,
                )
            )

        minimum = int(
            sensor.get("min_delay_us", 0) or 0
        )

        self.period_us = max(
            20000,
            minimum,
        )

        self.master_fd = None
        self.slave_fd = None
        self.slave_path = None

        self.thread = None

    def setup_pty(self):
        master, slave = pty.openpty()

        tty.setraw(slave)
        os.set_blocking(master, False)

        slave_path = os.ttyname(slave)

        if not stat.S_ISCHR(
            os.stat(slave_path).st_mode
        ):
            raise RuntimeError(
                f"{slave_path} is not a char device"
            )

        if os.path.lexists(self.devlink):
            if not os.path.islink(self.devlink):
                raise RuntimeError(
                    f"refusing to replace "
                    f"{self.devlink}"
                )

            os.unlink(self.devlink)

        os.symlink(
            slave_path,
            self.devlink,
        )

        self.master_fd = master
        self.slave_fd = slave
        self.slave_path = slave_path

        print(
            f"LSAIIOStreamBroker: "
            f"{self.dirname} "
            f"{self.name} "
            f"bus_id={self.bus_id} "
            f"-> {slave_path}",
            flush=True,
        )

    def enabled_state(self):
        enabled = (
            read_int(
                self.sysbase +
                "/buffer/enable"
            )
            != 0
        )

        mask = []

        for channel, value_index in self.config["channels"]:
            mask.append(
                read_int(
                    self.sysbase +
                    "/scan_elements/" +
                    channel +
                    "_en"
                )
                != 0
            )

        return enabled, tuple(mask)

    def pack(self, values, mask):
        payload = bytearray()

        #
        # Android rotation vectors expose x, y, z, w.
        # Linux IIO represents the quaternion scan element as
        # four repeated s32 values. Match our existing sysfs
        # representation by encoding each component as Q30.
        #
        if self.config.get("encoding") == "q30_quaternion":
            if not mask or not mask[0]:
                return b""

            if len(values) < 4:
                raise ValueError(
                    f"{self.dirname}: quaternion has "
                    f"{len(values)} values, expected >= 4"
                )

            for i in range(4):
                raw = int(
                    round(
                        float(values[i])
                        * (1 << 30)
                    )
                )

                raw = max(
                    -(1 << 31),
                    min((1 << 31) - 1, raw),
                )

                payload += struct.pack(
                    "<i",
                    raw,
                )

            return bytes(payload)

        if self.config.get("encoding") == "millidegrees":
            for (
                selected,
                (channel, value_index),
            ) in zip(
                mask,
                self.config["channels"],
            ):
                if not selected:
                    continue

                if value_index >= len(values):
                    raise ValueError(
                        f"{self.dirname}: "
                        f"missing orientation value "
                        f"{value_index}"
                    )

                raw = int(
                    round(float(values[value_index]) * 1000.0)
                )

                payload += struct.pack("<i", raw)

            return bytes(payload)

        for (
            selected,
            (channel, value_index),
        ) in zip(
            mask,
            self.config["channels"],
        ):
            if not selected:
                continue

            if value_index >= len(values):
                raise ValueError(
                    f"{self.dirname}: "
                    f"missing value index "
                    f"{value_index}"
                )

            raw = int(
                round(
                    float(values[value_index])
                    / self.resolution
                )
            )

            payload += struct.pack(
                "<i",
                raw,
            )

        return bytes(payload)

    def worker(self):
        previous_state = None

        while not STOP.is_set():
            sock = None

            try:
                sock = socket.create_connection(
                    (
                        self.host,
                        self.port,
                    ),
                    timeout=3,
                )

                sock.settimeout(None)

                sock.sendall(
                    (
                        f"WATCH {self.bus_id} "
                        f"{self.period_us}\n"
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

                    values = msg.get("values")

                    if not isinstance(values, list):
                        continue

                    enabled, mask = self.enabled_state()
                    state = (enabled, mask)

                    if state != previous_state:
                        #
                        # Starting a fresh IIO buffer session must
                        # never expose samples left queued by an
                        # earlier reader.
                        #
                        if enabled and (
                            previous_state is None
                            or not previous_state[0]
                        ):
                            try:
                                termios.tcflush(
                                    self.slave_fd,
                                    termios.TCIFLUSH,
                                )
                            except Exception:
                                pass

                        print(
                            f"LSAIIOStreamBroker: "
                            f"{self.dirname} "
                            f"buffer="
                            f"{'ON' if enabled else 'OFF'} "
                            f"scan={mask}",
                            flush=True,
                        )

                        previous_state = state

                    if not enabled:
                        continue

                    if not any(mask):
                        continue

                    payload = self.pack(
                        values,
                        mask,
                    )

                    if not payload:
                        continue

                    try:
                        os.write(
                            self.master_fd,
                            payload,
                        )

                    except BlockingIOError:
                        # Backpressure policy:
                        # never stall SensorBus.
                        pass

                    except OSError as e:
                        if e.errno not in (
                            errno.EAGAIN,
                            errno.EWOULDBLOCK,
                            errno.EIO,
                        ):
                            raise

                raise RuntimeError(
                    "SensorBus stream closed"
                )

            except Exception as e:
                if not STOP.is_set():
                    print(
                        f"LSAIIOStreamBroker: "
                        f"{self.dirname} "
                        f"stream error: {e}",
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
            target=self.worker,
            daemon=True,
            name=self.dirname,
        )

        self.thread.start()

    def cleanup(self):
        try:
            if (
                os.path.islink(self.devlink)
                and os.readlink(self.devlink)
                == self.slave_path
            ):
                os.unlink(self.devlink)
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
    registry = load_registry()

    host = registry[
        "sensorbus"
    ]["host"]

    port = int(
        registry[
            "sensorbus"
        ]["port"]
    )

    entries = devices_by_role(
        registry,
        "stream",
    )

    if not entries:
        raise RuntimeError(
            "no stream devices in LSA IIO registry"
        )

    devices = []

    for entry in entries:
        dirname = entry["dirname"]
        kind = entry["kind"]

        config = STREAM_CONFIGS.get(
            kind
        )

        if config is None:
            print(
                "LSAIIOStreamBroker: "
                f"{dirname}: "
                f"unsupported stream kind={kind}",
                flush=True,
            )
            continue

        sysbase = os.path.join(
            SYSROOT,
            dirname,
        )

        try:
            name = read_text(
                os.path.join(
                    sysbase,
                    "name",
                )
            )
        except Exception:
            name = f"lsa-{kind}"

        device = StreamDevice(
            dirname,
            name,
            config,
            entry["sensor"],
            host,
            port,
        )

        device.start()
        devices.append(device)

        print(
            "LSAIIOStreamBroker: "
            f"registered {dirname} "
            f"kind={kind} "
            f"bus_id={entry['bus_id']}",
            flush=True,
        )

    if not devices:
        raise RuntimeError(
            "no supported stream devices started"
        )

    def stop(signum=None, frame=None):
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
            time.sleep(0.2)

    finally:
        STOP.set()

        for device in devices:
            device.cleanup()



if __name__ == "__main__":
    main()
