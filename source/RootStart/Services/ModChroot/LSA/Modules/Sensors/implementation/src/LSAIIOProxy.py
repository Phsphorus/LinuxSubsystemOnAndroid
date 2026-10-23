#!/usr/bin/python3

import errno
import json
import math
import os
import socket
import stat
import sys
import threading
import time

from fusepy import FUSE, FuseOSError, Operations

from LSAIIOCommon import (
    STATE_SOCKET,
    load_registry,
)


HOST = None
PORT = None

CACHE_SECONDS = 0.050


class SensorReader:

    def __init__(self):
        self.cache = {}
        self.sensors = {}
        self.workers = {}

        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)

    def register(self, sensor):
        bus_id = int(sensor["bus_id"])

        with self.lock:
            self.sensors[bus_id] = sensor

    def period_for(self, sensor):
        if int(sensor.get("reporting_mode", 0)) != 0:
            return None

        minimum = int(sensor.get("min_delay_us", 0) or 0)

        return max(20000, minimum)

    def frequency_for(self, sensor):
        period = self.period_for(sensor)

        if not period:
            return None

        return 1000000.0 / period

    def ensure_worker(self, sensor):
        bus_id = int(sensor["bus_id"])

        with self.lock:
            worker = self.workers.get(bus_id)

            if worker is not None and worker.is_alive():
                return

            worker = threading.Thread(
                target=self.worker,
                args=(sensor,),
                daemon=True,
                name=f"LSAIIO-{bus_id}",
            )

            self.workers[bus_id] = worker
            worker.start()

    def worker(self, sensor):
        bus_id = int(sensor["bus_id"])
        string_type = sensor.get("string_type", "unknown")

        while True:
            sock = None

            try:
                period = self.period_for(sensor)

                if period is None:
                    command = f"WATCH {bus_id}\n"
                else:
                    command = f"WATCH {bus_id} {period}\n"

                print(
                    f"LSAIIOProxy: WATCH "
                    f"bus_id={bus_id} "
                    f"type={string_type}",
                    flush=True,
                )

                sock = socket.create_connection(
                    (HOST, PORT),
                    timeout=3,
                )

                sock.settimeout(None)
                sock.sendall(command.encode())

                f = sock.makefile(
                    "r",
                    encoding="utf-8",
                )

                for line in f:
                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue

                    if msg.get("kind") != "event":
                        continue

                    with self.cond:
                        self.cache[bus_id] = (
                            time.monotonic(),
                            msg,
                        )

                        self.cond.notify_all()

                raise RuntimeError(
                    "SensorBus stream closed"
                )

            except Exception as e:
                print(
                    f"LSAIIOProxy: stream error "
                    f"bus_id={bus_id}: {e}",
                    flush=True,
                )

            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass

            time.sleep(1)

    def read_event(self, sensor):
        bus_id = int(sensor["bus_id"])

        self.ensure_worker(sensor)

        deadline = time.monotonic() + 2.0

        with self.cond:
            while bus_id not in self.cache:
                remaining = deadline - time.monotonic()

                if remaining <= 0:
                    raise RuntimeError(
                        f"no sample available for bus_id={bus_id}"
                    )

                self.cond.wait(remaining)

            when, msg = self.cache[bus_id]

            #
            # Continuous sensors should remain alive. Don't silently
            # serve ancient data forever if SensorBus disappears.
            #
            if int(sensor.get("reporting_mode", 0)) == 0:
                age = time.monotonic() - when

                if age > 2.0:
                    raise RuntimeError(
                        f"stale sample bus_id={bus_id} "
                        f"age={age:.2f}s"
                    )

            #
            # On-change sensors intentionally retain their last sample.
            #
            return msg


