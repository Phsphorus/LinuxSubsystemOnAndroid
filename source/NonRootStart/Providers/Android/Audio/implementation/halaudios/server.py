import socket
import threading
from .config import HOST, CTRL_PORT, AUDIO_PORT
from .logging import log, ensure_log_dir
from .sink import start_sink, stop_sink
from .source import start_source, stop_source, status_source


def parse_sink_start(line: str) -> dict:
    fields = line.split()
    if not fields or fields[0] != "START":
        raise ValueError("not_start")
    spec = {}
    for field in fields[1:]:
        key, separator, value = field.partition("=")
        if separator != "=" or key not in {"FORMAT", "RATE", "CHANNELS", "BACKEND"}:
            raise ValueError("bad_sink_spec")
        spec[key.lower()] = value
    return spec

def handle_client(conn: socket.socket, addr):
    try:
        data = conn.recv(1024)
        if not data:
            return
        line = data.decode("utf8", "ignore").strip().upper()
        log(f"CTRL REQ {addr}: {line!r}")
        if line == "START" or line.startswith("START "):
            try:
                spec = parse_sink_start(line)
                backend = spec.pop("backend", "aaudio").lower()
                resp = start_sink(spec, backend)
            except ValueError as exc:
                resp = f"ERR {exc}"
        elif line == "STOP":
            resp = stop_sink()
        elif line == "START_SOURCE":
            resp = start_source()
        elif line == "STOP_SOURCE":
            resp = stop_source()
        elif line == "STATUS_SOURCE":
            resp = status_source()
        else:
            resp = "ERR unknown_cmd"
        log(f"CTRL RESP {addr}: {resp}")
        conn.sendall((resp + "\n").encode("utf8"))
    finally:
        conn.close()

def main():
    ensure_log_dir()
    log(f"AndroidAudioProvider starting on {HOST}:{CTRL_PORT}, AUDIO_PORT={AUDIO_PORT}")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, CTRL_PORT))
    s.listen(5)
    while True:
        conn, addr = s.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
