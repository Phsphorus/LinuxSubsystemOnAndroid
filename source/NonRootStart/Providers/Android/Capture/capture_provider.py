#!/data/data/com.termux/files/usr/bin/python
"""Termux-user Android camera and location provider.

Android acquisition stays in the Termux UID.  Consumers use ordinary Linux
endpoints: MJPEG over loopback HTTP and the GPSD JSON protocol over TCP.
"""

from __future__ import annotations

import json
import os
import signal
import socketserver
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE = Path(__file__).resolve().parent
STATE = BASE / "state"
CAMERA_DIR = STATE / "camera"
SECRET_FILE = STATE / "secret"
CAMERA_PORT = 8765
CONTROL_PORT = 8766
GPSD_PORT = 2947
TERMUX_BIN = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr")) / "bin"
CAMERA_COMMAND = TERMUX_BIN / "termux-camera-photo"
FFMPEG_COMMAND = TERMUX_BIN / "ffmpeg"
LOCATION_COMMAND = TERMUX_BIN / "termux-location"


def bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


def bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(minimum, min(value, maximum))


# Termux:API supplies still JPEGs.  Keep the Linux-facing stream modest enough
# for ordinary V4L2 consumers; the unscaled Android capture can exceed 9 MB per
# frame on the N6000.  Set the dimension to 0 only when full-resolution stills
# are explicitly wanted.
CAMERA_ID = os.environ.get("LSA_CAMERA_ID", "0")
CAMERA_MAX_DIMENSION = bounded_int("LSA_CAMERA_MAX_DIMENSION", 1280, 0, 3840)
CAMERA_CAPTURE_INTERVAL = bounded_float("LSA_CAMERA_CAPTURE_INTERVAL", 0.1, 0.0, 10.0)


