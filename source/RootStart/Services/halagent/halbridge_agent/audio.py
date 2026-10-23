import socket
from .config import AUDIO_CTRL_HOST, AUDIO_CTRL_PORT, SINK_PORT
from .logging import log

def _audio_ctrl_send(cmd: str) -> str:
    action = cmd.strip().split(None, 1)[0].upper() if cmd.strip() else "EMPTY"
    try:
        with socket.create_connection((AUDIO_CTRL_HOST, AUDIO_CTRL_PORT), timeout=2) as s:
            s.sendall((cmd.strip().upper() + "\n").encode("utf8"))
            resp = s.recv(1024).decode("utf8", "ignore").strip()
        result = resp.split(None, 1)[0] if resp else "EMPTY"
        log(f"AUDIOSINK_CTRL action={action} result={result}")
        return resp
    except Exception as e:
        log(f"AUDIOSINK_CTRL action={action} failed={type(e).__name__}")
        return "ERR ctrl_failed"

def audio_sink_start(args=None):
    args = args or []
    allowed = {"format", "rate", "channels", "backend"}
    fields = []
    for token in args:
        key, separator, value = token.partition("=")
        if separator != "=" or key not in allowed or not value:
            return "ERR bad_sink_spec"
        if key == "backend" and value.lower() not in {"aaudio", "opensles", "sox", "pulse-proxy", "termux-api"}:
            return "ERR unsupported_sink_backend"
        fields.append(f"{key}={value}")
    command = "START" + (" " + " ".join(fields) if fields else "")
    resp = _audio_ctrl_send(command)
    return f"OK {SINK_PORT}" if resp.startswith("OK") else "ERR sink_start_failed"

def audio_sink_stop():
    resp = _audio_ctrl_send("STOP")
    return "OK" if resp.startswith("OK") else "ERR sink_not_running"
