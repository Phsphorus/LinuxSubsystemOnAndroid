import threading
import time
from .pulse import setup_env, start_pulseaudio, ensure_android_sink
from .control import control_server
from .tuner import auto_tuner
from .agent import control_halagent_mic
from .stream import stream_loop
from .source_stream import source_stream_loop
from .logging import info

def main():
    setup_env()
    start_pulseaudio()
    ensure_android_sink()
    threading.Thread(target=control_server, daemon=True).start()
    threading.Thread(target=auto_tuner, daemon=True).start()
    mic_ok = control_halagent_mic()
    if not mic_ok:
        info("Continuing without halagent microphone control")
    else:
        threading.Thread(
            target=source_stream_loop,
            daemon=True,
            name="HALAudio-mic",
        ).start()

    # The Android provider can be briefly restarted by Termux or Android
    # without invalidating the Linux Pulse sink.  A dropped PCM TCP socket
    # must therefore reconnect instead of taking down the entire output path
    # and leaving only a visible-but-silent AndroidSink behind.
    while True:
        rc = stream_loop()
        info(f"Streaming pipeline ended exit code {rc}; retrying in one second")
        time.sleep(1.0)
