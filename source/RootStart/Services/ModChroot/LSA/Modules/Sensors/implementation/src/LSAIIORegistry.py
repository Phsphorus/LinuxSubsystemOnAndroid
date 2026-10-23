#!/usr/bin/python3

import argparse
import json
import os
import socket
from pathlib import Path


DEFAULT_HOST = os.environ.get(
    "LSA_SENSORBUS_HOST",
    "127.0.0.1",
)

DEFAULT_PORT = int(
    os.environ.get(
        "LSA_SENSORBUS_PORT",
        "8560",
    )
)


#
# This table describes Linux representation semantics.
#
# It does NOT contain Android bus IDs or Linux IIO device numbers.
#
# bus_id comes from HALSensorBus.
# iio:deviceN comes from runtime native-IIO discovery.
#
SPECS = [
    {
        "kind": "accel",
        "role": "stream",
        "string_type":
            "android.sensor.accelerometer",
    },
    {
        "kind": "gyro",
        "role": "stream",
        "string_type":
            "android.sensor.gyroscope",
    },
    {
        "kind": "magn",
        "role": "stream",
        "string_type":
            "android.sensor.magnetic_field",
    },
    {
        "kind": "pressure",
        "role": "stream",
        "string_type":
            "android.sensor.pressure",
    },
    {
        "kind": "accel_uncal",
        "role": "stream",
        "string_type":
            "android.sensor.accelerometer_uncalibrated",
    },
    {
        "kind": "gyro_uncal",
        "role": "stream",
        "string_type":
            "android.sensor.gyroscope_uncalibrated",
    },
    {
        "kind": "magn_uncal",
        "role": "stream",
        "string_type":
            "android.sensor.magnetic_field_uncalibrated",
    },
    {
        "kind": "light",
        "role": "state",
        "string_type":
            "android.sensor.light",
    },
    {
        "kind": "proximity",
        "role": "state",
        "string_type":
            "android.sensor.proximity",
    },
    {
        "kind": "gravity",
        "role": "stream",
        "string_type":
            "android.sensor.gravity",
    },
    {
        "kind": "linear",
        "role": "stream",
        "string_type":
            "android.sensor.linear_acceleration",
    },
    {
        "kind": "rotation",
        "role": "stream",
        "string_type":
            "android.sensor.rotation_vector",
    },
    {
        "kind": "game_rotation",
        "role": "stream",
        "string_type":
            "android.sensor.game_rotation_vector",
    },
    {
        "kind": "geomagnetic_rotation",
        "role": "stream",
        "string_type":
            "android.sensor.geomagnetic_rotation_vector",
    },
    {
        "kind": "orientation",
        "role": "stream",
        "string_type":
            "android.sensor.orientation",
    },
    {
        "kind": "steps",
        "role": "state",
        "string_type":
            "android.sensor.step_counter",
    },

    {
        "kind": "significant_motion",
        "role": "event",
        "string_type":
            "android.sensor.significant_motion",
        "wake_up": True,
        "event": {
            "enable_attr":
                "in_activity_change_en",
            "channel_type": 19,
            "event_type": 5,
            "direction": 0,
        },
    },
    {
        "kind": "step_detector",
        "role": "event",
        "string_type":
            "android.sensor.step_detector",
        "wake_up": False,
        "event": {
            "enable_attr":
                "in_steps_change_en",
            "value_attr":
                "in_steps_change_value",
            "value": 1,
            "channel_type": 20,
            "event_type": 5,
            "direction": 0,
        },
    },
    {
        "kind": "wake_gesture",
        "role": "event",
        "string_type":
            "android.sensor.wake_gesture",
        "wake_up": True,
        "event": {
            "enable_attr":
                "in_activity_change_en",
            "channel_type": 19,
            "event_type": 7,
            "direction": 0,
        },
    },
    {
        "kind": "step_detector_wakeup",
        "role": "event",
        "string_type":
            "android.sensor.step_detector",
        "wake_up": True,
        "event": {
            "enable_attr":
                "in_steps_change_en",
            "value_attr":
                "in_steps_change_value",
            "value": 1,
            "channel_type": 20,
            "event_type": 5,
            "direction": 0,
        },
    },
]


def sensorbus_list(host, port):
    sock = socket.create_connection(
        (host, port),
        timeout=3,
    )

    sensors = []

    try:
        sock.sendall(b"LIST\n")

        f = sock.makefile(
            "r",
            encoding="utf-8",
        )

        for line in f:
            try:
                msg = json.loads(line)
            except Exception:
                continue

            if msg.get("kind") == "sensor":
                sensors.append(msg)

            elif msg.get("kind") == "end":
                break

    finally:
        sock.close()

    sensors.sort(
        key=lambda x: int(x["bus_id"])
    )

    return sensors


