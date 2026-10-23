import os
import stat
from .config import (
    SHARED_BASE, CAM_TMP, REC_TMP, HAL_BASE, HAL_CAM, HAL_REC,
    HAL_SECRET_DIR, PLAY_TMP, LOG_DIR,
)

def ensure_private_directory(path, mode):
    """Create a root-owned state directory without following a replacement.

    HAL state is reached by a privileged service.  Unlike the explicit shared
    Android media staging area, no child below HAL_BASE needs to be writable
    by an arbitrary local UID.
    """
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        os.mkdir(path, mode)
        st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode) or st.st_uid != 0:
        raise RuntimeError(f"unsafe HAL runtime directory: {path}")
    os.chmod(path, mode)


def ensure_runtime_dirs():
    # Secure the parent before creating children in it.  In particular, do
    # not create the authentication directory below a world-writable state
    # directory left by an older deployment.
    os.makedirs(HAL_BASE, mode=0o711, exist_ok=True)
    try:
        os.chmod(HAL_BASE, 0o711)
    except Exception:
        pass

    for d in (SHARED_BASE, CAM_TMP, REC_TMP, PLAY_TMP, LOG_DIR):
        os.makedirs(d, exist_ok=True)

    # State children are private root service state.  Cross-UID media exchange
    # uses SHARED_BASE, so allowing writes here only enabled replacement and
    # symlink attacks against a privileged consumer.
    for d in (HAL_CAM, HAL_REC, HAL_SECRET_DIR):
        ensure_private_directory(d, 0o700)
