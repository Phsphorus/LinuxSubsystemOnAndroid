#!/usr/bin/python3

import dbus
import dbus.service
import dbus.mainloop.glib

import json
import math
import os
import socket
import threading
import time

from gi.repository import GLib


BUS_NAME = "net.hadess.SensorProxy"

MAIN_PATH = "/net/hadess/SensorProxy"
COMPASS_PATH = "/net/hadess/SensorProxy/Compass"

MAIN_IFACE = "net.hadess.SensorProxy"
COMPASS_IFACE = "net.hadess.SensorProxy.Compass"

PROPS_IFACE = "org.freedesktop.DBus.Properties"
INTROSPECT_IFACE = "org.freedesktop.DBus.Introspectable"

SENSOR_HOST = "127.0.0.1"
SENSOR_PORT = 8560


SENSOR_TYPES = {
    "accel": "android.sensor.accelerometer",
    "light": "android.sensor.light",
    "proximity": "android.sensor.proximity",
    "compass": "android.sensor.orientation",
}


MAIN_XML = """\
<node>
  <interface name="net.hadess.SensorProxy">
    <property name="HasAccelerometer" type="b" access="read"/>
    <property name="AccelerometerOrientation" type="s" access="read"/>
    <property name="AccelerometerTilt" type="s" access="read"/>

    <property name="HasAmbientLight" type="b" access="read"/>
    <property name="LightLevelUnit" type="s" access="read"/>
    <property name="LightLevel" type="d" access="read"/>

    <property name="HasProximity" type="b" access="read"/>
    <property name="ProximityNear" type="b" access="read"/>

    <method name="ClaimAccelerometer"/>
    <method name="ReleaseAccelerometer"/>
    <method name="ClaimLight"/>
    <method name="ReleaseLight"/>
    <method name="ClaimProximity"/>
    <method name="ReleaseProximity"/>
  </interface>
</node>
"""


COMPASS_XML = """\
<node>
  <interface name="net.hadess.SensorProxy.Compass">
    <property name="HasCompass" type="b" access="read"/>
    <property name="CompassHeading" type="d" access="read"/>

    <method name="ClaimCompass"/>
    <method name="ReleaseCompass"/>
  </interface>
</node>
"""


def list_sensorbus():
    sensors = {}

    sock = socket.create_connection(
        (SENSOR_HOST, SENSOR_PORT),
        timeout=3,
    )

    try:
        sock.sendall(b"LIST\n")
        f = sock.makefile("r", encoding="utf-8")

        for line in f:
            try:
                msg = json.loads(line)
            except Exception:
                continue

            if msg.get("kind") == "sensor":
                st = msg.get("string_type")
                if st:
                    sensors[st] = msg

            if msg.get("kind") == "end":
                break

    finally:
        sock.close()

    return sensors


def stock_orientation(previous, x, y, z):
    #
    # Equivalent geometry/thresholds to iio-sensor-proxy 3.7.
    #

    portrait = math.degrees(
        math.atan2(
            x,
            math.sqrt(y * y + z * z),
        )
    )

    landscape = math.degrees(
        math.atan2(
            y,
            math.sqrt(x * x + z * z),
        )
    )

    # Don't switch while sitting in the ambiguous corner region.
    if abs(portrait) > 35.0 and abs(landscape) > 35.0:
        return previous

    if abs(portrait) > 35.0:
        if portrait > 0:
            return "left-up"

        return "right-up"

    if abs(landscape) > 35.0:
        if landscape > 0:
            return "bottom-up"

        return "normal"

    return previous


def stock_tilt(x, y, z):
    tilt = math.degrees(
        math.atan2(
            z,
            math.sqrt(x * x + y * y),
        )
    )

    a = abs(tilt)

    if a <= 20.0:
        return "vertical"

    if a < 70.0:
        if tilt > 0:
            return "tilted-up"

        return "tilted-down"

    if a <= 90.0:
        if tilt > 0:
            return "face-up"

        return "face-down"

    return "undefined"


