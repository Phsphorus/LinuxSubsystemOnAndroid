#!/data/data/com.termux/files/usr/bin/python

import ctypes as C
import json
import math
import os
import signal
import socket
import threading


HOST = "127.0.0.1"
PORT = 8560
PACKAGE = b"com.termux.api"

lib = C.CDLL("libandroid.so")
P = C.c_void_p


# =========================================================
# ASensorEvent
# =========================================================

class ASensorVector(C.Structure):
    _fields_ = [
        ("x", C.c_float),
        ("y", C.c_float),
        ("z", C.c_float),
        ("status", C.c_int8),
        ("reserved", C.c_uint8 * 3),
    ]


class AUncalibratedEvent(C.Structure):
    _fields_ = [
        ("x_uncalib", C.c_float),
        ("y_uncalib", C.c_float),
        ("z_uncalib", C.c_float),
        ("x_bias", C.c_float),
        ("y_bias", C.c_float),
        ("z_bias", C.c_float),
    ]


class SensorPayload(C.Union):
    _fields_ = [
        ("f32", C.c_float * 16),
        ("u64", C.c_uint64 * 8),
        ("i64", C.c_int64 * 8),
        ("vector", ASensorVector),
        ("uncalibrated", AUncalibratedEvent),
        ("raw", C.c_ubyte * 64),
    ]


class ASensorEvent(C.Structure):
    _fields_ = [
        ("version", C.c_int32),
        ("sensor", C.c_int32),
        ("type", C.c_int32),
        ("reserved0", C.c_int32),
        ("timestamp", C.c_int64),
        ("payload", SensorPayload),
        ("flags", C.c_uint32),
        ("reserved1", C.c_int32 * 3),
    ]


# =========================================================
# Android NDK declarations
# =========================================================

lib.ASensorManager_getInstanceForPackage.argtypes = [C.c_char_p]
lib.ASensorManager_getInstanceForPackage.restype = P

lib.ASensorManager_getSensorList.argtypes = [
    P,
    C.POINTER(C.POINTER(P)),
]
lib.ASensorManager_getSensorList.restype = C.c_int

for name in (
    "ASensor_getName",
    "ASensor_getVendor",
    "ASensor_getStringType",
):
    fn = getattr(lib, name)
    fn.argtypes = [P]
    fn.restype = C.c_char_p

for name in (
    "ASensor_getType",
    "ASensor_getMinDelay",
    "ASensor_getFifoMaxEventCount",
    "ASensor_getFifoReservedEventCount",
    "ASensor_getReportingMode",
):
    fn = getattr(lib, name)
    fn.argtypes = [P]
    fn.restype = C.c_int

lib.ASensor_getResolution.argtypes = [P]
lib.ASensor_getResolution.restype = C.c_float

lib.ASensor_isWakeUpSensor.argtypes = [P]
lib.ASensor_isWakeUpSensor.restype = C.c_bool

lib.ALooper_prepare.argtypes = [C.c_int]
lib.ALooper_prepare.restype = P

lib.ALooper_pollOnce.argtypes = [
    C.c_int,
    C.POINTER(C.c_int),
    C.POINTER(C.c_int),
    C.POINTER(P),
]
lib.ALooper_pollOnce.restype = C.c_int

lib.ASensorManager_createEventQueue.argtypes = [
    P,
    P,
    C.c_int,
    P,
    P,
]
lib.ASensorManager_createEventQueue.restype = P

lib.ASensorManager_destroyEventQueue.argtypes = [P, P]
lib.ASensorManager_destroyEventQueue.restype = C.c_int

lib.ASensorEventQueue_enableSensor.argtypes = [P, P]
lib.ASensorEventQueue_enableSensor.restype = C.c_int

lib.ASensorEventQueue_disableSensor.argtypes = [P, P]
lib.ASensorEventQueue_disableSensor.restype = C.c_int

lib.ASensorEventQueue_setEventRate.argtypes = [
    P,
    P,
    C.c_int32,
]
lib.ASensorEventQueue_setEventRate.restype = C.c_int

lib.ASensorEventQueue_getEvents.argtypes = [
    P,
    C.POINTER(ASensorEvent),
    C.c_size_t,
]
lib.ASensorEventQueue_getEvents.restype = C.c_ssize_t


def android_sdk():
    try:
        with os.popen("/system/bin/getprop ro.build.version.sdk") as f:
            return int(f.read().strip())
    except Exception:
        return 0


SDK = android_sdk()

if SDK < 26:
    raise SystemExit(
        f"HALSensorBus requires supported API 26+; device API={SDK}"
    )


# =========================================================
# Sensor registry
# =========================================================

manager = lib.ASensorManager_getInstanceForPackage(PACKAGE)

if not manager:
    raise SystemExit("ASensorManager_getInstanceForPackage failed")

native_list = C.POINTER(P)()

sensor_count = lib.ASensorManager_getSensorList(
    manager,
    C.byref(native_list),
)

if sensor_count < 0:
    raise SystemExit(f"getSensorList failed: {sensor_count}")


def ctext(p):
    return p.decode(errors="replace") if p else ""


