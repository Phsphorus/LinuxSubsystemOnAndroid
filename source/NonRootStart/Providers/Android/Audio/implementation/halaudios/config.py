import os
HOST = "127.0.0.1"
CTRL_PORT = 7000
AUDIO_PORT = 8556
TERMUX_PREFIX = "/data/data/com.termux/files/usr"
TERMUX_BIN = os.path.join(TERMUX_PREFIX, "bin")
# Provider logs belong to the Termux-owned provider tree.  The Android shared
# media directory can be owned by a different app UID and is not a safe place
# for a Termux service to create or append its diagnostics.
PROVIDER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LOG_DIR = os.path.join(PROVIDER_DIR, "logs")
LOG_PATH = os.path.join(LOG_DIR, "audio.log")

SOURCE_PORT = 8557

# Android's output path accepts a negotiated raw PCM spec per connection.  The
# conservative default preserves the proven N6000 behavior when a caller does
# not negotiate explicitly.
DEFAULT_SINK_SPEC = {
    "format": "s16le",
    "rate": 48000,
    "channels": 2,
}
