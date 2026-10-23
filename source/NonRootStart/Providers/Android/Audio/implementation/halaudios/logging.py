import os
import time
from .config import LOG_DIR, LOG_PATH

def ensure_log_dir():
    os.makedirs(LOG_DIR, exist_ok=True)

def log(msg: str):
    ensure_log_dir()
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    try:
        with open(LOG_PATH, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
