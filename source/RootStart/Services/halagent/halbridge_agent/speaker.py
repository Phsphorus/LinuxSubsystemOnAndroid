import os
import shutil
from .config import PLAY_TMP, HAL_REC, HAL_CAM
from .common import run_termux, termux_cmd
from .logging import log

last_play_tmp = None

def vol_set(stream: str, level: str):
    proc = run_termux([termux_cmd("termux-volume"), stream.strip().lower(), level], "VOL")
    return "OK" if proc.returncode == 0 else "ERR vol_failed"

def resolve_play_path(arg: str) -> str:
    arg = arg.strip()
    if not arg: return ""
    if arg.startswith("/"): return arg
    cand = os.path.join(HAL_REC, arg)
    if os.path.exists(cand): return cand
    cand = os.path.join(HAL_CAM, arg)
    if os.path.exists(cand): return cand
    return ""

def spk_play(arg: str):
    global last_play_tmp
    src = resolve_play_path(arg)
    if not src or not os.path.exists(src):
        log(f"SPK play: source not found: {arg}")
        return "ERR play_not_found"
    try: vol_set("music", "15")
    except Exception as e: log(f"SPK VOL_SET WARN {e}")
    dst = os.path.join(PLAY_TMP, os.path.basename(src))
    try: shutil.copy2(src, dst)
    except Exception as e:
        log(f"SPK copy ERR {e}")
        return "ERR play_copy_failed"
    proc = run_termux([termux_cmd("termux-media-player"), "play", dst], "SPK_PLAY")
    if proc.returncode != 0:
        return "ERR play_failed"
    run_termux([termux_cmd("termux-media-player"), "info"], "SPK_INFO")
    try:
        if os.path.commonpath([os.path.abspath(src), os.path.abspath(HAL_REC)]) == os.path.abspath(HAL_REC):
            if os.path.exists(src):
                os.remove(src)
                log(f"SPK removed source {src}")
    except Exception as e:
        log(f"SPK remove source ERR {e}")
    last_play_tmp = dst
    return "OK"

def spk_stop():
    global last_play_tmp
    proc = run_termux([termux_cmd("termux-media-player"), "stop"], "SPK_STOP")
    if proc.returncode != 0:
        return "ERR stop_failed"
    try:
        if last_play_tmp and os.path.exists(last_play_tmp): os.remove(last_play_tmp)
    except Exception as e:
        log(f"SPK_STOP remove tmp ERR {e}")
    last_play_tmp = None
    return "OK"