class Device:

    def __init__(
        self,
        dirname,
        kind,
        sensor,
        reader,
    ):
        self.dirname = dirname

        self.kind = kind
        self.sensor = sensor
        self.reader = reader

        # Learned maximum/far value for Android proximity sensors.
        # Current NDK sensor metadata does not expose getMaximumRange().
        self.proximity_far = None

    @property
    def name(self):
        android_name = str(
            self.sensor.get("name", self.kind)
        )

        return f"lsa-{self.kind}-{android_name}"

    def resolution(self, fallback):
        try:
            r = float(self.sensor.get("resolution", 0))

            if r > 0:
                return r
        except Exception:
            pass

        return fallback

    def event(self):
        return self.reader.read_event(self.sensor)

    def values(self):
        msg = self.event()

        values = msg.get("values")

        if not isinstance(values, list):
            raise FuseOSError(errno.EIO)

        return [float(x) for x in values]

    def scale_vector(self, fallback=0.001, conversion=1.0):
        return self.resolution(fallback) * conversion

    def raw_vector(self, conversion=1.0, fallback=0.001):
        vals = self.values()

        resolution = self.resolution(fallback)

        return [
            int(round(v / resolution))
            for v in vals
        ]

    def sampling_frequency(self):
        f = self.reader.frequency_for(self.sensor)

        if f is None:
            return None

        return f

    def files(self):
        files = {
            "name": lambda: self.name,
        }

        frequency = self.sampling_frequency()

        if frequency is not None:
            files["sampling_frequency"] = (
                lambda f=frequency: f"{f:.6f}"
            )

        #
        # Android ACCELEROMETER:
        # values are already m/s^2.
        #
        if self.kind == "accel":
            scale = self.scale_vector(0.001)

            files.update({
                "in_accel_scale":
                    lambda: f"{scale:.12g}",

                "in_accel_x_raw":
                    lambda: str(self.raw_vector()[0]),

                "in_accel_y_raw":
                    lambda: str(self.raw_vector()[1]),

                "in_accel_z_raw":
                    lambda: str(self.raw_vector()[2]),
            })

        #
        # Android GYROSCOPE:
        # values are rad/s, matching IIO anglvel units.
        #
        elif self.kind == "gyro":
            scale = self.scale_vector(0.0001)

            files.update({
                "in_anglvel_scale":
                    lambda: f"{scale:.12g}",

                "in_anglvel_x_raw":
                    lambda: str(self.raw_vector()[0]),

                "in_anglvel_y_raw":
                    lambda: str(self.raw_vector()[1]),

                "in_anglvel_z_raw":
                    lambda: str(self.raw_vector()[2]),
            })

        #
        # Android magnetic field = microtesla.
        # Linux IIO magnetic field = Gauss.
        #
        # 1 uT = 0.01 Gauss.
        #
        elif self.kind == "magn":
            resolution_ut = self.resolution(0.01)
            scale_gauss = resolution_ut * 0.01

            files.update({
                "in_magn_scale":
                    lambda: f"{scale_gauss:.12g}",

                "in_magn_x_raw":
                    lambda: str(
                        int(round(
                            self.values()[0] /
                            resolution_ut
                        ))
                    ),

                "in_magn_y_raw":
                    lambda: str(
                        int(round(
                            self.values()[1] /
                            resolution_ut
                        ))
                    ),

                "in_magn_z_raw":
                    lambda: str(
                        int(round(
                            self.values()[2] /
                            resolution_ut
                        ))
                    ),
            })

        #
        # Android pressure = hPa.
        # Linux IIO pressure = kPa.
        #
        # 1 hPa = 0.1 kPa.
        #
        elif self.kind == "pressure":
            resolution_hpa = self.resolution(0.01)
            scale_kpa = resolution_hpa * 0.1

            files.update({
                "in_pressure_scale":
                    lambda: f"{scale_kpa:.12g}",

                "in_pressure_raw":
                    lambda: str(
                        int(round(
                            self.values()[0] /
                            resolution_hpa
                        ))
                    ),
            })

        #
        # Android ALS is already lux.
        #
        elif self.kind == "light":
            files.update({
                "in_illuminance_input":
                    lambda: f"{self.values()[0]:.6f}",
            })

        #
        # Android proximity is distance in cm.
        #
        # IIO has a standard distance channel, so expose truthful
        # physical distance in meters instead of inventing a
        # device-specific proximity scale.
        #
        elif self.kind == "proximity":

            def proximity():
                distance_cm = self.values()[0]

                if (
                    self.proximity_far is None
                    or distance_cm > self.proximity_far
                ):
                    self.proximity_far = distance_cm

                # Current phone is a normal binary Android prox:
                # 0 cm = near, 5 cm = far.
                #
                # Once a positive far value is learned, use halfway
                # between 0 and far as the boundary.
                if self.proximity_far and self.proximity_far > 0:
                    near = (
                        distance_cm <
                        (self.proximity_far * 0.5)
                    )
                else:
                    near = distance_cm <= 0.001

                return distance_cm, near

            files.update({
                # Truthful physical distance in meters.
                "in_distance_input":
                    lambda: f"{proximity()[0] * 0.01:.6f}",

                # Generic IIO proximity semantics:
                # 1 = near, 0 = far.
                "in_proximity_raw":
                    lambda: "1" if proximity()[1] else "0",

                # IIO says raw >= nearlevel means near.
                "in_proximity_nearlevel":
                    lambda: "1",
            })

        #
        # Android UNCALIBRATED sensors:
        #
        # values[0:3] = uncalibrated measurement
        # values[3:6] = estimated bias
        #
        # Linux IIO offset semantics are:
        #
        #   processed = (raw + offset) * scale
        #
        # Android calibrated measurement is:
        #
        #   calibrated = uncalibrated - bias
        #
        # Therefore:
        #
        #   offset = -bias / Android_resolution
        #

        elif self.kind == "accel_uncal":
            resolution = self.resolution(0.001)

            def data():
                v = self.values()

                if len(v) < 6:
                    raise FuseOSError(errno.EIO)

                raw = [
                    int(round(v[i] / resolution))
                    for i in range(3)
                ]

                offset = [
                    int(round(-v[i + 3] / resolution))
                    for i in range(3)
                ]

                return raw, offset

            files.update({
                "in_accel_scale":
                    lambda: f"{resolution:.12g}",

                "in_accel_x_raw":
                    lambda: str(data()[0][0]),
                "in_accel_y_raw":
                    lambda: str(data()[0][1]),
                "in_accel_z_raw":
                    lambda: str(data()[0][2]),

                "in_accel_x_offset":
                    lambda: str(data()[1][0]),
                "in_accel_y_offset":
                    lambda: str(data()[1][1]),
                "in_accel_z_offset":
                    lambda: str(data()[1][2]),
            })


        elif self.kind == "gyro_uncal":
            resolution = self.resolution(0.0001)

            def data():
                v = self.values()

                if len(v) < 6:
                    raise FuseOSError(errno.EIO)

                raw = [
                    int(round(v[i] / resolution))
                    for i in range(3)
                ]

                offset = [
                    int(round(-v[i + 3] / resolution))
                    for i in range(3)
                ]

                return raw, offset

            files.update({
                "in_anglvel_scale":
                    lambda: f"{resolution:.12g}",

                "in_anglvel_x_raw":
                    lambda: str(data()[0][0]),
                "in_anglvel_y_raw":
                    lambda: str(data()[0][1]),
                "in_anglvel_z_raw":
                    lambda: str(data()[0][2]),

                "in_anglvel_x_offset":
                    lambda: str(data()[1][0]),
                "in_anglvel_y_offset":
                    lambda: str(data()[1][1]),
                "in_anglvel_z_offset":
                    lambda: str(data()[1][2]),
            })


        elif self.kind == "magn_uncal":
            resolution_ut = self.resolution(0.01)

            # Android magnetic values are microtesla.
            # IIO magnetic field unit is Gauss.
            scale_gauss = resolution_ut * 0.01

            def data():
                v = self.values()

                if len(v) < 6:
                    raise FuseOSError(errno.EIO)

                raw = [
                    int(round(v[i] / resolution_ut))
                    for i in range(3)
                ]

                offset = [
                    int(round(-v[i + 3] / resolution_ut))
                    for i in range(3)
                ]

                return raw, offset

            files.update({
                "in_magn_scale":
                    lambda: f"{scale_gauss:.12g}",

                "in_magn_x_raw":
                    lambda: str(data()[0][0]),
                "in_magn_y_raw":
                    lambda: str(data()[0][1]),
                "in_magn_z_raw":
                    lambda: str(data()[0][2]),

                "in_magn_x_offset":
                    lambda: str(data()[1][0]),
                "in_magn_y_offset":
                    lambda: str(data()[1][1]),
                "in_magn_z_offset":
                    lambda: str(data()[1][2]),
            })


        #
        # Linux explicitly has gravity channels.
        # Android gravity is m/s^2.
        #
        elif self.kind == "gravity":
            scale = self.scale_vector(0.001)

            files.update({
                "in_gravity_scale":
                    lambda: f"{scale:.12g}",

                "in_gravity_x_raw":
                    lambda: str(self.raw_vector()[0]),

                "in_gravity_y_raw":
                    lambda: str(self.raw_vector()[1]),

                "in_gravity_z_raw":
                    lambda: str(self.raw_vector()[2]),
            })

        #
        # Linux explicitly has linear-acceleration channels.
        #
        elif self.kind == "linear":
            scale = self.scale_vector(0.001)

            files.update({
                "in_accel_linear_scale":
                    lambda: f"{scale:.12g}",

                "in_accel_linear_x_raw":
                    lambda: str(self.raw_vector()[0]),

                "in_accel_linear_y_raw":
                    lambda: str(self.raw_vector()[1]),

                "in_accel_linear_z_raw":
                    lambda: str(self.raw_vector()[2]),
            })

        #
        # Android rotation vector:
        # values[0:4] = quaternion x y z w.
        #
        # Represent it as Q30 integer raw values.
        #
        elif self.kind in (
            "rotation",
            "game_rotation",
            "geomagnetic_rotation",
        ):
            qscale = 1.0 / (1 << 30)

            def quaternion():
                v = self.values()

                if len(v) < 4:
                    raise FuseOSError(errno.EIO)

                return [
                    int(round(v[i] * (1 << 30)))
                    for i in range(4)
                ]

            files.update({
                "in_rot_scale":
                    lambda: f"{qscale:.15g}",

                "in_rot_quaternion_raw":
                    lambda: " ".join(
                        str(x)
                        for x in quaternion()
                    ),
            })

        #
        # Legacy Android orientation:
        # azimuth / pitch / roll in degrees.
        #
        elif self.kind == "orientation":
            scale = 0.001

            def orient():
                v = self.values()

                return [
                    int(round(x / scale))
                    for x in v[:3]
                ]

            files.update({
                "in_rot_scale":
                    lambda: f"{scale:.6f}",

                "in_rot_yaw_raw":
                    lambda: str(orient()[0]),

                "in_rot_pitch_raw":
                    lambda: str(orient()[1]),

                "in_rot_roll_raw":
                    lambda: str(orient()[2]),
            })

        #
        # Linux IIO has an explicit pedometer step counter.
        #
        elif self.kind == "steps":

            def steps():
                msg = self.event()

                if "step_counter" not in msg:
                    raise FuseOSError(errno.EIO)

                return int(msg["step_counter"])

            files.update({
                "in_steps_input":
                    lambda: str(steps()),
            })

        return files