class StreamWorker:

    def __init__(self, backend, kind):
        self.backend = backend
        self.kind = kind

        self.stop_event = threading.Event()
        self.thread = None
        self.sock = None

    def start(self):
        if self.thread is not None and self.thread.is_alive():
            return

        self.stop_event.clear()

        self.thread = threading.Thread(
            target=self.run,
            daemon=True,
            name=f"LSASensor-{self.kind}",
        )

        self.thread.start()

    def stop(self):
        self.stop_event.set()

        sock = self.sock

        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass

            try:
                sock.close()
            except Exception:
                pass

    def run(self):
        while not self.stop_event.is_set():

            sensor = self.backend.sensor_for(self.kind)

            if sensor is None:
                time.sleep(1)
                continue

            bus_id = sensor["bus_id"]

            if self.kind in ("accel", "compass"):
                command = f"WATCH {bus_id} 20000\n"
            else:
                command = f"WATCH {bus_id}\n"

            sock = None

            try:
                print(
                    f"LSASensorProxy: WATCH "
                    f"{self.kind} bus_id={bus_id}",
                    flush=True,
                )

                sock = socket.create_connection(
                    (SENSOR_HOST, SENSOR_PORT),
                    timeout=3,
                )

                self.sock = sock

                sock.settimeout(None)
                sock.sendall(command.encode())

                f = sock.makefile(
                    "r",
                    encoding="utf-8",
                )

                for line in f:

                    if self.stop_event.is_set():
                        break

                    try:
                        msg = json.loads(line)
                    except Exception:
                        continue

                    if msg.get("kind") != "event":
                        continue

                    self.backend.handle_event(
                        self.kind,
                        msg,
                    )

            except Exception as e:
                if not self.stop_event.is_set():
                    print(
                        f"LSASensorProxy: "
                        f"{self.kind} stream error: {e}",
                        flush=True,
                    )

            finally:
                self.sock = None

                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass

            if not self.stop_event.is_set():
                time.sleep(1)


class MainProxy(dbus.service.Object):

    def __init__(self, bus_name, backend):
        super().__init__(bus_name, MAIN_PATH)

        self.backend = backend

        self.props = {
            "HasAccelerometer": dbus.Boolean(False),
            "AccelerometerOrientation":
                dbus.String("undefined"),
            "AccelerometerTilt":
                dbus.String("undefined"),

            "HasAmbientLight": dbus.Boolean(False),
            "LightLevelUnit": dbus.String("lux"),
            "LightLevel": dbus.Double(0.0),

            "HasProximity": dbus.Boolean(False),
            "ProximityNear": dbus.Boolean(False),
        }

    @dbus.service.method(
        PROPS_IFACE,
        in_signature="ss",
        out_signature="v",
    )
    def Get(self, interface, name):
        if interface != MAIN_IFACE or name not in self.props:
            raise dbus.exceptions.DBusException(
                "Invalid property"
            )

        return self.props[name]

    @dbus.service.method(
        PROPS_IFACE,
        in_signature="s",
        out_signature="a{sv}",
    )
    def GetAll(self, interface):
        if interface != MAIN_IFACE:
            return {}

        return self.props

    @dbus.service.method(
        PROPS_IFACE,
        in_signature="ssv",
        out_signature="",
    )
    def Set(self, interface, name, value):
        raise dbus.exceptions.DBusException(
            "Property is read-only"
        )

    @dbus.service.signal(
        PROPS_IFACE,
        signature="sa{sv}as",
    )
    def PropertiesChanged(
        self,
        interface,
        changed,
        invalidated,
    ):
        pass

    def change(self, name, value):
        if self.props.get(name) == value:
            return

        self.props[name] = value

        self.PropertiesChanged(
            MAIN_IFACE,
            {name: value},
            [],
        )

    @dbus.service.method(
        INTROSPECT_IFACE,
        in_signature="",
        out_signature="s",
    )
    def Introspect(self):
        return MAIN_XML

    @dbus.service.method(
        MAIN_IFACE,
        sender_keyword="sender",
    )
    def ClaimAccelerometer(self, sender=None):
        self.backend.claim("accel", sender)

    @dbus.service.method(
        MAIN_IFACE,
        sender_keyword="sender",
    )
    def ReleaseAccelerometer(self, sender=None):
        self.backend.release("accel", sender)

    @dbus.service.method(
        MAIN_IFACE,
        sender_keyword="sender",
    )
    def ClaimLight(self, sender=None):
        self.backend.claim("light", sender)

    @dbus.service.method(
        MAIN_IFACE,
        sender_keyword="sender",
    )
    def ReleaseLight(self, sender=None):
        self.backend.release("light", sender)

    @dbus.service.method(
        MAIN_IFACE,
        sender_keyword="sender",
    )
    def ClaimProximity(self, sender=None):
        self.backend.claim("proximity", sender)

    @dbus.service.method(
        MAIN_IFACE,
        sender_keyword="sender",
    )
    def ReleaseProximity(self, sender=None):
        self.backend.release("proximity", sender)


