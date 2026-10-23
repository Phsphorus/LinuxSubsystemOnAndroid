import ctypes as C
import os
import re
import socket
import subprocess
import threading

from .config import TERMUX_BIN, SOURCE_PORT
from .logging import log


HOST = "127.0.0.1"

source_lock = threading.Lock()
source_thread = None
source_listener = None
source_stop_event = threading.Event()

# OpenSL fallback process.
active_proc = None

# Current client, used to unblock a stopped source cleanly.
active_conn = None


# =========================================================
# Common
# =========================================================

def _android_sdk() -> int:
    try:
        out = subprocess.check_output(
            ["/system/bin/getprop", "ro.build.version.sdk"],
            text=True,
            timeout=2,
        ).strip()
        return int(out)
    except Exception:
        return 0


def _channel_map(channels: int) -> str:
    if channels == 1:
        return "mono"

    if channels == 2:
        return "front-left,front-right"

    # Let Pulse choose a map for uncommon layouts.
    return "-"


def _send_header(conn: socket.socket, spec):
    header = (
        f"LSAUDIO1 "
        f"format={spec['format']} "
        f"rate={spec['rate']} "
        f"channels={spec['channels']} "
        f"map={spec['channel_map']}\n"
    )

    conn.sendall(header.encode("ascii"))


# =========================================================
# AAudio backend
# Android API 26+
# =========================================================

AAUDIO_DIRECTION_INPUT = 1
AAUDIO_FORMAT_PCM_I16 = 1


def _load_aaudio():
    lib = C.CDLL("libaaudio.so")

    c_void_p = C.c_void_p
    c_i32 = C.c_int32
    c_i64 = C.c_int64

    lib.AAudio_createStreamBuilder.argtypes = [
        C.POINTER(c_void_p)
    ]
    lib.AAudio_createStreamBuilder.restype = c_i32

    lib.AAudioStreamBuilder_setDirection.argtypes = [
        c_void_p,
        c_i32,
    ]

    lib.AAudioStreamBuilder_setFormat.argtypes = [
        c_void_p,
        c_i32,
    ]

    lib.AAudioStreamBuilder_openStream.argtypes = [
        c_void_p,
        C.POINTER(c_void_p),
    ]
    lib.AAudioStreamBuilder_openStream.restype = c_i32

    lib.AAudioStreamBuilder_delete.argtypes = [
        c_void_p
    ]
    lib.AAudioStreamBuilder_delete.restype = c_i32

    lib.AAudioStream_getSampleRate.argtypes = [
        c_void_p
    ]
    lib.AAudioStream_getSampleRate.restype = c_i32

    lib.AAudioStream_getChannelCount.argtypes = [
        c_void_p
    ]
    lib.AAudioStream_getChannelCount.restype = c_i32

    lib.AAudioStream_getFormat.argtypes = [
        c_void_p
    ]
    lib.AAudioStream_getFormat.restype = c_i32

    lib.AAudioStream_getFramesPerBurst.argtypes = [
        c_void_p
    ]
    lib.AAudioStream_getFramesPerBurst.restype = c_i32

    lib.AAudioStream_requestStart.argtypes = [
        c_void_p
    ]
    lib.AAudioStream_requestStart.restype = c_i32

    lib.AAudioStream_read.argtypes = [
        c_void_p,
        c_void_p,
        c_i32,
        c_i64,
    ]
    lib.AAudioStream_read.restype = c_i32

    lib.AAudioStream_requestStop.argtypes = [
        c_void_p
    ]
    lib.AAudioStream_requestStop.restype = c_i32

    lib.AAudioStream_close.argtypes = [
        c_void_p
    ]
    lib.AAudioStream_close.restype = c_i32

    if hasattr(lib, "AAudio_convertResultToText"):
        lib.AAudio_convertResultToText.argtypes = [c_i32]
        lib.AAudio_convertResultToText.restype = C.c_char_p

    if hasattr(lib, "AAudioStreamBuilder_setPackageName"):
        lib.AAudioStreamBuilder_setPackageName.argtypes = [
            c_void_p,
            C.c_char_p,
        ]

    return lib


def _aaudio_error(lib, code):
    try:
        if hasattr(lib, "AAudio_convertResultToText"):
            result = lib.AAudio_convertResultToText(code)

            if result:
                return result.decode(errors="replace")

    except Exception:
        pass

    return str(code)


def _aaudio_check(lib, operation, result):
    if result < 0:
        raise RuntimeError(
            f"{operation}: {result} "
            f"({_aaudio_error(lib, result)})"
        )

    return result