class EventDevice:

    def __init__(
        self,
        dirname,
        name,
        sensor,
    ):
        self.dirname = dirname
        self.name = name
        self.sensor = sensor

    def files(self):
        return {
            "name": lambda: self.name,
        }


class LSAIIOFS(Operations):

    def __init__(self):
        global HOST, PORT

        registry = load_registry()

        HOST = registry[
            "sensorbus"
        ]["host"]

        PORT = int(
            registry[
                "sensorbus"
            ]["port"]
        )

        reader = SensorReader()

        self.native_links = {
            entry["dirname"]: entry["target"]
            for entry in registry.get(
                "native",
                [],
            )
        }

        self.devices = {}

        #
        # Canonical metadata indexed by Linux dirname.
        # This is now the authority for role checks elsewhere
        # in the FUSE implementation.
        #
        self.device_meta = {}

        # Writable virtual IIO buffer state.
        self.buffer_state = {}

        # Event-only virtual IIO state.
        self.event_state = {}

        for name, target in sorted(
            self.native_links.items()
        ):
            print(
                "LSAIIOProxy: preserve native "
                f"{name} -> {target}",
                flush=True,
            )

        print(
            "LSAIIOProxy: "
            "first synthetic index="
            f"{registry['first_synthetic_index']}",
            flush=True,
        )

        #
        # Linux IIO ABI layout by semantic sensor kind.
        #
        # This is intentionally static: it describes the Linux
        # representation, not hardware/device identity.
        #
        scan_layouts = {
            "accel": [
                "in_accel_x",
                "in_accel_y",
                "in_accel_z",
            ],

            "gyro": [
                "in_anglvel_x",
                "in_anglvel_y",
                "in_anglvel_z",
            ],

            "magn": [
                "in_magn_x",
                "in_magn_y",
                "in_magn_z",
            ],

            "pressure": [
                "in_pressure",
            ],

            "accel_uncal": [
                "in_accel_x",
                "in_accel_y",
                "in_accel_z",
            ],

            "gyro_uncal": [
                "in_anglvel_x",
                "in_anglvel_y",
                "in_anglvel_z",
            ],

            "magn_uncal": [
                "in_magn_x",
                "in_magn_y",
                "in_magn_z",
            ],

            "gravity": [
                "in_gravity_x",
                "in_gravity_y",
                "in_gravity_z",
            ],

            "linear": [
                "in_accel_x-g",
                "in_accel_y-g",
                "in_accel_z-g",
            ],

            "rotation": [
                "in_rot_quaternion",
            ],

            "game_rotation": [
                "in_rot_quaternion",
            ],

            "geomagnetic_rotation": [
                "in_rot_quaternion",
            ],

            "orientation": [
                "in_rot_yaw",
                "in_rot_pitch",
                "in_rot_roll",
            ],

            "light": [
                "in_illuminance",
            ],

            "proximity": [
                "in_proximity",
            ],

            "steps": [
                "in_steps",
            ],
        }

        seen = set()

        for entry in registry["devices"]:
            dirname = entry["dirname"]
            kind = entry["kind"]
            role = entry["role"]
            sensor = entry["sensor"]

            if dirname in seen:
                raise RuntimeError(
                    "duplicate registry dirname: "
                    f"{dirname}"
                )

            seen.add(dirname)

            if dirname in self.native_links:
                raise RuntimeError(
                    "synthetic/native IIO collision: "
                    f"{dirname}"
                )

            self.device_meta[
                dirname
            ] = entry

            #
            # Event-only devices use registry-provided event
            # metadata to construct their sysfs attributes.
            #
            if role == "event":
                event = entry.get(
                    "event"
                )

                if not event:
                    raise RuntimeError(
                        f"{dirname}: "
                        "event role without event metadata"
                    )

                name = (
                    "lsa-"
                    + kind.replace(
                        "_",
                        "-",
                    )
                )

                device = EventDevice(
                    dirname,
                    name,
                    sensor,
                )

                self.devices[
                    dirname
                ] = device

                attrs = {
                    event["enable_attr"]: {
                        "mode": "rw",
                        "value": 0,
                    },
                }

                value_attr = event.get(
                    "value_attr"
                )

                if value_attr:
                    attrs[value_attr] = {
                        "mode": "ro",
                        "value": int(
                            event.get(
                                "value",
                                0,
                            )
                        ),
                    }

                self.event_state[
                    dirname
                ] = {
                    "sensor": sensor,
                    "kind": kind,
                    "attrs": attrs,
                }

                print(
                    "LSAIIOProxy: "
                    f"{dirname} "
                    f"role=event "
                    f"kind={kind} "
                    f"<- bus_id={entry['bus_id']} "
                    f"wake={entry['wake_up']}",
                    flush=True,
                )

                continue

            #
            # Stream/state devices share the direct-value Device
            # implementation. Their behavioral role is retained
            # separately in self.device_meta.
            #
            reader.register(
                sensor
            )

            device = Device(
                dirname,
                kind,
                sensor,
                reader,
            )

            self.devices[
                dirname
            ] = device

            layout = scan_layouts.get(
                kind
            )

            if layout is not None:
                self.buffer_state[
                    dirname
                ] = {
                    "length": 128,
                    "watermark": 1,
                    "enable": 0,

                    "scan": {
                        channel: 0
                        for channel in layout
                    },
                }

            print(
                "LSAIIOProxy: "
                f"{dirname} "
                f"role={role} "
                f"kind={kind} "
                f"<- bus_id={entry['bus_id']} "
                f"{sensor.get('name')}",
                flush=True,
            )

    def _parts(self, path):
        return [x for x in path.split("/") if x]

    def _device(self, name):
        return self.devices.get(name)

    def _buffered(self, name):
        return name in self.buffer_state

    def _direct_file(self, parts):
        if len(parts) != 2:
            return None

        device = self._device(parts[0])

        if device is None:
            return None

        return device.files().get(parts[1])

    def _virtual_file(self, parts):
        if len(parts) != 3:
            return None

        devname, directory, filename = parts

        if (
            devname in self.event_state
            and directory == "events"
        ):
            attr = self.event_state[
                devname
            ]["attrs"].get(filename)

            if attr is None:
                return None

            return (
                attr["mode"],
                lambda a=attr: str(a["value"]),
            )

        if not self._buffered(devname):
            return None

        state = self.buffer_state[devname]

        if directory == "buffer":
            if filename == "length":
                return ("rw", lambda: str(state["length"]))

            if filename == "enable":
                return ("rw", lambda: str(state["enable"]))

            if filename == "watermark":
                return ("rw", lambda: str(state["watermark"]))

            return None

        if directory == "scan_elements":
            scan = state["scan"]

            for index, channel in enumerate(scan):
                if filename == f"{channel}_en":
                    return (
                        "rw",
                        lambda c=channel: str(scan[c]),
                    )

                if filename == f"{channel}_index":
                    return (
                        "ro",
                        lambda i=index: str(i),
                    )

                if filename == f"{channel}_type":
                    #
                    # Quaternion is one IIO scan element containing
                    # four consecutive signed 32-bit Q30 values.
                    #
                    scan_types = {
                        "in_rot_quaternion":
                            "le:s32/32X4>>0",

                        "in_illuminance":
                            "le:u32/32>>0",

                        "in_proximity":
                            "le:u32/32>>0",

                        "in_steps":
                            "le:u64/64>>0",
                    }

                    scan_type = scan_types.get(
                        channel,
                        "le:s32/32>>0",
                    )

                    return (
                        "ro",
                        lambda t=scan_type: t,
                    )

        return None

    def getattr(self, path, fh=None):
        now = time.time()

        base_dir = {
            "st_mode": stat.S_IFDIR | 0o555,
            "st_nlink": 2,
            "st_ctime": now,
            "st_mtime": now,
            "st_atime": now,
        }

        if path == "/":
            return base_dir

        parts = self._parts(path)

        if (
            len(parts) == 1
            and parts[0] in self.native_links
        ):
            target = self.native_links[parts[0]]

            return {
                "st_mode": stat.S_IFLNK | 0o777,
                "st_nlink": 1,
                "st_size": len(target),
                "st_ctime": now,
                "st_mtime": now,
                "st_atime": now,
            }

        if (
            len(parts) == 1
            and parts[0] in self.devices
        ):
            return base_dir

        if (
            len(parts) == 2
            and parts[0] in self.event_state
            and parts[1] == "events"
        ):
            return base_dir

        if (
            len(parts) == 2
            and self._buffered(parts[0])
            and parts[1] in ("buffer", "scan_elements")
        ):
            return base_dir

        getter = self._direct_file(parts)

        if getter is not None:
            return {
                "st_mode": stat.S_IFREG | 0o444,
                "st_nlink": 1,
                "st_size": 4096,
                "st_ctime": now,
                "st_mtime": now,
                "st_atime": now,
            }

        virtual = self._virtual_file(parts)

        if virtual is not None:
            mode, getter = virtual

            perms = 0o644 if mode == "rw" else 0o444

            return {
                "st_mode": stat.S_IFREG | perms,
                "st_nlink": 1,
                "st_size": 4096,
                "st_ctime": now,
                "st_mtime": now,
                "st_atime": now,
            }

        raise FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        if path == "/":
            entries = set(self.native_links)
            entries.update(self.devices)

            return [".", "..", *sorted(entries)]

        parts = self._parts(path)

        if (
            len(parts) == 1
            and parts[0] in self.devices
        ):
            device = self.devices[parts[0]]
            entries = set(device.files())

            if self._buffered(parts[0]):
                entries.add("buffer")
                entries.add("scan_elements")

            if parts[0] in self.event_state:
                entries.add("events")

            return [".", "..", *sorted(entries)]

        if (
            len(parts) == 2
            and parts[0] in self.event_state
            and parts[1] == "events"
        ):
            attrs = self.event_state[
                parts[0]
            ]["attrs"]

            return [
                ".",
                "..",
                *sorted(attrs),
            ]

        if (
            len(parts) == 2
            and self._buffered(parts[0])
        ):
            devname, directory = parts
            state = self.buffer_state[devname]

            if directory == "buffer":
                return [
                    ".",
                    "..",
                    "enable",
                    "length",
                    "watermark",
                ]

            if directory == "scan_elements":
                entries = []

                for channel in state["scan"]:
                    entries.extend([
                        f"{channel}_en",
                        f"{channel}_index",
                        f"{channel}_type",
                    ])

                return [".", "..", *sorted(entries)]

        raise FuseOSError(errno.ENOENT)

    def readlink(self, path):
        parts = self._parts(path)

        if (
            len(parts) == 1
            and parts[0] in self.native_links
        ):
            return self.native_links[parts[0]]

        raise FuseOSError(errno.ENOENT)

    def open(self, path, flags):
        parts = self._parts(path)

        getter = self._direct_file(parts)

        if getter is not None:
            if flags & (os.O_WRONLY | os.O_RDWR):
                raise FuseOSError(errno.EROFS)

            return 0

        virtual = self._virtual_file(parts)

        if virtual is not None:
            mode, getter = virtual

            if (
                flags & (os.O_WRONLY | os.O_RDWR)
                and mode != "rw"
            ):
                raise FuseOSError(errno.EROFS)

            return 0

        raise FuseOSError(errno.ENOENT)

    def read(self, path, size, offset, fh):
        parts = self._parts(path)

        getter = self._direct_file(parts)

        if getter is None:
            virtual = self._virtual_file(parts)

            if virtual is None:
                raise FuseOSError(errno.ENOENT)

            mode, getter = virtual

        try:
            data = str(getter()) + "\n"
        except FuseOSError:
            raise
        except Exception as e:
            print(
                f"LSAIIOProxy: read error {path}: {e}",
                flush=True,
            )
            raise FuseOSError(errno.EIO)

        data = data.encode()

        return data[offset:offset + size]

    def truncate(self, path, length, fh=None):
        parts = self._parts(path)

        virtual = self._virtual_file(parts)

        if virtual is None:
            raise FuseOSError(errno.EROFS)

        mode, getter = virtual

        if mode != "rw":
            raise FuseOSError(errno.EROFS)

        # Normal shell redirection/libiio opens these attributes
        # with O_TRUNC, which results in truncate(path, 0).
        #
        # sysfs attributes are transactional values, not ordinary
        # files, so accepting the truncate does not clear our
        # current logical state. The following write replaces it.
        if length != 0:
            raise FuseOSError(errno.EINVAL)

        return 0

    def write(self, path, data, offset, fh):
        parts = self._parts(path)

        if len(parts) != 3:
            raise FuseOSError(errno.EROFS)

        devname, directory, filename = parts

        if (
            devname in self.event_state
            and directory == "events"
        ):
            attr = self.event_state[
                devname
            ]["attrs"].get(filename)

            if attr is None:
                raise FuseOSError(errno.ENOENT)

            if attr["mode"] != "rw":
                raise FuseOSError(errno.EROFS)

            try:
                text = data.decode(
                    errors="strict"
                ).rstrip(
                    "\x00\r\n\t "
                )

                value = int(text)

            except Exception:
                raise FuseOSError(errno.EINVAL)

            if filename.endswith("_en"):
                if value not in (0, 1):
                    raise FuseOSError(
                        errno.EINVAL
                    )

            attr["value"] = value

            print(
                f"LSAIIOProxy: write "
                f"/{devname}/events/"
                f"{filename}={value}",
                flush=True,
            )

            return len(data)

        if not self._buffered(devname):
            raise FuseOSError(errno.EROFS)

        state = self.buffer_state[devname]

        try:
            # libiio/sysfs writers may include a trailing NUL.
            text = data.decode(
                errors="strict"
            ).rstrip("\x00\r\n\t ")

            value = int(text)
        except Exception:
            raise FuseOSError(errno.EINVAL)

        if directory == "buffer":
            if filename == "length":
                if value <= 0:
                    raise FuseOSError(errno.EINVAL)

                state["length"] = value

            elif filename == "enable":
                if value not in (0, 1):
                    raise FuseOSError(errno.EINVAL)

                state["enable"] = value

            elif filename == "watermark":
                if value <= 0:
                    raise FuseOSError(errno.EINVAL)

                state["watermark"] = value

            else:
                raise FuseOSError(errno.EROFS)

        elif directory == "scan_elements":
            if not filename.endswith("_en"):
                raise FuseOSError(errno.EROFS)

            channel = filename[:-3]

            if channel not in state["scan"]:
                raise FuseOSError(errno.ENOENT)

            if value not in (0, 1):
                raise FuseOSError(errno.EINVAL)

            state["scan"][channel] = value

        else:
            raise FuseOSError(errno.EROFS)

        #
        # State/on-change devices must react immediately to libiio
        # buffer transitions. Polling FUSE attributes from another
        # process is too racy for this.
        #
        if (
            self.device_meta.get(
                devname,
                {},
            ).get("role")
            == "state"
        ):
            try:
                message = json.dumps({
                    "device": devname,
                    "enable": int(state["enable"]),
                    "scan": dict(state["scan"]),
                }).encode()

                notify = socket.socket(
                    socket.AF_UNIX,
                    socket.SOCK_DGRAM,
                )

                try:
                    notify.sendto(
                        message,
                        STATE_SOCKET,
                    )
                finally:
                    notify.close()

            except OSError:
                # State broker is optional; FUSE must remain usable
                # even when it is not running.
                pass

        print(
            f"LSAIIOProxy: write {path}={value}",
            flush=True,
        )

        return len(data)


def main():
    if len(sys.argv) != 2:
        print(
            f"usage: {sys.argv[0]} MOUNTPOINT",
            file=sys.stderr,
        )
        raise SystemExit(2)

    mountpoint = sys.argv[1]

    FUSE(
        LSAIIOFS(),
        mountpoint,
        foreground=True,
        nothreads=False,

        # Synthetic sysfs values are dynamic and frequently much
        # shorter than their advertised st_size.  Bypass the FUSE
        # page cache so reads have sysfs-like short-read/EOF semantics
        # instead of being zero-padded to st_size.
        direct_io=True,
    )


if __name__ == "__main__":
    main()