class CompassProxy(dbus.service.Object):

    def __init__(self, bus_name, backend):
        super().__init__(bus_name, COMPASS_PATH)

        self.backend = backend

        self.props = {
            "HasCompass": dbus.Boolean(False),
            "CompassHeading": dbus.Double(-1.0),
        }

    @dbus.service.method(
        PROPS_IFACE,
        in_signature="ss",
        out_signature="v",
    )
    def Get(self, interface, name):
        if interface != COMPASS_IFACE or name not in self.props:
            raise dbus.exceptions.DBusException(
                "Invalid property"
            )

        return self.props[name]

    @dbus.service.method(
        PROPS_IFACE,
        in_signature="s",
        out_signature="a{sv}",
    )
    def GetAll(self, interface):
        if interface != COMPASS_IFACE:
            return {}

        return self.props

    @dbus.service.method(
        PROPS_IFACE,
        in_signature="ssv",
        out_signature="",
    )
    def Set(self, interface, name, value):
        raise dbus.exceptions.DBusException(
            "Property is read-only"
        )

    @dbus.service.signal(
        PROPS_IFACE,
        signature="sa{sv}as",
    )
    def PropertiesChanged(
        self,
        interface,
        changed,
        invalidated,
    ):
        pass

    def change(self, name, value):
        if self.props.get(name) == value:
            return

        self.props[name] = value

        self.PropertiesChanged(
            COMPASS_IFACE,
            {name: value},
            [],
        )

    @dbus.service.method(
        INTROSPECT_IFACE,
        in_signature="",
        out_signature="s",
    )
    def Introspect(self):
        return COMPASS_XML

    @dbus.service.method(
        COMPASS_IFACE,
        sender_keyword="sender",
    )
    def ClaimCompass(self, sender=None):
        self.backend.claim("compass", sender)

    @dbus.service.method(
        COMPASS_IFACE,
        sender_keyword="sender",
    )
    def ReleaseCompass(self, sender=None):
        self.backend.release("compass", sender)


