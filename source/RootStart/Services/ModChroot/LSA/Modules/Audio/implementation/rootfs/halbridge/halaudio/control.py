import os
import socket
from .config import CTRL_SOCK_PATH
from .logging import info
from .profiles import bump_profile_user, get_profile_status

def control_server():
    try: os.unlink(CTRL_SOCK_PATH)
    except FileNotFoundError: pass
    except OSError: pass
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(CTRL_SOCK_PATH)
    s.listen(5)
    info(f"Control socket listening on {CTRL_SOCK_PATH}")
    while True:
        conn, _ = s.accept()
        with conn:
            try: data = conn.recv(1024)
            except Exception: continue
            if not data: continue
            cmd = data.decode("utf8", "ignore").strip().upper()
            if cmd == "UP":
                # Preserve chosen baseline semantics exactly.
                eff, p = bump_profile_user(-1)
                resp = f"OK manual UP -> eff={eff} {p['name']} frames={p['frames']} latency={p['pacat_latency_ms']}ms\n"
            elif cmd == "DOWN":
                eff, p = bump_profile_user(+1)
                resp = f"OK manual DOWN -> eff={eff} {p['name']} frames={p['frames']} latency={p['pacat_latency_ms']}ms\n"
            elif cmd in ("STATUS", ""):
                auto_i, off, eff, p = get_profile_status()
                resp = f"OK status auto={auto_i} offset={off} eff={eff} {p['name']} frames={p['frames']} latency={p['pacat_latency_ms']}ms\n"
            else:
                resp = "ERR unknown_cmd\n"
            try: conn.sendall(resp.encode("utf8"))
            except Exception: pass
