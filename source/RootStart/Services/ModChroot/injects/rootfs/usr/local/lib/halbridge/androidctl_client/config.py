from pathlib import Path
HOST = "127.0.0.1"
PORT = 5556
BRIDGE_BASE = Path("/mnt/halbridge")
BRIDGE_CAM = BRIDGE_BASE / "cam"
BRIDGE_REC = BRIDGE_BASE / "rec"
SECRET_DIR = BRIDGE_BASE / "secret"
SECRET_PATH = SECRET_DIR / "secret"
