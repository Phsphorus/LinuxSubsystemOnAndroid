import os

HOST = "127.0.0.1"
PORT = 5556

TERMUX_BIN = "/data/data/com.termux/files/usr/bin"
TERMUX_HOME = "/data/data/com.termux/files/home"
SHARED_BASE = "/sdcard/halbridge"

CAM_TMP = os.path.join(SHARED_BASE, "camtmp")
REC_TMP = os.path.join(TERMUX_HOME, "rectmp")

HAL_BASE = "/data/local/RootStart/Services/halagent/state"
HAL_CAM = os.path.join(HAL_BASE, "cam")
HAL_REC = os.path.join(HAL_BASE, "rec")
HAL_SECRET_DIR = os.path.join(HAL_BASE, "secret")
SECRET_PATH = os.path.join(HAL_SECRET_DIR, "secret")
# A second credential is delivered only to the selected Linux audio user.
# HALAgent accepts it for the small audio-control command set, while the
# master credential remains root-only for all other Android controls.
AUDIO_SECRET_PATH = os.path.join(HAL_SECRET_DIR, "audio-secret")

PLAY_TMP = os.path.join(SHARED_BASE, "playtmp")

SINK_PORT = 8556
AUDIO_CTRL_HOST = "127.0.0.1"
AUDIO_CTRL_PORT = 7000

SERVICE_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOG_DIR = os.path.join(SERVICE_BASE, "logs")
LOG_PATH = os.path.join(LOG_DIR, "halagent.log")

# ============================================================
# LSA_MODE_CONTROLLER
# ============================================================

# Authoritative runtime mode state.
MODE_STATE_PATH = os.path.join(HAL_BASE, "mode")

# LSA's own Termux:X11 fork.
#
# Keep the Java activity namespace unchanged; only the Android
# application ID is being isolated from upstream Termux:X11.
LSA_X11_PACKAGE = "com.phsphorus.lsa.x11"
LSA_X11_ACTIVITY = "com.termux.x11.MainActivity"

