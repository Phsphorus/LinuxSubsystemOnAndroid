import threading
from .config import PROFILES
from .logging import info

AUTO_INDEX = 0
USER_OFFSET = 0
PROFILE_LOCK = threading.Lock()

def _clamp_index(idx: int) -> int:
    return max(0, min(len(PROFILES) - 1, idx))

def get_profile():
    with PROFILE_LOCK:
        eff = _clamp_index(AUTO_INDEX + USER_OFFSET)
        base = PROFILES[eff].copy()
        base["auto_index"] = AUTO_INDEX
        base["user_offset"] = USER_OFFSET
        base["effective_index"] = eff
    return base

def bump_profile_user(delta: int):
    global USER_OFFSET
    with PROFILE_LOCK:
        USER_OFFSET += delta
        eff = _clamp_index(AUTO_INDEX + USER_OFFSET)
        p = PROFILES[eff]
    info(f"Manual bump: auto={AUTO_INDEX} offset={USER_OFFSET} -> effective={eff} ({p['name']})")
    return eff, p

def bump_profile_auto(delta: int):
    global AUTO_INDEX
    with PROFILE_LOCK:
        AUTO_INDEX = _clamp_index(AUTO_INDEX + delta)
        eff = _clamp_index(AUTO_INDEX + USER_OFFSET)
        p = PROFILES[eff]
    info(f"Auto set: auto={AUTO_INDEX} offset={USER_OFFSET} -> effective={eff} ({p['name']})")
    return eff, p

def set_auto_index(idx: int):
    global AUTO_INDEX
    with PROFILE_LOCK:
        AUTO_INDEX = _clamp_index(idx)
        eff = _clamp_index(AUTO_INDEX + USER_OFFSET)
        p = PROFILES[eff]
    info(f"Auto set: auto={AUTO_INDEX} offset={USER_OFFSET} -> effective={eff} ({p['name']})")
    return eff, p

def get_profile_status():
    with PROFILE_LOCK:
        auto_i = AUTO_INDEX
        off = USER_OFFSET
        eff = _clamp_index(auto_i + off)
        p = PROFILES[eff]
    return auto_i, off, eff, p
