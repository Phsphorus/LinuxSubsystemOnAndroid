import time
from pathlib import Path

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def wait_for_file(p: Path, timeout: float = 5.0, interval: float = 0.1) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if p.exists() and p.stat().st_size > 0:
            return True
        time.sleep(interval)
    return p.exists() and p.stat().st_size > 0
