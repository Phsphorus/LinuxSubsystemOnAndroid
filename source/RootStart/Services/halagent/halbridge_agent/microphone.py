import socket

from .logging import log

HALAUDIOS_HOST = "127.0.0.1"
HALAUDIOS_CTRL_PORT = 7000


def _halaudios_cmd(cmd: str) -> str:
    try:
        with socket.create_connection(
            (HALAUDIOS_HOST, HALAUDIOS_CTRL_PORT),
            timeout=5,
        ) as s:
            s.sendall((cmd.strip() + "\n").encode("utf8"))

            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk

        resp = data.decode("utf8", "ignore").strip()

        if not resp:
            return "ERR empty_response"

        return resp

    except OSError as e:
        log(f"MIC relay ERR cmd={cmd!r}: {e}")
        return f"ERR halaudios {e}"


def mic_start():
    return _halaudios_cmd("START_SOURCE")


def mic_stop():
    return _halaudios_cmd("STOP_SOURCE")


def mic_status():
    return _halaudios_cmd("STATUS_SOURCE")