def native_iio_devices():
    base = Path(
        "/sys/bus/iio/devices"
    )

    result = []

    try:
        names = list(base.iterdir())
    except Exception:
        return result

    for path in names:
        name = path.name

        if not name.startswith(
            "iio:device"
        ):
            continue

        try:
            index = int(
                name[len("iio:device"):]
            )
        except Exception:
            continue

        sensor_name = ""

        try:
            sensor_name = (
                path / "name"
            ).read_text().strip()
        except Exception:
            pass

        #
        # This also makes registry generation safe while our
        # prototype FUSE tree is currently mounted:
        # never mistake an existing LSA synthetic device for
        # native kernel IIO.
        #
        if sensor_name.startswith("lsa-"):
            continue

        try:
            target = os.path.realpath(
                str(path)
            )
        except Exception:
            target = str(path)

        result.append({
            "index": index,
            "dirname": name,
            "name": sensor_name,
            "target": target,
        })

    result.sort(
        key=lambda x: x["index"]
    )

    return result


def matches(sensor, spec):
    if (
        sensor.get("string_type")
        != spec["string_type"]
    ):
        return False

    if "wake_up" in spec:
        if (
            bool(sensor.get("wake_up", False))
            != bool(spec["wake_up"])
        ):
            return False

    return True


def build_registry(host, port):
    sensors = sensorbus_list(
        host,
        port,
    )

    native = native_iio_devices()

    if native:
        next_index = max(
            x["index"]
            for x in native
        ) + 1
    else:
        next_index = 0

    used_bus_ids = set()
    devices = []
    missing = []

    for spec in SPECS:
        candidates = [
            sensor
            for sensor in sensors
            if (
                int(sensor["bus_id"])
                not in used_bus_ids
                and matches(sensor, spec)
            )
        ]

        if not candidates:
            missing.append({
                "kind": spec["kind"],
                "string_type":
                    spec["string_type"],
                "wake_up":
                    spec.get("wake_up"),
            })
            continue

        #
        # Deterministic if a vendor exposes multiple physical
        # implementations of the same public semantic sensor.
        #
        sensor = sorted(
            candidates,
            key=lambda x: int(
                x["bus_id"]
            ),
        )[0]

        bus_id = int(
            sensor["bus_id"]
        )

        used_bus_ids.add(bus_id)

        entry = {
            "index": next_index,
            "dirname":
                f"iio:device{next_index}",
            "kind": spec["kind"],
            "role": spec["role"],
            "bus_id": bus_id,
            "string_type":
                sensor.get(
                    "string_type",
                    "",
                ),
            "android_name":
                sensor.get(
                    "name",
                    "",
                ),
            "reporting_mode":
                int(
                    sensor.get(
                        "reporting_mode",
                        0,
                    )
                ),
            "wake_up":
                bool(
                    sensor.get(
                        "wake_up",
                        False,
                    )
                ),
            "sensor": sensor,
        }

        if "event" in spec:
            entry["event"] = dict(
                spec["event"]
            )

        devices.append(entry)
        next_index += 1

    return {
        "version": 1,

        "sensorbus": {
            "host": host,
            "port": port,
        },

        "native": native,

        "first_synthetic_index":
            (
                devices[0]["index"]
                if devices
                else next_index
            ),

        "devices": devices,

        "missing": missing,
    }


def atomic_write(path, obj):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_name(
        path.name + ".tmp"
    )

    with tmp.open("w") as f:
        json.dump(
            obj,
            f,
            indent=2,
            sort_keys=True,
        )

        f.write("\n")

    os.replace(
        tmp,
        path,
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
    )

    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
    )

    parser.add_argument(
        "--output",
        default=
            "/run/lsa-iio/registry.json",
    )

    args = parser.parse_args()

    registry = build_registry(
        args.host,
        args.port,
    )

    atomic_write(
        args.output,
        registry,
    )

    print(
        "LSAIIORegistry: "
        f"native={len(registry['native'])} "
        f"synthetic={len(registry['devices'])} "
        f"missing={len(registry['missing'])} "
        f"first="
        f"{registry['first_synthetic_index']}"
    )

    for dev in registry["devices"]:
        print(
            "LSAIIORegistry: "
            f"{dev['dirname']} "
            f"role={dev['role']} "
            f"kind={dev['kind']} "
            f"<- bus_id={dev['bus_id']} "
            f"wake={dev['wake_up']}"
        )

    if registry["missing"]:
        for item in registry["missing"]:
            print(
                "LSAIIORegistry: "
                "MISSING "
                f"{item['kind']} "
                f"{item['string_type']} "
                f"wake={item['wake_up']}"
            )


if __name__ == "__main__":
    main()