sensors = []

for bus_id in range(sensor_count):
    sensor = native_list[bus_id]

    entry = {
        "bus_id": bus_id,
        "sensor": sensor,
        "type": lib.ASensor_getType(sensor),
        "name": ctext(lib.ASensor_getName(sensor)),
        "vendor": ctext(lib.ASensor_getVendor(sensor)),
        "string_type": ctext(lib.ASensor_getStringType(sensor)),
        "reporting_mode": lib.ASensor_getReportingMode(sensor),
        "wake_up": bool(lib.ASensor_isWakeUpSensor(sensor)),
        "min_delay_us": lib.ASensor_getMinDelay(sensor),
        "resolution": float(lib.ASensor_getResolution(sensor)),
        "fifo_reserved": lib.ASensor_getFifoReservedEventCount(sensor),
        "fifo_max": lib.ASensor_getFifoMaxEventCount(sensor),
    }

    # Handle is useful metadata on API 29+, but never our primary identity.
    if SDK >= 29 and hasattr(lib, "ASensor_getHandle"):
        lib.ASensor_getHandle.argtypes = [P]
        lib.ASensor_getHandle.restype = C.c_int
        entry["android_handle"] = lib.ASensor_getHandle(sensor)

    sensors.append(entry)


def public_meta(entry):
    return {
        k: v
        for k, v in entry.items()
        if k != "sensor"
    }


# =========================================================
# Wire helpers
# =========================================================

