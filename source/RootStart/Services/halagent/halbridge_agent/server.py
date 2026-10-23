import socket
import threading
import hmac
from . import auth
from .config import HOST, PORT
from .cpu import detect_cpu_clusters
from .dispatch import dispatch_cmd
from .logging import log
from .runtime import ensure_runtime_dirs
from .mode import initialize_mode  # LSA_MODE_CONTROLLER

MAX_REQUEST_BYTES = 4096
MAX_CLIENTS = 16
CLIENT_SLOTS = threading.BoundedSemaphore(MAX_CLIENTS)
# The audio user gets a distinct, short-scope credential.  It cannot operate
# camera, CPU, playback, volume, or global mode controls.
AUDIO_CLIENT_COMMANDS = frozenset({
    "AUDIOSINK_START",
    "AUDIOSINK_STOP",
    "MIC_START",
    "MIC_STOP",
    "MIC_STATUS",
})


def client_thread(conn, addr):
    try:
        conn.settimeout(5.0)
        log(f"connection from {addr}")
        data = conn.recv(MAX_REQUEST_BYTES + 1)
        if not data:
            return
        if len(data) > MAX_REQUEST_BYTES:
            # Do not render received bytes in logs: an overlong pre-auth
            # request can still contain a valid authentication secret.
            log(f"authentication request rejected for {addr}: request too large")
            conn.sendall(b"ERR request_too_large\n")
            return
        line = data.decode("utf8", "ignore").strip()
        if not line:
            return
        if auth.SECRET is None or auth.AUDIO_SECRET is None:
            log(f"authentication unavailable for {addr}")
            resp = "ERR auth_unavailable"
        else:
            parts = line.split()
            if len(parts) < 2:
                log(f"authentication failed for {addr}: malformed request")
                resp = "ERR bad_format"
            elif hmac.compare_digest(parts[0], auth.SECRET):
                log(f"authentication succeeded for {addr}; authenticated request received")
                resp = dispatch_cmd(parts[1], parts[2:])
            elif hmac.compare_digest(parts[0], auth.AUDIO_SECRET):
                if parts[1] not in AUDIO_CLIENT_COMMANDS:
                    log(f"audio authentication scope rejected for {addr}")
                    resp = "ERR auth_scope"
                else:
                    log(f"audio authentication succeeded for {addr}; audio request received")
                    resp = dispatch_cmd(parts[1], parts[2:])
            else:
                log(f"authentication failed for {addr}")
                resp = "ERR auth"
        log(f"response for {addr}: {resp.split(None, 1)[0] if resp else 'EMPTY'}")
        conn.sendall((resp + "\n").encode("utf8"))
    finally:
        try:
            conn.close()
        finally:
            CLIENT_SLOTS.release()

def main():
    ensure_runtime_dirs()

    # LSA_MODE_CONTROLLER
    # RST / halagent restart always returns ownership to SHARED.
    initialize_mode()

    detect_cpu_clusters()
    auth.load_or_create_secret()
    log(f"halagent modular starting on {HOST}:{PORT}")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen(5)
    while True:
        conn, addr = s.accept()
        if not CLIENT_SLOTS.acquire(blocking=False):
            # Bounded unauthenticated connections prevent a local app from
            # consuming the service with idle TCP sessions.  Again, only
            # metadata is logged before authentication.
            log(f"connection rejected for {addr}: client limit reached")
            conn.close()
            continue
        threading.Thread(target=client_thread, args=(conn, addr), daemon=True).start()