def _open_aaudio():
    lib = _load_aaudio()

    builder = C.c_void_p()
    stream = C.c_void_p()

    _aaudio_check(
        lib,
        "create builder",
        lib.AAudio_createStreamBuilder(C.byref(builder)),
    )

    try:
        lib.AAudioStreamBuilder_setDirection(
            builder,
            AAUDIO_DIRECTION_INPUT,
        )

        # Request signed 16-bit PCM but deliberately leave rate and
        # channel count unspecified. Android chooses its native values.
        lib.AAudioStreamBuilder_setFormat(
            builder,
            AAUDIO_FORMAT_PCM_I16,
        )

        # Android 12+ attribution. com.termux.api shares the Termux UID
        # and owns the microphone permission used by this bridge.
        if (
            _android_sdk() >= 31
            and hasattr(
                lib,
                "AAudioStreamBuilder_setPackageName",
            )
        ):
            lib.AAudioStreamBuilder_setPackageName(
                builder,
                b"com.termux.api",
            )

        _aaudio_check(
            lib,
            "open stream",
            lib.AAudioStreamBuilder_openStream(
                builder,
                C.byref(stream),
            ),
        )

    finally:
        try:
            lib.AAudioStreamBuilder_delete(builder)
        except Exception:
            pass

    rate = lib.AAudioStream_getSampleRate(stream)
    channels = lib.AAudioStream_getChannelCount(stream)
    audio_format = lib.AAudioStream_getFormat(stream)
    burst = lib.AAudioStream_getFramesPerBurst(stream)

    if audio_format != AAUDIO_FORMAT_PCM_I16:
        try:
            lib.AAudioStream_close(stream)
        except Exception:
            pass

        raise RuntimeError(
            f"unexpected AAudio format {audio_format}"
        )

    if rate <= 0 or channels <= 0:
        try:
            lib.AAudioStream_close(stream)
        except Exception:
            pass

        raise RuntimeError(
            f"invalid AAudio spec "
            f"rate={rate} channels={channels}"
        )

    spec = {
        "name": "AAudio",
        "format": "s16le",
        "channels": channels,
        "rate": rate,
        "channel_map": _channel_map(channels),
        "burst": burst,
    }

    return lib, stream, spec


def _capture_aaudio(conn: socket.socket):
    lib, stream, spec = _open_aaudio()

    _send_header(conn, spec)

    log(
        "SOURCE client connected "
        f"backend=AAudio "
        f"{spec['format']} "
        f"{spec['channels']}ch "
        f"{spec['rate']}Hz "
        f"burst={spec['burst']} "
        f"map={spec['channel_map']}"
    )

    burst = spec["burst"]

    if burst <= 0:
        burst = 192

    chunk_frames = max(192, burst * 2)

    frame_bytes = spec["channels"] * 2
    buf = C.create_string_buffer(
        chunk_frames * frame_bytes
    )

    try:
        _aaudio_check(
            lib,
            "start stream",
            lib.AAudioStream_requestStart(stream),
        )

        while not source_stop_event.is_set():
            got = lib.AAudioStream_read(
                stream,
                buf,
                chunk_frames,

                # 250 ms prevents stop/restart from getting stuck
                # behind a permanently blocking read.
                250_000_000,
            )

            if got < 0:
                raise RuntimeError(
                    f"AAudio read: {got} "
                    f"({_aaudio_error(lib, got)})"
                )

            if got == 0:
                continue

            size = got * frame_bytes
            conn.sendall(buf.raw[:size])

    finally:
        try:
            lib.AAudioStream_requestStop(stream)
        except Exception:
            pass

        try:
            lib.AAudioStream_close(stream)
        except Exception:
            pass


# =========================================================
# OpenSL ES fallback
# Used for Android versions without AAudio or devices where
# AAudio cannot be opened.
# =========================================================

def _pactl(*args):
    pactl = os.path.join(TERMUX_BIN, "pactl")

    return subprocess.run(
        [pactl, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=5,
    )


def _ensure_sles_source() -> bool:
    try:
        result = _pactl(
            "list",
            "short",
            "sources",
        )

        if "module-sles-source.c" in result.stdout:
            return True

        result = _pactl(
            "load-module",
            "module-sles-source",
        )

        log(
            "SOURCE fallback load module-sles-source: "
            f"{result.stdout.strip()}"
        )

        if result.returncode != 0:
            return False

        result = _pactl(
            "list",
            "short",
            "sources",
        )

        return "module-sles-source.c" in result.stdout

    except Exception as e:
        log(f"SOURCE OpenSL fallback setup ERR {e}")
        return False


def _discover_sles_source():
    result = _pactl(
        "list",
        "short",
        "sources",
    )

    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip())

    source_name = None
    sample_spec = None

    for line in result.stdout.splitlines():
        fields = line.split("\t")

        if len(fields) < 4:
            continue

        name = fields[1].strip()
        driver = fields[2].strip()

        if driver == "module-sles-source.c":
            source_name = name
            sample_spec = fields[3].strip()
            break

    if not source_name or not sample_spec:
        raise RuntimeError(
            "OpenSL ES source not found"
        )

    match = re.match(
        r"^(\S+)\s+(\d+)ch\s+(\d+)Hz$",
        sample_spec,
    )

    if not match:
        raise RuntimeError(
            "cannot parse OpenSL source specification: "
            f"{sample_spec!r}"
        )

    audio_format = match.group(1)
    channels = int(match.group(2))
    rate = int(match.group(3))

    return {
        "name": source_name,
        "format": audio_format,
        "channels": channels,
        "rate": rate,
        "channel_map": _channel_map(channels),
    }