def send_json(conn, obj):
    data = (
        json.dumps(
            obj,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode()

    conn.sendall(data)


def clean_float(v):
    v = float(v)
    return v if math.isfinite(v) else None


VECTOR3_TYPES = {
    1,   # accelerometer
    2,   # magnetic field
    3,   # orientation
    4,   # gyroscope
    9,   # gravity
    10,  # linear acceleration
}

UNCALIBRATED_TYPES = {
    14,  # magnetic field uncalibrated
    16,  # gyroscope uncalibrated
    35,  # accelerometer uncalibrated
}

SINGLE_VALUE_TYPES = {
    5,   # light
    6,   # pressure
    8,   # proximity
    17,  # significant motion
    18,  # step detector
    23,  # wake gesture
}

ROTATION_VALUE_COUNTS = {
    11: 5,  # rotation vector
    15: 4,  # game rotation vector
    20: 5,  # geomagnetic rotation vector
}


def event_payload(event):
    t = event.type

    if t in VECTOR3_TYPES:
        v = event.payload.vector

        return {
            "values": [
                clean_float(v.x),
                clean_float(v.y),
                clean_float(v.z),
            ],
            "accuracy": int(v.status),
        }

    if t in UNCALIBRATED_TYPES:
        v = event.payload.uncalibrated

        return {
            "values": [
                clean_float(v.x_uncalib),
                clean_float(v.y_uncalib),
                clean_float(v.z_uncalib),
                clean_float(v.x_bias),
                clean_float(v.y_bias),
                clean_float(v.z_bias),
            ],
        }

    if t == 19:
        return {
            "step_counter": int(event.payload.u64[0]),
        }

    if t in SINGLE_VALUE_TYPES:
        return {
            "values": [
                clean_float(event.payload.f32[0]),
            ],
        }

    if t in ROTATION_VALUE_COUNTS:
        count = ROTATION_VALUE_COUNTS[t]

        return {
            "values": [
                clean_float(event.payload.f32[i])
                for i in range(count)
            ],
        }

    # Unknown/future Android sensor type.
    # Preserve its payload for debugging without pretending we
    # understand the semantics.
    return {
        "raw_f32": [
            clean_float(event.payload.f32[i])
            for i in range(16)
        ],
    }


# =========================================================
# WATCH implementation
#
# One connection owns one ASensorEventQueue.
# This means API 26 does NOT need ASensor_getHandle() to
# distinguish duplicate sensor types.
# =========================================================

def watch_sensor(conn, entry, requested_period):
    sensor = entry["sensor"]

    ALOOPER_PREPARE_ALLOW_NON_CALLBACKS = 1

    looper = lib.ALooper_prepare(
        ALOOPER_PREPARE_ALLOW_NON_CALLBACKS
    )

    if not looper:
        send_json(conn, {
            "kind": "error",
            "error": "looper_prepare_failed",
        })
        return

    queue = lib.ASensorManager_createEventQueue(
        manager,
        looper,
        1,
        None,
        None,
    )

    if not queue:
        send_json(conn, {
            "kind": "error",
            "error": "event_queue_failed",
        })
        return

    try:
        rc = lib.ASensorEventQueue_enableSensor(
            queue,
            sensor,
        )

        if rc < 0:
            send_json(conn, {
                "kind": "error",
                "error": "enable_failed",
                "code": rc,
                "bus_id": entry["bus_id"],
            })
            return

        actual_period = None

        # Continuous sensors only.
        if entry["reporting_mode"] == 0:
            min_delay = max(
                0,
                entry["min_delay_us"],
            )

            if requested_period is None:
                requested_period = 20_000

            actual_period = max(
                min_delay,
                requested_period,
            )

            rc = lib.ASensorEventQueue_setEventRate(
                queue,
                sensor,
                actual_period,
            )

            if rc < 0:
                send_json(conn, {
                    "kind": "error",
                    "error": "set_rate_failed",
                    "code": rc,
                    "bus_id": entry["bus_id"],
                })
                return

        send_json(conn, {
            "kind": "watch",
            "sensor": public_meta(entry),
            "period_us": actual_period,
        })

        events = (ASensorEvent * 64)()

        while True:
            lib.ALooper_pollOnce(
                1000,
                None,
                None,
                None,
            )

            while True:
                n = lib.ASensorEventQueue_getEvents(
                    queue,
                    events,
                    len(events),
                )

                if n <= 0:
                    break

                for i in range(n):
                    event = events[i]

                    payload = event_payload(event)

                    send_json(conn, {
                        "kind": "event",
                        "bus_id": entry["bus_id"],
                        "type": event.type,
                        "timestamp_ns": int(event.timestamp),
                        "flags": int(event.flags),
                        **payload,
                    })

                    #
                    # Android reporting mode 2 is one-shot.
                    # The framework/HAL automatically disables the
                    # sensor after the trigger fires.
                    #
                    # End this WATCH immediately so finally() destroys
                    # the now-consumed ASensorEventQueue. Leaving the
                    # queue alive can prevent a later WATCH from
                    # genuinely re-arming some vendor HALs.
                    #
                    if entry["reporting_mode"] == 2:
                        return

    except (
        BrokenPipeError,
        ConnectionResetError,
        socket.timeout,
        OSError,
    ):
        pass

    finally:
        try:
            lib.ASensorEventQueue_disableSensor(
                queue,
                sensor,
            )
        except Exception:
            pass

        try:
            lib.ASensorManager_destroyEventQueue(
                manager,
                queue,
            )
        except Exception:
            pass


# =========================================================
# Client protocol
#
# LIST
# WATCH <bus_id> [period_us]
# PING
# =========================================================

def client_thread(conn, addr):
    # Never allow a dead/slow Debian reader to produce an
    # unbounded sensor history.
    conn.settimeout(2.0)

    try:
        f = conn.makefile("rb")

        line = f.readline(512)

        if not line:
            return

        fields = line.decode(
            "ascii",
            errors="replace",
        ).strip().split()

        if not fields:
            return

        command = fields[0].upper()

        if command == "PING":
            send_json(conn, {
                "kind": "pong",
                "version": 1,
                "sdk": SDK,
            })
            return

        if command == "LIST":
            send_json(conn, {
                "kind": "hello",
                "protocol": "LSASENSOR1",
                "sdk": SDK,
                "count": len(sensors),
            })

            for entry in sensors:
                send_json(conn, {
                    "kind": "sensor",
                    **public_meta(entry),
                })

            send_json(conn, {
                "kind": "end",
                "count": len(sensors),
            })
            return

        if command == "WATCH":
            if len(fields) < 2:
                send_json(conn, {
                    "kind": "error",
                    "error": "usage WATCH <bus_id> [period_us]",
                })
                return

            try:
                bus_id = int(fields[1])
            except ValueError:
                send_json(conn, {
                    "kind": "error",
                    "error": "bad_bus_id",
                })
                return

            if not 0 <= bus_id < len(sensors):
                send_json(conn, {
                    "kind": "error",
                    "error": "unknown_bus_id",
                })
                return

            period = None

            if len(fields) >= 3:
                try:
                    period = int(fields[2])
                except ValueError:
                    send_json(conn, {
                        "kind": "error",
                        "error": "bad_period",
                    })
                    return

                if period <= 0:
                    send_json(conn, {
                        "kind": "error",
                        "error": "bad_period",
                    })
                    return

            # Blocking WATCH owns this connection.
            conn.settimeout(0.25)

            watch_sensor(
                conn,
                sensors[bus_id],
                period,
            )
            return

        send_json(conn, {
            "kind": "error",
            "error": "unknown_command",
        })

    finally:
        try:
            conn.close()
        except Exception:
            pass


# =========================================================
# Server
# =========================================================

running = True


def stop_signal(_signum, _frame):
    global running
    running = False


signal.signal(signal.SIGTERM, stop_signal)
signal.signal(signal.SIGINT, stop_signal)

server = socket.socket(
    socket.AF_INET,
    socket.SOCK_STREAM,
)

server.setsockopt(
    socket.SOL_SOCKET,
    socket.SO_REUSEADDR,
    1,
)

server.bind((HOST, PORT))
server.listen(32)
server.settimeout(1.0)

print(
    f"HALSensorBus: LSASENSOR1 "
    f"listening {HOST}:{PORT} "
    f"sdk={SDK} sensors={len(sensors)}",
    flush=True,
)

while running:
    try:
        conn, addr = server.accept()

    except socket.timeout:
        continue

    except OSError:
        break

    threading.Thread(
        target=client_thread,
        args=(conn, addr),
        daemon=True,
    ).start()

try:
    server.close()
except Exception:
    pass

print("HALSensorBus: stopped", flush=True)
