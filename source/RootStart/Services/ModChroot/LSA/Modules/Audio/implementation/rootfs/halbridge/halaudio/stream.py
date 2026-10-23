import socket
import subprocess
import sys
from .agent import control_halagent_sink
from .config import AUDIO_HOST, AUDIO_PORT, SINK_MONITOR
from .logging import info
from .pulse import android_sink_spec
from .profiles import get_profile
from .utils import which, read_exact

def pin_output_capture(proc_pid):
    """Force HALAudio's output-capture pacat onto AndroidSink.monitor."""
    import time

    for _ in range(40):
        result = subprocess.run(
            ["pactl", "list", "source-outputs"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        current_index = None
        current_pid = None

        for line in result.stdout.splitlines():
            stripped = line.strip()

            if stripped.startswith("Source Output #"):
                current_index = stripped.split("#", 1)[1]
                current_pid = None
                continue

            if stripped.startswith("application.process.id ="):
                try:
                    current_pid = int(
                        stripped.split("=", 1)[1]
                        .strip()
                        .strip('"')
                    )
                except ValueError:
                    current_pid = None

                if current_index is not None and current_pid == proc_pid:
                    moved = subprocess.run(
                        [
                            "pactl",
                            "move-source-output",
                            current_index,
                            SINK_MONITOR,
                        ],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )

                    if moved.returncode == 0:
                        info(
                            f"pinned source-output #{current_index} "
                            f"pid={proc_pid} to {SINK_MONITOR}"
                        )
                        return True

        time.sleep(0.05)

    info(
        f"WARNING could not locate pacat source-output "
        f"pid={proc_pid} for pinning"
    )
    return False


def stream_loop():
    rec_cmd = None
    for cand in ("pacat", "parec"):
        if which(cand):
            rec_cmd = cand; break
    if rec_cmd is None:
        print("[HALAudio] pacat or parec not found", file=sys.stderr); return 1
    try:
        sink_spec = android_sink_spec()
    except Exception as exc:
        print(f"[HALAudio] cannot discover AndroidSink spec: {exc}", file=sys.stderr)
        return 1

    # PulseAudio owns conversion when its internal sink format is not raw
    # signed 16-bit PCM. Preserve its negotiated rate and layout where the
    # Android sink can accept them, and request conversion only when needed.
    spec = dict(sink_spec)
    if spec["format"] != "s16le":
        info(
            f"converting Pulse sink format {spec['format']} to s16le "
            "for the Android raw PCM transport"
        )
        spec["format"] = "s16le"
    if not 1 <= spec["channels"] <= 8:
        info(
            f"remixing Pulse sink layout {spec['channels']}ch to stereo "
            "for the Android raw PCM transport"
        )
        spec["channels"] = 2

    if not control_halagent_sink(spec):
        print("[HALAudio] cannot negotiate Android output sink", file=sys.stderr)
        return 1

    prof = get_profile()
    if rec_cmd == "pacat":
        cmd = [
            "pacat",
            "--record",
            "--client-name=LSA-HALAudio-OutputCapture",
            "--stream-name=LSA-HALAudio-AndroidSinkMonitor",
            "--device", SINK_MONITOR,
            f"--format={spec['format']}",
            f"--rate={spec['rate']}",
            f"--channels={spec['channels']}",
            f"--latency-msec={prof['pacat_latency_ms']}",
        ]
    else:
        cmd = [
            "parec", "-d", SINK_MONITOR, "--raw",
            f"--rate={spec['rate']}",
            f"--channels={spec['channels']}",
            f"--format={spec['format']}",
        ]
    info(
        f"using {rec_cmd} from {SINK_MONITOR} "
        f"format={spec['format']} rate={spec['rate']} channels={spec['channels']}"
    )
    info(f"initial profile {prof['effective_index']} {prof['name']} frames={prof['frames']} latency={prof['pacat_latency_ms']}ms")
    info(f"streaming via TCP to {AUDIO_HOST}:{AUDIO_PORT}")
    info("PulseAudio default sink selects the active LSA playback route")
    try:
        sock = socket.create_connection((AUDIO_HOST, AUDIO_PORT), timeout=5.0)
    except OSError as e:
        print(f"[HALAudio] Failed to connect to {AUDIO_HOST}:{AUDIO_PORT}: {e}", file=sys.stderr); return 1
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        pin_output_capture(proc.pid)
    except Exception as e:
        print(f"[HALAudio] failed to start {rec_cmd} {e}", file=sys.stderr); sock.close(); return 1
    try:
        while True:
            prof = get_profile()
            bytes_per_frame = spec["channels"] * 2
            data = read_exact(proc.stdout, prof["frames"] * bytes_per_frame)
            if not data: break
            try: sock.sendall(data)
            except Exception as e:
                print(f"[HALAudio] sendall error {e}", file=sys.stderr); break
    except KeyboardInterrupt:
        info("KeyboardInterrupt stopping stream")
    finally:
        try: proc.terminate()
        except Exception: pass
        try: proc.wait(timeout=1)
        except Exception: pass
        try: sock.close()
        except Exception: pass
        info("streamer exited")
    return 0