class Backend:

    def __init__(self, bus):
        self.bus = bus

        self.main = None
        self.compass = None

        self.registry = {}
        self.sensors = {}

        self.claims = {
            kind: set()
            for kind in SENSOR_TYPES
        }

        self.workers = {
            kind: StreamWorker(self, kind)
            for kind in SENSOR_TYPES
        }

        self.fx = None
        self.fy = None
        self.fz = None

        self.orientation = "undefined"
        self.tilt = "undefined"

        self.orientation_candidate = None
        self.orientation_candidate_since = 0.0

        self.tilt_candidate = None
        self.tilt_candidate_since = 0.0

        self.proximity_far_reference = None

        threshold = os.environ.get(
            "LSA_PROXIMITY_NEAR_CM"
        )

        self.proximity_threshold = None

        if threshold:
            try:
                self.proximity_threshold = float(threshold)
            except Exception:
                pass

        self.compass_heading = -1.0

        self.refresh_registry()

        bus.add_signal_receiver(
            self.name_owner_changed,
            signal_name="NameOwnerChanged",
            dbus_interface="org.freedesktop.DBus",
            bus_name="org.freedesktop.DBus",
            path="/org/freedesktop/DBus",
        )

    def attach(self, main, compass):
        self.main = main
        self.compass = compass
        self.publish_presence()

    def refresh_registry(self):
        try:
            self.registry = list_sensorbus()
        except Exception as e:
            print(
                f"LSASensorProxy: LIST failed: {e}",
                flush=True,
            )

            self.registry = {}

        self.sensors = {
            kind: self.registry.get(string_type)
            for kind, string_type in SENSOR_TYPES.items()
        }

    def sensor_for(self, kind):
        return self.sensors.get(kind)

    def publish_presence(self):
        if self.main is None:
            return

        self.main.change(
            "HasAccelerometer",
            dbus.Boolean(
                self.sensor_for("accel") is not None
            ),
        )

        self.main.change(
            "HasAmbientLight",
            dbus.Boolean(
                self.sensor_for("light") is not None
            ),
        )

        self.main.change(
            "HasProximity",
            dbus.Boolean(
                self.sensor_for("proximity") is not None
            ),
        )

        self.compass.change(
            "HasCompass",
            dbus.Boolean(
                self.sensor_for("compass") is not None
            ),
        )

    def claim(self, kind, sender):
        sender = str(sender or "unknown")

        self.refresh_registry()
        self.publish_presence()

        first = not self.claims[kind]

        self.claims[kind].add(sender)

        print(
            f"LSASensorProxy: claim "
            f"{kind} sender={sender} "
            f"claims={len(self.claims[kind])}",
            flush=True,
        )

        if first and self.sensor_for(kind) is not None:
            self.workers[kind].start()

    def release(self, kind, sender):
        sender = str(sender or "unknown")

        self.claims[kind].discard(sender)

        print(
            f"LSASensorProxy: release "
            f"{kind} sender={sender} "
            f"claims={len(self.claims[kind])}",
            flush=True,
        )

        if not self.claims[kind]:
            self.workers[kind].stop()

    def name_owner_changed(
        self,
        name,
        old_owner,
        new_owner,
    ):
        if not old_owner or new_owner:
            return

        sender = str(name)

        for kind in self.claims:
            if sender in self.claims[kind]:
                self.claims[kind].discard(sender)

                print(
                    f"LSASensorProxy: client vanished "
                    f"{sender}; released {kind}",
                    flush=True,
                )

                if not self.claims[kind]:
                    self.workers[kind].stop()

    def handle_event(self, kind, msg):
        values = msg.get("values")

        if not isinstance(values, list):
            return

        if kind == "accel" and len(values) >= 3:
            GLib.idle_add(
                self.apply_accel,
                float(values[0]),
                float(values[1]),
                float(values[2]),
            )

        elif kind == "light" and values:
            GLib.idle_add(
                self.apply_light,
                float(values[0]),
            )

        elif kind == "proximity" and values:
            GLib.idle_add(
                self.apply_proximity,
                float(values[0]),
            )

        elif kind == "compass" and values:
            GLib.idle_add(
                self.apply_compass,
                float(values[0]),
            )

    def stabilize_orientation(self, value):
        if value == self.orientation:
            self.orientation_candidate = None
            return

        now = time.monotonic()

        if value != self.orientation_candidate:
            self.orientation_candidate = value
            self.orientation_candidate_since = now
            return

        if now - self.orientation_candidate_since < 0.20:
            return

        old = self.orientation
        self.orientation = value
        self.orientation_candidate = None

        self.main.change(
            "AccelerometerOrientation",
            dbus.String(value),
        )

        print(
            f"LSASensorProxy: orientation "
            f"{old} -> {value}",
            flush=True,
        )

    def stabilize_tilt(self, value):
        if value == self.tilt:
            self.tilt_candidate = None
            return

        now = time.monotonic()

        if value != self.tilt_candidate:
            self.tilt_candidate = value
            self.tilt_candidate_since = now
            return

        if now - self.tilt_candidate_since < 0.20:
            return

        old = self.tilt
        self.tilt = value
        self.tilt_candidate = None

        self.main.change(
            "AccelerometerTilt",
            dbus.String(value),
        )

        print(
            f"LSASensorProxy: tilt "
            f"{old} -> {value}",
            flush=True,
        )

    def apply_accel(self, x, y, z):
        #
        # Low-pass the Android stream before applying stock
        # iio-sensor-proxy classification.
        #
        alpha = 0.18

        if self.fx is None:
            self.fx = x
            self.fy = y
            self.fz = z
        else:
            self.fx = alpha * x + (1.0 - alpha) * self.fx
            self.fy = alpha * y + (1.0 - alpha) * self.fy
            self.fz = alpha * z + (1.0 - alpha) * self.fz

        orientation = stock_orientation(
            self.orientation,
            self.fx,
            self.fy,
            self.fz,
        )

        tilt = stock_tilt(
            self.fx,
            self.fy,
            self.fz,
        )

        self.stabilize_orientation(orientation)
        self.stabilize_tilt(tilt)

        return False

    def apply_light(self, level):
        old = float(self.main.props["LightLevel"])

        if abs(level - old) < 0.01:
            return False

        self.main.change(
            "LightLevel",
            dbus.Double(level),
        )

        print(
            f"LSASensorProxy: light {level:.3f} lux",
            flush=True,
        )

        return False

    def apply_proximity(self, distance):
        #
        # Android reports proximity as distance.
        #
        # If a device-specific threshold is configured, use it.
        # Otherwise learn the observed "far" value. This works
        # cleanly with common binary sensors such as this device's
        # 0 cm / 5 cm sensor.
        #

        if self.proximity_threshold is not None:
            near = distance < self.proximity_threshold

        else:
            if distance <= 0.001:
                near = True

            else:
                if (
                    self.proximity_far_reference is None
                    or distance > self.proximity_far_reference
                ):
                    self.proximity_far_reference = distance

                threshold = (
                    self.proximity_far_reference * 0.5
                )

                near = distance < threshold

        old = bool(self.main.props["ProximityNear"])

        if near != old:
            self.main.change(
                "ProximityNear",
                dbus.Boolean(near),
            )

            print(
                f"LSASensorProxy: proximity "
                f"distance={distance:.3f} "
                f"near={near}",
                flush=True,
            )

        return False

    def apply_compass(self, heading):
        heading %= 360.0

        old = self.compass_heading

        if old >= 0:
            diff = abs(
                ((heading - old + 180.0) % 360.0) - 180.0
            )

            # Avoid publishing tiny magnetic jitter.
            if diff < 1.0:
                return False

        self.compass_heading = heading

        self.compass.change(
            "CompassHeading",
            dbus.Double(heading),
        )

        print(
            f"LSASensorProxy: compass "
            f"{heading:.2f} deg",
            flush=True,
        )

        return False


def main():
    dbus.mainloop.glib.DBusGMainLoop(
        set_as_default=True
    )

    bus = dbus.SystemBus()

    name = dbus.service.BusName(
        BUS_NAME,
        bus=bus,
        do_not_queue=True,
    )

    backend = Backend(bus)

    main_proxy = MainProxy(
        name,
        backend,
    )

    compass_proxy = CompassProxy(
        name,
        backend,
    )

    backend.attach(
        main_proxy,
        compass_proxy,
    )

    print(
        "LSASensorProxy: owns net.hadess.SensorProxy",
        flush=True,
    )

    for kind, sensor in backend.sensors.items():
        if sensor is None:
            print(
                f"LSASensorProxy: {kind}: absent",
                flush=True,
            )
        else:
            print(
                f"LSASensorProxy: {kind}: "
                f"bus_id={sensor['bus_id']} "
                f"name={sensor.get('name')}",
                flush=True,
            )

    GLib.MainLoop().run()


if __name__ == "__main__":
    main()
