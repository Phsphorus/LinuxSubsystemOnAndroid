import socket
from .config import HOST, PORT, SECRET_DIR, SECRET_PATH

_SECRET = None

def load_secret():
    global _SECRET
    if _SECRET is not None:
        return _SECRET
    if not SECRET_DIR.exists():
        raise RuntimeError(f"secret dir missing {SECRET_DIR}")
    token = SECRET_PATH.read_text().strip()
    if not token:
        raise RuntimeError("secret file is empty")
    _SECRET = token
    return token

def send_cmd(cmd: str) -> str:
    cmd = cmd.strip()
    if not cmd:
        return "ERR empty_cmd"
    try:
        secret = load_secret()
    except Exception as e:
        return f"ERR cannot read shared secret at {SECRET_PATH}: {e}"
    full = f"{secret} {cmd}"
    try:
        with socket.create_connection((HOST, PORT), timeout=5) as s:
            s.sendall((full + "\n").encode("utf8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
    except OSError as e:
        return f"ERR connect {e}"
    return data.decode("utf8", "ignore").strip()
