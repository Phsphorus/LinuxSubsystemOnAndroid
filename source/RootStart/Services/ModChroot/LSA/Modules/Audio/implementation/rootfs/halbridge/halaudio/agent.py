"""Audio-scoped HALAgent client used by the unprivileged HALAudio process."""

import os
import socket
import sys

from .logging import info


HALAGENT_HOST = "127.0.0.1"
HALAGENT_PORT = 5556


def _audio_token():
    path = os.environ.get("LSA_HAL_AUDIO_TOKEN_FILE", "")
    if not path:
        raise RuntimeError("LSA_HAL_AUDIO_TOKEN_FILE is not set")
    with open(path, encoding="utf-8") as handle:
        token = handle.read().strip()
    if not token:
        raise RuntimeError("audio-control credential is empty")
    return token


def _request(command):
    """Send one command without logging the per-user credential."""
    try:
        token = _audio_token()
        with socket.create_connection((HALAGENT_HOST, HALAGENT_PORT), timeout=3.0) as conn:
            conn.settimeout(5.0)
            conn.sendall(f"{token} {command}\n".encode("utf-8"))
            response = conn.recv(4096).decode("utf-8", "replace").strip()
        return response or "ERR empty_response"
    except Exception as exc:
        return f"EXC {type(exc).__name__}: {exc}"

def control_halagent_sink(spec):
    backend = os.environ.get("LSA_AUDIO_BACKEND", "aaudio").strip().lower()
    if backend not in {"aaudio", "opensles", "sox", "pulse-proxy", "termux-api"}:
        print(f"[HALAudio] unsupported selected audio backend: {backend}", file=sys.stderr)
        return False
    info("Stopping halagent sink if any")
    _request("AUDIOSINK_STOP")
    info("Starting halagent sink")
    resp = _request(
        "AUDIOSINK_START "
        f"backend={backend} format={spec['format']} rate={spec['rate']} channels={spec['channels']}"
    )
    info(
        f"halagent {resp} requested="
        f"backend={backend} {spec['format']} {spec['channels']}ch {spec['rate']}Hz"
    )
    if not (resp.startswith("OK") or resp == "ERR sink_running"):
        print("[HALAudio] halagent AUDIOSINK failed or not supported", file=sys.stderr)
        print(f"[HALAudio] Response {resp}", file=sys.stderr)
        return False
    return True

def control_halagent_mic():
    info("Stopping halagent mic if any")
    _request("MIC_STOP")
    info("Starting halagent mic")
    resp = _request("MIC_START")
    info(f"halagent mic {resp}")

    if not (resp.startswith("OK") or resp == "ERR source_running"):
        print(
            "[HALAudio] halagent microphone failed or not supported",
            file=sys.stderr,
        )
        print(f"[HALAudio] Response {resp}", file=sys.stderr)
        return False

    return True
