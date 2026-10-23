"""Durable Android AAudio output listener for Linux-side raw PCM."""

try:
    # audioop was removed from CPython 3.13.  Termux now ships a newer
    # interpreter, so keep using it when an older interpreter provides it,
    # but never make the Android playback service depend on it.
    import audioop
except ModuleNotFoundError:
    audioop = None
import ctypes as C
import os
import socket
import subprocess
import threading
import time
import wave

from .config import AUDIO_PORT, DEFAULT_SINK_SPEC
from .logging import log


HOST = "127.0.0.1"
AAUDIO_DIRECTION_OUTPUT = 0
AAUDIO_FORMAT_PCM_I16 = 1
WRITE_TIMEOUT_NS = 250_000_000

sink_lock = threading.Lock()
sink_thread = None
sink_listener = None
sink_stop_event = threading.Event()
active_conn = None

TERMUX_PREFIX = "/data/data/com.termux/files/usr"
TERMUX_BIN = os.path.join(TERMUX_PREFIX, "bin")
PROVIDER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FALLBACK_STATE = os.path.join(PROVIDER_DIR, "state", "fallback-audio")
TERMUX_PULSE_RUNTIME = os.path.join(FALLBACK_STATE, "pulse-runtime")
TERMUX_PULSE_SOCKET = os.path.join(TERMUX_PULSE_RUNTIME, "native")
TERMUX_SLES_SINK = "LSAOpenSLESSink"


def normalise_spec(requested: dict | None = None) -> dict:
    spec = dict(DEFAULT_SINK_SPEC)
    if requested:
        spec.update(requested)

    audio_format = str(spec.get("format", "")).lower()
    if audio_format != "s16le":
        raise ValueError("unsupported_format")

    rate = int(spec.get("rate", 0))
    channels = int(spec.get("channels", 0))
    if not 8000 <= rate <= 192000:
        raise ValueError("invalid_rate")
    if not 1 <= channels <= 8:
        raise ValueError("invalid_channels")

    return {"format": audio_format, "rate": rate, "channels": channels}


def _ratecv_s16le(payload, channels, input_rate, output_rate, state):
    """Convert interleaved s16le between rates without splitting frames.

    Older interpreters retain audioop's higher-quality converter.  On current
    Termux Python, a small streaming nearest-frame converter keeps the sink
    operational and maintains channel alignment if AAudio negotiates a rate
    different from the Linux client.
    """
    if audioop is not None:
        return audioop.ratecv(
            payload, 2, channels, input_rate, output_rate, state
        )

    if input_rate == output_rate:
        return payload, state

    frame_bytes = channels * 2
    accumulator = state.get("accumulator", 0) if state else 0
    converted = bytearray()
    for offset in range(0, len(payload), frame_bytes):
        accumulator += output_rate
        while accumulator >= input_rate:
            converted.extend(payload[offset:offset + frame_bytes])
            accumulator -= input_rate
    return bytes(converted), {"accumulator": accumulator}


def _load_aaudio():
    lib = C.CDLL("libaaudio.so")
    c_void_p = C.c_void_p
    c_i32 = C.c_int32
    c_i64 = C.c_int64

    lib.AAudio_createStreamBuilder.argtypes = [C.POINTER(c_void_p)]
    lib.AAudio_createStreamBuilder.restype = c_i32
    lib.AAudioStreamBuilder_setDirection.argtypes = [c_void_p, c_i32]
    lib.AAudioStreamBuilder_setFormat.argtypes = [c_void_p, c_i32]
    lib.AAudioStreamBuilder_setSampleRate.argtypes = [c_void_p, c_i32]
    lib.AAudioStreamBuilder_setChannelCount.argtypes = [c_void_p, c_i32]
    lib.AAudioStreamBuilder_openStream.argtypes = [c_void_p, C.POINTER(c_void_p)]
    lib.AAudioStreamBuilder_openStream.restype = c_i32
    lib.AAudioStreamBuilder_delete.argtypes = [c_void_p]
    lib.AAudioStreamBuilder_delete.restype = c_i32
    lib.AAudioStream_getSampleRate.argtypes = [c_void_p]
    lib.AAudioStream_getSampleRate.restype = c_i32
    lib.AAudioStream_getChannelCount.argtypes = [c_void_p]
    lib.AAudioStream_getChannelCount.restype = c_i32
    lib.AAudioStream_getFormat.argtypes = [c_void_p]
    lib.AAudioStream_getFormat.restype = c_i32
    lib.AAudioStream_requestStart.argtypes = [c_void_p]
    lib.AAudioStream_requestStart.restype = c_i32
    lib.AAudioStream_write.argtypes = [c_void_p, c_void_p, c_i32, c_i64]
    lib.AAudioStream_write.restype = c_i32
    lib.AAudioStream_requestStop.argtypes = [c_void_p]
    lib.AAudioStream_requestStop.restype = c_i32
    lib.AAudioStream_close.argtypes = [c_void_p]
    lib.AAudioStream_close.restype = c_i32

    if hasattr(lib, "AAudio_convertResultToText"):
        lib.AAudio_convertResultToText.argtypes = [c_i32]
        lib.AAudio_convertResultToText.restype = C.c_char_p

    return lib


def _error_name(lib, code):
    try:
        result = lib.AAudio_convertResultToText(code)
        if result:
            return result.decode(errors="replace")
    except Exception:
        pass
    return str(code)


def _check(lib, operation, result):
    if result < 0:
        raise RuntimeError(f"{operation}: {result} ({_error_name(lib, result)})")
    return result


def _open_output(spec):
    lib = _load_aaudio()
    builder = C.c_void_p()
    stream = C.c_void_p()
    _check(lib, "create builder", lib.AAudio_createStreamBuilder(C.byref(builder)))
    try:
        lib.AAudioStreamBuilder_setDirection(builder, AAUDIO_DIRECTION_OUTPUT)
        lib.AAudioStreamBuilder_setFormat(builder, AAUDIO_FORMAT_PCM_I16)
        lib.AAudioStreamBuilder_setSampleRate(builder, spec["rate"])
        lib.AAudioStreamBuilder_setChannelCount(builder, spec["channels"])
        _check(lib, "open output", lib.AAudioStreamBuilder_openStream(builder, C.byref(stream)))
    finally:
        lib.AAudioStreamBuilder_delete(builder)

    actual = {
        "format": lib.AAudioStream_getFormat(stream),
        "rate": lib.AAudioStream_getSampleRate(stream),
        "channels": lib.AAudioStream_getChannelCount(stream),
    }
    if actual["format"] != AAUDIO_FORMAT_PCM_I16:
        lib.AAudioStream_close(stream)
        raise RuntimeError(f"unexpected output format {actual['format']}")
    if actual["channels"] != spec["channels"]:
        lib.AAudioStream_close(stream)
        raise RuntimeError(
            f"output channel mismatch requested={spec['channels']} actual={actual['channels']}"
        )
    if actual["rate"] <= 0:
        lib.AAudioStream_close(stream)
        raise RuntimeError(f"invalid output rate {actual['rate']}")

    return lib, stream, actual