def _capture_sles(conn: socket.socket):
    global active_proc

    if not _ensure_sles_source():
        raise RuntimeError(
            "OpenSL fallback unavailable"
        )

    spec = _discover_sles_source()

    _send_header(conn, spec)

    log(
        "SOURCE client connected "
        f"backend=OpenSL-fallback "
        f"{spec['name']} "
        f"{spec['format']} "
        f"{spec['channels']}ch "
        f"{spec['rate']}Hz "
        f"map={spec['channel_map']}"
    )

    parecord = os.path.join(
        TERMUX_BIN,
        "parecord",
    )

    proc = subprocess.Popen(
        [
            parecord,
            f"--device={spec['name']}",
            "--raw",
            f"--format={spec['format']}",
            f"--rate={spec['rate']}",
            f"--channels={spec['channels']}",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    active_proc = proc

    try:
        while not source_stop_event.is_set():
            data = proc.stdout.read(65536)

            if not data:
                break

            conn.sendall(data)

    finally:
        try:
            proc.terminate()
        except Exception:
            pass

        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

        active_proc = None


# =========================================================
# Client/session selection
# =========================================================

def _capture_client(conn: socket.socket):
    sdk = _android_sdk()

    # Preferred backend.
    if sdk >= 26:
        try:
            _capture_aaudio(conn)
            return

        except (
            BrokenPipeError,
            ConnectionResetError,
        ):
            return

        except Exception as e:
            log(
                "SOURCE AAudio ERR "
                f"{e}; trying OpenSL fallback"
            )

            # If AAudio already sent its stream header, the connection
            # may no longer be reusable safely. The normal Debian source
            # loop reconnects automatically, so close this session.
            return

    # Android 7 / pre-AAudio compatibility path.
    try:
        _capture_sles(conn)

    except (
        BrokenPipeError,
        ConnectionResetError,
        OSError,
    ):
        pass


# =========================================================
# Listener lifecycle
# =========================================================

def _serve_loop(listener: socket.socket):
    global active_conn

    log(
        f"SOURCE listening on "
        f"{HOST}:{SOURCE_PORT}"
    )

    while not source_stop_event.is_set():
        try:
            conn, _addr = listener.accept()

        except socket.timeout:
            continue

        except OSError:
            break

        active_conn = conn

        try:
            with conn:
                _capture_client(conn)

        except Exception as e:
            log(f"SOURCE client ERR {e}")

        finally:
            active_conn = None
            log("SOURCE client disconnected")

    log("SOURCE listener exited")


def start_source() -> str:
    global source_thread
    global source_listener

    with source_lock:
        if (
            source_thread is not None
            and source_thread.is_alive()
        ):
            return "ERR source_running"

        source_stop_event.clear()

        listener = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        listener.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )

        try:
            listener.bind(
                (HOST, SOURCE_PORT)
            )

            listener.listen(1)
            listener.settimeout(0.5)

        except Exception as e:
            try:
                listener.close()
            except Exception:
                pass

            log(f"SOURCE bind ERR {e}")
            return "ERR bind_failed"

        source_listener = listener

        source_thread = threading.Thread(
            target=_serve_loop,
            args=(listener,),
            name="AndroidAudio-source",
            daemon=True,
        )

        source_thread.start()

        sdk = _android_sdk()

        if sdk >= 26:
            log(
                "SOURCE started "
                "preferred_backend=AAudio"
            )
        else:
            log(
                "SOURCE started "
                "preferred_backend=OpenSL-fallback"
            )

        return "OK"


def stop_source() -> str:
    global source_thread
    global source_listener
    global active_proc
    global active_conn

    with source_lock:
        source_stop_event.set()

        conn = active_conn

        if conn is not None:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass

        proc = active_proc

        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

        listener = source_listener
        source_listener = None

        if listener is not None:
            try:
                listener.close()
            except Exception:
                pass

        thread = source_thread

        if (
            thread is not None
            and thread.is_alive()
        ):
            thread.join(timeout=2)

        source_thread = None
        active_proc = None
        active_conn = None

        log("SOURCE stopped")

        return "OK"


def status_source() -> str:
    thread = source_thread

    if (
        thread is not None
        and thread.is_alive()
    ):
        return "RUNNING"

    return "STOPPED"
