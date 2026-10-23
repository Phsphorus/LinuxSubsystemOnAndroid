# LSA_MODE_CONTROLLER
#
# Privileged Android-side LSA ownership-mode controller.
#
# SHARED:
#   Android remains interactive.
#   X11 logical grabs remain valid.
#   Android physical pointer capture is not authoritative.
#
# FULL:
#   LSA-X11 becomes the interactive frontend.
#   Android SystemUI expansion is blocked.
#   X11 physical pointer capture may be honored.
#
# Android userspace quiescing is intentionally NOT implemented
# here yet. It will be attached after this transition engine is
# independently proven.

import os
import subprocess
import threading
import time

from .config import (
    MODE_STATE_PATH,
    LSA_X11_PACKAGE,
    LSA_X11_ACTIVITY,
)
from .logging import log


_MODE_LOCK = threading.RLock()

_VALID_MODES = ("shared", "full")


def _android_env():
    env = os.environ.copy()

    # Android framework tools must never inherit Termux linker
    # pollution from the root service environment.
    env.pop("LD_LIBRARY_PATH", None)
    env.pop("LD_PRELOAD", None)
    env.pop("LD_AUDIT", None)

    env["PATH"] = (
        "/system/bin:"
        "/system_ext/bin:"
        "/product/bin:"
        "/vendor/bin:"
        "/odm/bin"
    )

    return env


def _run_android(argv, timeout=8):
    try:
        proc = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            env=_android_env(),
        )

        out = (proc.stdout or "").strip()

        log(
            "MODE EXEC "
            + repr(argv)
            + f" rc={proc.returncode} out={out!r}"
        )

        return proc.returncode, out

    except Exception as e:
        log(f"MODE EXEC ERR argv={argv!r} error={e}")
        return 255, str(e)


def _write_state(mode):
    if mode not in _VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}")

    directory = os.path.dirname(MODE_STATE_PATH)
    os.makedirs(directory, exist_ok=True)

    tmp = MODE_STATE_PATH + ".tmp"

    with open(tmp, "w") as f:
        f.write(mode + "\n")

    os.chmod(tmp, 0o644)
    os.replace(tmp, MODE_STATE_PATH)


def _read_state():
    try:
        with open(MODE_STATE_PATH) as f:
            mode = f.read().strip().lower()

        if mode in _VALID_MODES:
            return mode

    except Exception:
        pass

    return "shared"


def _package_installed():
    rc, out = _run_android([
        "/system/bin/cmd",
        "package",
        "path",
        LSA_X11_PACKAGE,
    ])

    return rc == 0 and "package:" in out


def _start_lsa_x11():
    component = (
        LSA_X11_PACKAGE
        + "/"
        + LSA_X11_ACTIVITY
    )

    rc, out = _run_android([
        "/system/bin/am",
        "start",
        "--user",
        "0",
        "-n",
        component,
    ])

    if rc != 0:
        return False

    lower = out.lower()

    if "error type" in lower or "error:" in lower:
        return False

    return True


def _broadcast_mode(mode):
    action = LSA_X11_PACKAGE + ".LSA_MODE"

    rc, out = _run_android([
        "/system/bin/am",
        "broadcast",
        "--user",
        "0",
        "-a",
        action,
        "-p",
        LSA_X11_PACKAGE,
        "--es",
        "mode",
        mode,
    ])

    if rc != 0:
        return False

    lower = out.lower()

    if "error type" in lower or "error:" in lower:
        return False

    return True


def _statusbar_full():
    # Collapse anything already open first.
    _run_android([
        "/system/bin/cmd",
        "statusbar",
        "collapse",
    ])

    rc, _ = _run_android([
        "/system/bin/cmd",
        "statusbar",
        "send-disable-flag",
        "statusbar-expansion",
    ])

    return rc == 0


def _statusbar_shared():
    rc, _ = _run_android([
        "/system/bin/cmd",
        "statusbar",
        "send-disable-flag",
        "none",
    ])

    return rc == 0


def initialize_mode():
    """
    Every halagent start is a safety boundary.

    ./RST therefore always establishes SHARED regardless of
    whatever state existed before the restart.
    """

    with _MODE_LOCK:
        log("MODE INIT forcing SHARED")

        # If the LSA frontend exists, revoke exclusive capture.
        if _package_installed():
            if not _broadcast_mode("shared"):
                log("MODE INIT WARN frontend SHARED broadcast failed")

        if not _statusbar_shared():
            log("MODE INIT WARN statusbar restore failed")

        _write_state("shared")

        log("MODE INIT state=shared")


def mode_get():
    with _MODE_LOCK:
        return "OK " + _read_state()


def _enter_shared():
    """
    FULL -> SHARED ordering:

        frontend SHARED
        -> physical pointer capture revoked
        -> SystemUI restored
        -> state committed SHARED

    Failure to contact the frontend does NOT leave SystemUI
    disabled. SHARED is the safety state.
    """

    frontend_ok = True

    if _package_installed():
        frontend_ok = _broadcast_mode("shared")

        if not frontend_ok:
            log("MODE SHARED WARN frontend broadcast failed")

    status_ok = _statusbar_shared()

    if not status_ok:
        log("MODE SHARED WARN statusbar restore failed")

    _write_state("shared")

    log(
        "MODE COMMIT shared "
        f"frontend_ok={frontend_ok} statusbar_ok={status_ok}"
    )

    return "OK shared"


def _enter_full():
    """
    SHARED -> FULL phase-1 ordering:

        verify LSA-X11 installed
        -> launch LSA-X11
        -> block SystemUI expansion
        -> tell frontend FULL
        -> state committed FULL

    If the frontend transition fails, statusbar ownership is
    rolled back and state remains SHARED.
    """

    if not _package_installed():
        log(
            "MODE FULL refused: "
            f"{LSA_X11_PACKAGE} is not installed"
        )
        return "ERR lsa_x11_not_installed"

    if not _start_lsa_x11():
        log("MODE FULL refused: failed to start LSA-X11")
        return "ERR lsa_x11_start_failed"

    # Give MainActivity/receiver a moment to become available.
    time.sleep(0.30)

    if not _statusbar_full():
        log("MODE FULL refused: statusbar control failed")
        _statusbar_shared()
        return "ERR statusbar_control_failed"

    if not _broadcast_mode("full"):
        log("MODE FULL rollback: frontend broadcast failed")

        # Best-effort frontend revoke, then restore Android UI.
        _broadcast_mode("shared")
        _statusbar_shared()
        _write_state("shared")

        return "ERR lsa_x11_mode_broadcast_failed"

    _write_state("full")

    log("MODE COMMIT full")

    return "OK full"


def mode_set(mode):
    mode = (mode or "").strip().lower()

    if mode not in _VALID_MODES:
        return "ERR mode_must_be_full_or_shared"

    with _MODE_LOCK:
        current = _read_state()

        log(f"MODE REQUEST current={current} requested={mode}")

        # Reapplying the same mode intentionally resynchronizes
        # the external Android/frontend state.
        if mode == "shared":
            return _enter_shared()

        return _enter_full()