def _write_pcm(lib, stream, data, channels):
    frame_bytes = channels * 2
    offset = 0
    while offset < len(data) and not sink_stop_event.is_set():
        frames = min((len(data) - offset) // frame_bytes, 4096)
        if frames <= 0:
            return
        size = frames * frame_bytes
        payload = C.create_string_buffer(data[offset:offset + size])
        written = _check(
            lib,
            "write output",
            lib.AAudioStream_write(stream, C.cast(payload, C.c_void_p), frames, WRITE_TIMEOUT_NS),
        )
        if written == 0:
            continue
        offset += written * frame_bytes


def _play_client_aaudio(conn: socket.socket, requested):
    lib, stream, actual = _open_output(requested)
    conversion_state = None
    pending = b""
    input_frame_bytes = requested["channels"] * 2
    try:
        _check(lib, "start output", lib.AAudioStream_requestStart(stream))
        log(
            "SINK client connected backend=AAudio "
            f"requested={requested['format']} {requested['channels']}ch {requested['rate']}Hz "
            f"actual=s16le {actual['channels']}ch {actual['rate']}Hz"
        )
        if actual["rate"] != requested["rate"] and audioop is None:
            log("SINK resampler=internal-nearest (audioop unavailable)")
        while not sink_stop_event.is_set():
            data = conn.recv(65536)
            if not data:
                break
            pending += data
            whole = (len(pending) // input_frame_bytes) * input_frame_bytes
            if not whole:
                continue
            payload, pending = pending[:whole], pending[whole:]
            if actual["rate"] != requested["rate"]:
                payload, conversion_state = _ratecv_s16le(
                    payload,
                    requested["channels"],
                    requested["rate"],
                    actual["rate"],
                    conversion_state,
                )
            _write_pcm(lib, stream, payload, actual["channels"])
    finally:
        try:
            lib.AAudioStream_requestStop(stream)
        except Exception:
            pass
        try:
            lib.AAudioStream_close(stream)
        except Exception:
            pass


def _termux_pulse_env():
    return {
        **os.environ,
        "HOME": PROVIDER_DIR,
        "XDG_RUNTIME_DIR": TERMUX_PULSE_RUNTIME,
        "PULSE_SERVER": f"unix:{TERMUX_PULSE_SOCKET}",
    }


def _run_termux_pulse(*args, timeout=5):
    return subprocess.run(
        [os.path.join(TERMUX_BIN, "pactl"), *args],
        env=_termux_pulse_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def _ensure_opensles_sink():
    """Start an isolated Termux PulseAudio server backed by OpenSL ES."""
    os.makedirs(TERMUX_PULSE_RUNTIME, exist_ok=True)
    os.chmod(TERMUX_PULSE_RUNTIME, 0o700)

    try:
        if _run_termux_pulse("info").returncode == 0:
            sinks = _run_termux_pulse("list", "short", "sinks")
            if any(line.split("\t")[1:2] == [TERMUX_SLES_SINK] for line in sinks.stdout.splitlines()):
                return
    except (OSError, subprocess.SubprocessError):
        pass

    pulseaudio = os.path.join(TERMUX_BIN, "pulseaudio")
    command = [
        pulseaudio,
        "--daemonize=yes",
        "--exit-idle-time=-1",
        "--disable-shm=yes",
        "--log-target=stderr",
        "--load=module-native-protocol-unix auth-anonymous=1",
        f"--load=module-sles-sink sink_name={TERMUX_SLES_SINK}",
    ]
    result = subprocess.run(
        command,
        env=_termux_pulse_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
    )
    if result.returncode:
        raise RuntimeError(f"cannot start Termux OpenSL PulseAudio: {result.stdout.strip()}")

    for _ in range(30):
        try:
            sinks = _run_termux_pulse("list", "short", "sinks")
            if sinks.returncode == 0 and any(
                line.split("\t")[1:2] == [TERMUX_SLES_SINK]
                for line in sinks.stdout.splitlines()
            ):
                return
        except (OSError, subprocess.SubprocessError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Termux OpenSL PulseAudio sink did not become ready")


def _stream_subprocess(conn: socket.socket, requested, command, backend):
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        log(
            f"SINK client connected backend={backend} "
            f"requested={requested['format']} {requested['channels']}ch {requested['rate']}Hz"
        )
        while not sink_stop_event.is_set():
            data = conn.recv(65536)
            if not data:
                break
            process.stdin.write(data)
            process.stdin.flush()
    finally:
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()


def _play_opensles(conn: socket.socket, requested, backend):
    _ensure_opensles_sink()
    command = [
        os.path.join(TERMUX_BIN, "pacat"),
        f"--server=unix:{TERMUX_PULSE_SOCKET}",
        "--playback",
        f"--device={TERMUX_SLES_SINK}",
        "--raw",
        "--format=s16le",
        f"--rate={requested['rate']}",
        f"--channels={requested['channels']}",
    ]
    _stream_subprocess(conn, requested, command, backend)


def _play_sox(conn: socket.socket, requested):
    command = [
        os.path.join(TERMUX_BIN, "play"),
        "-q", "-t", "raw", "-e", "signed-integer", "-b", "16",
        "-c", str(requested["channels"]), "-r", str(requested["rate"]), "-L", "-",
    ]
    _stream_subprocess(conn, requested, command, "SoX")


def _play_termux_api(conn: socket.socket, requested):
    """Tier-Z buffered fallback for devices without a native streaming sink."""
    os.makedirs(FALLBACK_STATE, exist_ok=True)
    path = os.path.join(FALLBACK_STATE, "termux-api-output.wav")
    total = 0
    with wave.open(path, "wb") as output:
        output.setnchannels(requested["channels"])
        output.setsampwidth(2)
        output.setframerate(requested["rate"])
        while not sink_stop_event.is_set():
            data = conn.recv(65536)
            if not data:
                break
            output.writeframesraw(data)
            total += len(data)
    if total:
        result = subprocess.run(
            [os.path.join(TERMUX_BIN, "termux-media-player"), "play", path],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
        )
        if result.returncode:
            raise RuntimeError(f"Termux:API playback failed: {result.stdout.strip()}")
    log(f"SINK client disconnected backend=TermuxAPI buffered_bytes={total}")


def _play_client(conn: socket.socket, requested, backend):
    if backend == "aaudio":
        return _play_client_aaudio(conn, requested)
    if backend in {"opensles", "pulse-proxy"}:
        return _play_opensles(conn, requested, backend)
    if backend == "sox":
        return _play_sox(conn, requested)
    if backend == "termux-api":
        return _play_termux_api(conn, requested)
    raise RuntimeError(f"unsupported backend {backend}")


def _serve_sink(listener: socket.socket, spec, backend):
    global active_conn
    log(f"SINK listening backend=AAudio on {HOST}:{AUDIO_PORT}")
    try:
        while not sink_stop_event.is_set():
            try:
                conn, _addr = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            active_conn = conn
            try:
                with conn:
                    _play_client(conn, spec, backend)
            except Exception as exc:
                log(f"SINK client ERR {type(exc).__name__}: {exc}")
            finally:
                active_conn = None
                log("SINK client disconnected")
    finally:
        try:
            listener.close()
        except Exception:
            pass
        log("SINK listener exited")


def start_sink(requested: dict | None = None, backend: str = "aaudio") -> str:
    global sink_thread, sink_listener
    with sink_lock:
        if sink_thread is not None and sink_thread.is_alive():
            return "ERR sink_running"
        try:
            spec = normalise_spec(requested)
        except (TypeError, ValueError) as exc:
            return f"ERR {exc}"
        if backend not in {"aaudio", "opensles", "sox", "pulse-proxy", "termux-api"}:
            return "ERR unsupported_backend"

        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((HOST, AUDIO_PORT))
            listener.listen(1)
            listener.settimeout(0.5)
        except OSError as exc:
            listener.close()
            log(f"SINK bind ERR {type(exc).__name__}: {exc}")
            return "ERR bind_failed"

        sink_stop_event.clear()
        sink_listener = listener
        sink_thread = threading.Thread(
            target=_serve_sink,
            args=(listener, spec, backend),
            name="AndroidAudio-sink",
            daemon=True,
        )
        sink_thread.start()
        log(
            f"SINK started backend={backend} format={spec['format']} "
            f"rate={spec['rate']} channels={spec['channels']}"
        )
        return (
            f"OK format={spec['format']} "
            f"rate={spec['rate']} channels={spec['channels']}"
        )


def stop_sink() -> str:
    global sink_thread, sink_listener, active_conn
    with sink_lock:
        if sink_thread is None:
            return "ERR sink_not_running"
        sink_stop_event.set()
        if active_conn is not None:
            try:
                active_conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if sink_listener is not None:
            try:
                sink_listener.close()
            except OSError:
                pass
        if sink_thread.is_alive():
            sink_thread.join(timeout=3)
        sink_thread = None
        sink_listener = None
        active_conn = None
        log("SINK stopped")
        return "OK"
