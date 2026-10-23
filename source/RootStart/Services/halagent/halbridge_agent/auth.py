import os
import errno
import stat
from .config import HAL_BASE, HAL_SECRET_DIR, SECRET_PATH, AUDIO_SECRET_PATH
from .logging import log

SECRET = None
AUDIO_SECRET = None


def _enforce_private_directory(path, mode):
    if os.geteuid() == 0:
        os.chown(path, 0, 0)
    os.chmod(path, mode)
    current = stat.S_IMODE(os.stat(path).st_mode)
    if current != mode:
        raise PermissionError(f"unsafe mode on authentication directory: {oct(current)}")


def _secret_needs_rotation(path):
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(metadata.st_mode):
        return True
    mode = stat.S_IMODE(metadata.st_mode)
    return mode != 0o600 or (os.geteuid() == 0 and metadata.st_uid != 0)


def _create_secret(path):
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(os.urandom(32).hex() + "\n")


def _load_or_create_secret(path):
    if _secret_needs_rotation(path):
        # A world-readable, replaceable, foreign-owned, or non-regular
        # credential may already be known to another user.  Replacing it is
        # safer than merely narrowing permissions around a leaked token.
        os.unlink(path)
    try:
        _create_secret(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

    if _secret_needs_rotation(path):
        raise PermissionError("authentication secret ownership or mode is unsafe")

    with open(path, encoding="utf-8") as handle:
        secret = handle.read().strip()
    if not secret:
        raise ValueError("empty secret file")
    return secret


def load_or_create_secret():
    global SECRET, AUDIO_SECRET
    try:
        os.makedirs(HAL_BASE, mode=0o711, exist_ok=True)
        _enforce_private_directory(HAL_BASE, 0o711)
        os.makedirs(HAL_SECRET_DIR, mode=0o700, exist_ok=True)
        _enforce_private_directory(HAL_SECRET_DIR, 0o700)

        SECRET = _load_or_create_secret(SECRET_PATH)
        AUDIO_SECRET = _load_or_create_secret(AUDIO_SECRET_PATH)
        log("HAL authentication material is ready")
    except Exception as e:
        SECRET = None
        AUDIO_SECRET = None
        log(f"HAL authentication setup failed: {e}")
    return SECRET
