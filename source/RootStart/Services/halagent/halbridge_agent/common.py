import os
import re
import subprocess
import time
from .config import TERMUX_BIN
from .logging import log

def safe_name(name: str) -> str:
    name = name.strip()
    if not name:
        name = "snap"
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)

def timestamp_name(prefix="snap", ext=".jpg") -> str:
    return f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}{ext}"

def run_termux(cmd, tag):
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    # Command output can carry caller-controlled or provider-controlled data.
    # Preserve outcome diagnostics without writing the payload to a persistent
    # HALAgent log.
    log(
        f"{tag} rc={proc.returncode} "
        f"stdout_bytes={len(proc.stdout or '')} stderr_bytes={len(proc.stderr or '')}"
    )
    return proc

def termux_cmd(name: str) -> str:
    return os.path.join(TERMUX_BIN, name)