class ProviderState:
    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.location_lock = threading.Lock()
        self.running = True
        self.camera_active = False
        self.location_active = False
        self.generation = 0
        self.frame: bytes | None = None
        self.frame_width = 0
        self.frame_height = 0
        self.frame_timestamp = 0.0
        self.frame_scaled = False
        self.last_camera_error = ""
        self.last_location: dict[str, object] | None = None
        self.last_location_at = 0.0

    def snapshot(self) -> dict[str, object]:
        with self.condition:
            return {
                "camera_active": self.camera_active,
                "location_active": self.location_active,
                "frame_generation": self.generation,
                "camera_endpoint": f"http://127.0.0.1:{CAMERA_PORT}/camera.mjpg",
                "snapshot_endpoint": f"http://127.0.0.1:{CAMERA_PORT}/snapshot.jpg",
                "frame_endpoint": f"http://127.0.0.1:{CAMERA_PORT}/frame.jpg",
                "frame_width": self.frame_width,
                "frame_height": self.frame_height,
                "frame_bytes": len(self.frame) if self.frame else 0,
                "frame_timestamp": self.frame_timestamp,
                "frame_scaled": self.frame_scaled,
                "camera_max_dimension": CAMERA_MAX_DIMENSION,
                "gpsd_endpoint": f"tcp://127.0.0.1:{GPSD_PORT}",
                "last_camera_error": self.last_camera_error,
            }

    def set_camera(self, active: bool) -> None:
        with self.condition:
            self.camera_active = active
            self.condition.notify_all()

    def set_location(self, active: bool) -> None:
        with self.condition:
            self.location_active = active
            self.condition.notify_all()

    def wait_for_frame(self, generation: int, timeout: float) -> tuple[int, bytes | None, int, int, float]:
        deadline = time.monotonic() + timeout
        with self.condition:
            while self.running and (self.frame is None or self.generation <= generation):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.condition.wait(remaining)
            return (
                self.generation,
                self.frame,
                self.frame_width,
                self.frame_height,
                self.frame_timestamp,
            )

    def publish_frame(self, payload: bytes, width: int, height: int, scaled: bool) -> None:
        staged = CAMERA_DIR / ".latest.jpg.tmp"
        latest = CAMERA_DIR / "latest.jpg"
        staged.write_bytes(payload)
        staged.replace(latest)
        with self.condition:
            self.frame = payload
            self.frame_width = width
            self.frame_height = height
            self.frame_timestamp = time.time()
            self.frame_scaled = scaled
            self.generation += 1
            self.last_camera_error = ""
            self.condition.notify_all()

    @staticmethod
    def jpeg_dimensions(payload: bytes) -> tuple[int, int] | None:
        if len(payload) < 10 or payload[:2] != b"\xff\xd8":
            return None
        offset = 2
        start_of_frame = {
            0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
            0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
        }
        while offset + 9 <= len(payload):
            if payload[offset] != 0xFF:
                offset += 1
                continue
            while offset < len(payload) and payload[offset] == 0xFF:
                offset += 1
            if offset >= len(payload):
                return None
            marker = payload[offset]
            offset += 1
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(payload):
                return None
            length = (payload[offset] << 8) | payload[offset + 1]
            if length < 2 or offset + length > len(payload):
                return None
            if marker in start_of_frame and length >= 8:
                height = (payload[offset + 3] << 8) | payload[offset + 4]
                width = (payload[offset + 5] << 8) | payload[offset + 6]
                return (width, height) if width and height else None
            offset += length
        return None

    def normalise_camera_frame(self, capture_path: Path) -> tuple[bytes, int, int, bool]:
        payload = capture_path.read_bytes()
        dimensions = self.jpeg_dimensions(payload)
        if not dimensions:
            raise RuntimeError("camera command returned a JPEG with no dimensions")
        width, height = dimensions
        if (
            not CAMERA_MAX_DIMENSION
            or max(width, height) <= CAMERA_MAX_DIMENSION
            or not FFMPEG_COMMAND.is_file()
        ):
            return payload, width, height, False

        scale = CAMERA_MAX_DIMENSION / max(width, height)
        target_width = max(2, int(width * scale) // 2 * 2)
        target_height = max(2, int(height * scale) // 2 * 2)
        scaled_path = capture_path.with_name(capture_path.stem + ".scaled.jpg")
        result = subprocess.run(
            [
                str(FFMPEG_COMMAND), "-y", "-loglevel", "error",
                "-i", str(capture_path), "-frames:v", "1",
                "-vf", f"scale={target_width}:{target_height}",
                "-q:v", "5", str(scaled_path),
            ],
            capture_output=True,
            text=True,
            timeout=25,
        )
        try:
            if result.returncode != 0 or not scaled_path.is_file():
                detail = (result.stderr or result.stdout or "ffmpeg scaling failed").strip()
                raise RuntimeError(f"camera scaling failed: {detail}")
            scaled = scaled_path.read_bytes()
            scaled_dimensions = self.jpeg_dimensions(scaled)
            if not scaled or not scaled_dimensions:
                raise RuntimeError("camera scaling produced an invalid JPEG")
            return scaled, scaled_dimensions[0], scaled_dimensions[1], True
        finally:
            scaled_path.unlink(missing_ok=True)

    def camera_worker(self) -> None:
        while self.running:
            with self.condition:
                while self.running and not self.camera_active:
                    self.condition.wait(1.0)
                if not self.running:
                    return
            capture_path = CAMERA_DIR / f".capture-{os.getpid()}.jpg"
            captured = False
            try:
                capture_path.unlink(missing_ok=True)
                command = [str(CAMERA_COMMAND)]
                if CAMERA_ID:
                    command.extend(["-c", CAMERA_ID])
                command.append(str(capture_path))
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=25,
                )
                if result.returncode != 0 or not capture_path.is_file():
                    detail = (result.stderr or result.stdout or "camera command failed").strip()
                    raise RuntimeError(detail)
                payload, width, height, scaled = self.normalise_camera_frame(capture_path)
                self.publish_frame(payload, width, height, scaled)
                captured = True
            except Exception as exc:  # The next interval may recover permission/device state.
                with self.condition:
                    self.last_camera_error = str(exc)
                    self.condition.notify_all()
            finally:
                capture_path.unlink(missing_ok=True)
            # A failed Android capture should not spin.  Successful captures
            # begin the next still request promptly; Camera2/MediaCodec can
            # replace this source later without changing Linux endpoints.
            time.sleep(CAMERA_CAPTURE_INTERVAL if captured else max(1.0, CAMERA_CAPTURE_INTERVAL))

    def location(self) -> dict[str, object] | None:
        if not self.location_active:
            return None
        with self.location_lock:
            if self.last_location and time.monotonic() - self.last_location_at < 1.0:
                return self.last_location
            try:
                result = subprocess.run(
                    [str(LOCATION_COMMAND), "-p", "gps", "-r", "once"],
                    capture_output=True,
                    text=True,
                    timeout=25,
                )
                if result.returncode != 0 or not result.stdout.strip():
                    return None
                value = json.loads(result.stdout)
                if not isinstance(value, dict):
                    return None
                self.last_location = value
                self.last_location_at = time.monotonic()
                return value
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
                return None


STATE_OBJECT = ProviderState()


def write_json_line(handle, value: dict[str, object]) -> None:
    handle.write((json.dumps(value, separators=(",", ":")) + "\n").encode("utf-8"))
    handle.flush()


def gpsd_tpv(location: dict[str, object] | None) -> dict[str, object]:
    if not location:
        return {"class": "TPV", "mode": 1}
    payload: dict[str, object] = {"class": "TPV", "mode": 3}
    mappings = {
        "latitude": "lat",
        "longitude": "lon",
        "altitude": "altHAE",
        "speed": "speed",
        "bearing": "track",
        "timestamp": "time",
    }
    for source, target in mappings.items():
        if source in location:
            payload[target] = location[source]
    if "lat" not in payload or "lon" not in payload:
        payload["mode"] = 1
    return payload


class CameraHandler(BaseHTTPRequestHandler):
    server_version = "LSAAndroidCamera/1"

    def log_message(self, *_args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        request = urlparse(self.path)
        if request.path == "/status":
            body = json.dumps(STATE_OBJECT.snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if request.path == "/snapshot.jpg":
            _generation, frame, _width, _height, _timestamp = STATE_OBJECT.wait_for_frame(-1, 3.0)
            if not frame:
                self.send_error(503, "camera provider has no frame")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.end_headers()
            self.wfile.write(frame)
            return
        if request.path == "/frame.jpg":
            try:
                after = int(parse_qs(request.query).get("after", ["-1"])[0])
            except ValueError:
                self.send_error(400, "after must be an integer")
                return
            generation, frame, width, height, timestamp = STATE_OBJECT.wait_for_frame(after, 12.0)
            if not frame or generation <= after:
                self.send_error(503, "camera provider has no newer frame")
                return
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(frame)))
            self.send_header("X-LSA-Camera-Generation", str(generation))
            self.send_header("X-LSA-Camera-Width", str(width))
            self.send_header("X-LSA-Camera-Height", str(height))
            self.send_header("X-LSA-Camera-Timestamp", f"{timestamp:.6f}")
            self.end_headers()
            self.wfile.write(frame)
            return
        if request.path != "/camera.mjpg":
            self.send_error(404)
            return
        boundary = b"lsa-camera"
        self.send_response(200)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=lsa-camera")
        self.end_headers()
        generation = -1
        try:
            while STATE_OBJECT.running:
                generation, frame, width, height, timestamp = STATE_OBJECT.wait_for_frame(generation, 15.0)
                if not frame:
                    continue
                self.wfile.write(b"--" + boundary + b"\r\n")
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii"))
                self.wfile.write(frame + b"\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return


class GPSDHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        write_json_line(self.wfile, {"class": "VERSION", "release": "LSA Android Location Provider", "proto_major": 3, "proto_minor": 14})
        watching = False
        while STATE_OBJECT.running:
            line = self.rfile.readline(4096)
            if not line:
                return
            command = line.decode("utf-8", "replace").strip()
            if command.startswith("?WATCH"):
                watching = '"enable":true' in command.replace(" ", "").lower()
                write_json_line(self.wfile, {"class": "WATCH", "enable": watching, "json": True})
            elif command.startswith("?POLL"):
                write_json_line(self.wfile, {"class": "POLL", "time": time.time(), "active": 0, "tpv": [gpsd_tpv(STATE_OBJECT.location())]})
            if watching:
                # A GPSD consumer must learn that this provider has no fix
                # when the Location backend is inactive.  Previously the
                # connection stayed open after WATCH but produced no TPV at
                # all.  Keep the watch alive so a later backend start wakes
                # the client through ProviderState.set_location().
                while STATE_OBJECT.running:
                    write_json_line(self.wfile, gpsd_tpv(STATE_OBJECT.location()))
                    with STATE_OBJECT.condition:
                        timeout = 1.0 if STATE_OBJECT.location_active else 5.0
                        STATE_OBJECT.condition.wait(timeout)


def read_secret() -> str:
    if not SECRET_FILE.exists():
        token = os.urandom(32).hex()
        SECRET_FILE.write_text(token + "\n", encoding="utf-8")
        os.chmod(SECRET_FILE, 0o644)
    return SECRET_FILE.read_text(encoding="utf-8").strip()


class ControlHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline(4096).decode("utf-8", "replace").strip()
        if not line:
            return
        parts = line.split()
        if len(parts) < 2 or parts[0] != self.server.secret:  # type: ignore[attr-defined]
            self.wfile.write(b"ERR authentication\n")
            return
        command = parts[1:]
        if command == ["status"]:
            response = "OK " + json.dumps(STATE_OBJECT.snapshot(), separators=(",", ":"))
        elif command == ["camera", "start"]:
            STATE_OBJECT.set_camera(True)
            response = "OK camera active"
        elif command == ["camera", "stop"]:
            STATE_OBJECT.set_camera(False)
            response = "OK camera stopped"
        elif command == ["camera", "status"]:
            response = "OK " + json.dumps(STATE_OBJECT.snapshot(), separators=(",", ":"))
        elif command == ["location", "start"]:
            STATE_OBJECT.set_location(True)
            response = "OK location active"
        elif command == ["location", "stop"]:
            STATE_OBJECT.set_location(False)
            response = "OK location stopped"
        elif command == ["location", "status"]:
            response = "OK " + json.dumps(STATE_OBJECT.snapshot(), separators=(",", ":"))
        else:
            response = "ERR unknown command"
        self.wfile.write((response + "\n").encode("utf-8"))


class ThreadingTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(server) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def main() -> None:
    CAMERA_DIR.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    secret = read_secret()
    camera = ThreadingHTTPServer(("127.0.0.1", CAMERA_PORT), CameraHandler)
    gpsd = ThreadingTCPServer(("127.0.0.1", GPSD_PORT), GPSDHandler)
    control = ThreadingTCPServer(("127.0.0.1", CONTROL_PORT), ControlHandler)
    control.secret = secret  # type: ignore[attr-defined]
    servers = (camera, gpsd, control)
    for server in servers:
        serve(server)
    threading.Thread(target=STATE_OBJECT.camera_worker, daemon=True).start()

    def stop(_signum, _frame) -> None:
        STATE_OBJECT.running = False
        with STATE_OBJECT.condition:
            STATE_OBJECT.condition.notify_all()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"Android capture provider ready: camera={CAMERA_PORT} control={CONTROL_PORT} gpsd={GPSD_PORT}", flush=True)
    while STATE_OBJECT.running:
        time.sleep(0.25)
    for server in servers:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
