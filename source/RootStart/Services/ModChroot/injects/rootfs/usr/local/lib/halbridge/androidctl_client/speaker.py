import shutil
import sys
from pathlib import Path
from .config import BRIDGE_REC
from .files import ensure_dir
from .transport import send_cmd

def spk_play(args):
    if not args:
        print("usage: androidctl spk-play <file>", file=sys.stderr); raise SystemExit(1)
    src = Path(args[0]).expanduser()
    if not src.exists():
        print(f"no such file: {src}", file=sys.stderr); raise SystemExit(1)
    ensure_dir(BRIDGE_REC)
    shutil.copy2(src, BRIDGE_REC / src.name)
    print(send_cmd(f"SPK_PLAY {src.name}"))

def spk_stop():
    print(send_cmd("SPK_STOP"))

def vol_cmd(args):
    if len(args) < 2:
        print("usage: androidctl vol <music|ring|alarm|stream> <level 0-15>", file=sys.stderr); raise SystemExit(1)
    stream, level = args[0], args[1]
    try: lvl = int(level)
    except ValueError:
        print("level must be an integer 0-15", file=sys.stderr); raise SystemExit(1)
    if not 0 <= lvl <= 15:
        print("level must be between 0 and 15", file=sys.stderr); raise SystemExit(1)
    print(send_cmd(f"VOL_SET {stream} {lvl}"))
