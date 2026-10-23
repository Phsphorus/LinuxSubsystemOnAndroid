import re
import socket
import os
import fcntl
import time
import subprocess

from .config import SOURCE_HOST, SOURCE_PORT, SOURCE_FIFO, SOURCE_NAME, SINK_MONITOR
from .logging import info
from .pulse import configure_echo_cancel, ensure_android_source


HEADER_PREFIX = "LSAUDIO1 "
HEADER_MAX = 1024


def parse_header(line: bytes):
    if len(line) > HEADER_MAX:
        raise ValueError("header_too_large")

    text = line.decode("ascii", "strict").strip()

    if not text.startswith(HEADER_PREFIX):
        raise ValueError(f"bad_header {text!r}")

    fields = {}

    for item in text[len(HEADER_PREFIX):].split():
        if "=" not in item:
            raise ValueError(f"bad_field {item!r}")

        key, value = item.split("=", 1)
        fields[key] = value

    for required in ("format", "rate", "channels", "map"):
        if required not in fields:
            raise ValueError(f"missing_{required}")

    fmt = fields["format"]

    if not re.fullmatch(r"[A-Za-z0-9_-]+", fmt):
        raise ValueError("bad_format")

    rate = int(fields["rate"])
    channels = int(fields["channels"])

    if not 1000 <= rate <= 768000:
        raise ValueError("bad_rate")

    if not 1 <= channels <= 32:
        raise ValueError("bad_channels")

    channel_map = fields["map"]

    if channel_map != "-" and not re.fullmatch(
        r"[A-Za-z0-9_,.-]+",
        channel_map,
    ):
        raise ValueError("bad_channel_map")

    return {
        "format": fmt,
        "rate": rate,
        "channels": channels,
        "map": channel_map,
    }


def repin_output_capture():
    result = subprocess.run(
        ["pactl", "list", "source-outputs"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    current_index = None
    is_halaudio = False

    for line in result.stdout.splitlines():
        stripped = line.strip()

        if stripped.startswith("Source Output #"):
            if current_index is not None and is_halaudio:
                subprocess.run(
                    ["pactl", "move-source-output", current_index, SINK_MONITOR],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

            current_index = stripped.split("#", 1)[1]
            is_halaudio = False
            continue

        if stripped == 'application.name = "LSA-HALAudio-OutputCapture"':
            is_halaudio = True

    if current_index is not None and is_halaudio:
        subprocess.run(
            ["pactl", "move-source-output", current_index, SINK_MONITOR],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    info(f"re-pinned HALAudio output capture to {SINK_MONITOR}")


_source_running_cached = False
_source_running_check_at = 0.0


def _android_source_running():
    """Return whether a Linux application is actively consuming AndroidSource."""
    global _source_running_cached, _source_running_check_at

    now = time.monotonic()

    # Avoid spawning pactl for every tiny PCM packet.
    if now < _source_running_check_at:
        return _source_running_cached

    _source_running_check_at = now + 0.10

    try:
        result = subprocess.run(
            ["pactl", "list", "short", "sources"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1,
        )

        running = False

        for line in result.stdout.splitlines():
            fields = line.split("\t")

            if len(fields) >= 5 and fields[1].strip() == SOURCE_NAME:
                running = fields[4].strip().upper() == "RUNNING"
                break

        _source_running_cached = running
        return running

    except Exception:
        # Safer to drop PCM than accumulate stale microphone history.
        _source_running_cached = False
        return False


def source_stream_loop():
    while True:
        sock = None
        stream = None

        try:
            info(
                f"mic connecting to "
                f"{SOURCE_HOST}:{SOURCE_PORT}"
            )

            sock = socket.create_connection(
                (SOURCE_HOST, SOURCE_PORT),
                timeout=5.0,
            )

            sock.settimeout(None)

            # Use one buffered file object for BOTH the header and PCM.
            # If readline() prefetches audio bytes, they remain available
            # through this same object instead of being lost.
            stream = sock.makefile("rb")

            header = stream.readline(HEADER_MAX + 1)

            if not header.endswith(b"\n"):
                raise ValueError("unterminated_header")

            spec = parse_header(header)

            info(
                "mic negotiated "
                f"format={spec['format']} "
                f"rate={spec['rate']} "
                f"channels={spec['channels']} "
                f"map={spec['map']}"
            )

            if not ensure_android_source(spec):
                raise RuntimeError("cannot_create_AndroidSource")

            configure_echo_cancel()

            # AndroidSource becoming the default source may cause PulseAudio
            # to move existing recording streams. Restore HALAudio's output
            # capture to the AndroidSink monitor after that transition.
            repin_output_capture()

            info(f"mic streaming into {SOURCE_FIFO}")

            # module-pipe-source owns the read side of this FIFO.
            # Opening here waits until PulseAudio is ready to consume it.
            with open(SOURCE_FIFO, "wb", buffering=0) as fifo:
                flags = fcntl.fcntl(fifo.fileno(), fcntl.F_GETFL)
                fcntl.fcntl(
                    fifo.fileno(),
                    fcntl.F_SETFL,
                    flags | os.O_NONBLOCK,
                )
                while True:
                    data = stream.read1(8192)

                    if not data:
                        raise ConnectionError("mic_stream_eof")

                    # Keep draining Android/AAudio continuously, but only
                    # deliver PCM while a Linux application is actually
                    # consuming AndroidSource. This prevents stale audio
                    # from accumulating while the Pulse source is suspended.
                    if not _android_source_running():
                        continue

                    try:
                        fifo.write(data)
                    except BlockingIOError:
                        # Never allow the FIFO to backpressure the network.
                        # Dropping a packet is preferable to replaying stale
                        # microphone audio later.
                        continue

        except Exception as e:
            info(f"mic stream disconnected: {e}")
            time.sleep(1.0)

        finally:
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass

            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass
