import os
import re
import subprocess
import sys
import time
from .config import PA_HOME, PA_RUN, SINK_NAME, SOURCE_NAME, SOURCE_FIFO
from .logging import info
from .utils import run


AEC_SOURCE_NAME = "LSAAecSource"
AEC_SINK_NAME = "LSAAecSink"
AEC_MODULE_NAME = "module-echo-cancel"


def _lsa_aec_module_id():
    """Return LSA's echo-cancel module ID, without touching user modules."""
    result = run(["pactl", "list", "short", "modules"], capture=True)
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3:
            continue
        module_id, module_name, arguments = fields
        if (
            module_name == AEC_MODULE_NAME
            and f"source_name={AEC_SOURCE_NAME}" in arguments
            and f"sink_name={AEC_SINK_NAME}" in arguments
        ):
            return module_id
    return None


def _set_raw_defaults():
    run(["pactl", "set-default-sink", SINK_NAME])
    run(["pactl", "set-default-source", SOURCE_NAME])


def disable_echo_cancel(restore_defaults=True):
    """Unload only the named LSA AEC module, leaving user modules alone."""
    module_id = _lsa_aec_module_id()
    if module_id is not None:
        result = run(["pactl", "unload-module", module_id], capture=True)
        if result.returncode == 0:
            info("PulseAudio echo cancellation disabled")
        else:
            info("PulseAudio echo cancellation module could not be unloaded")
    if restore_defaults:
        _set_raw_defaults()


def configure_echo_cancel():
    """Select the one supported AEC path and expose it as Pulse defaults.

    Android's AcousticEchoCanceler attaches to a Java AudioRecord session.
    HALAudio currently captures through direct AAudio, so it cannot honestly
    claim that backend yet.  `auto` therefore chooses the verified PulseAudio
    WebRTC path; explicit `android` leaves raw endpoints selected until a real
    Android AudioRecord provider is added.
    """
    requested = os.environ.get("LSA_AEC_BACKEND", "auto").strip().lower()
    if requested not in {"auto", "pulseaudio", "android", "off"}:
        info(f"unknown AEC backend {requested!r}; using auto")
        requested = "auto"

    if requested == "off":
        disable_echo_cancel()
        info("AEC backend selected: off")
        return "off"

    if requested == "android":
        disable_echo_cancel()
        info(
            "Android AEC requested but unavailable: direct AAudio capture has "
            "no Android AudioRecord effect session; raw AndroidSource selected"
        )
        return "unavailable"

    module_id = _lsa_aec_module_id()
    if module_id is None:
        result = run(
            [
                "pactl",
                "load-module",
                AEC_MODULE_NAME,
                "aec_method=webrtc",
                f"source_master={SOURCE_NAME}",
                f"sink_master={SINK_NAME}",
                f"source_name={AEC_SOURCE_NAME}",
                f"sink_name={AEC_SINK_NAME}",
                f"source_properties=device.description={AEC_SOURCE_NAME}",
                f"sink_properties=device.description={AEC_SINK_NAME}",
            ],
            capture=True,
        )
        if result.returncode != 0:
            _set_raw_defaults()
            detail = (result.stderr or result.stdout).strip()
            info(f"PulseAudio WebRTC AEC unavailable; raw endpoints selected: {detail}")
            return "unavailable"
        module_id = result.stdout.strip()
        info(f"PulseAudio WebRTC AEC enabled module={module_id}")

    sink_result = run(["pactl", "set-default-sink", AEC_SINK_NAME], capture=True)
    source_result = run(["pactl", "set-default-source", AEC_SOURCE_NAME], capture=True)
    if sink_result.returncode != 0 or source_result.returncode != 0:
        disable_echo_cancel()
        info("PulseAudio WebRTC AEC endpoints were incomplete; raw endpoints selected")
        return "unavailable"

    info("AEC backend selected: pulseaudio-webrtc")
    return "pulseaudio"

def setup_env():
    info(f"HOME={PA_HOME}")
    info(f"XDG_RUNTIME_DIR={PA_RUN}")
    info(f"XDG_CONFIG_HOME={PA_HOME}/.config")
    os.makedirs(os.path.join(PA_HOME, ".config", "pulse"), exist_ok=True)
    os.makedirs(PA_RUN, exist_ok=True)
    try: os.chmod(PA_RUN, 0o777)
    except PermissionError: pass
    os.environ["HOME"] = PA_HOME
    os.environ["XDG_RUNTIME_DIR"] = PA_RUN
    os.environ["XDG_CONFIG_HOME"] = os.path.join(PA_HOME, ".config")
    os.environ.pop("PULSE_SERVER", None)
    os.environ.pop("PULSE_COOKIE", None)

def start_pulseaudio():
    info("Checking PulseAudio state")
    rc = subprocess.run(["pulseaudio", "--check"]).returncode
    if rc == 0:
        info("PulseAudio already running")
    else:
        info("Starting PulseAudio")
        result = subprocess.run(["pulseaudio", "-vv", "--log-target=stderr", "--exit-idle-time=-1", "--system=false", "--daemonize=yes"])
        if result.returncode != 0:
            print("[HALAudio] Failed to start PulseAudio", file=sys.stderr); raise SystemExit(1)
        time.sleep(1)
    os.environ["PULSE_SERVER"] = f"unix:{PA_RUN}/pulse/native"
    os.environ["PULSE_COOKIE"] = os.path.join(PA_HOME, ".config", "pulse", "cookie")
    info(f"PULSE_SERVER={os.environ['PULSE_SERVER']}")
    info(f"PULSE_COOKIE={os.environ['PULSE_COOKIE']}")
    info("Verifying pactl info")
    result = subprocess.run(["pactl", "info"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        print("[HALAudio] Cannot talk to PulseAudio at PULSE_SERVER", file=sys.stderr)
        print(result.stdout, file=sys.stderr); raise SystemExit(1)

def ensure_android_sink():
    info(f"Ensuring sink {SINK_NAME} exists")
    result = run(["pactl", "list", "short", "sinks"], capture=True)
    if SINK_NAME not in result.stdout:
        info(f"Creating sink {SINK_NAME}")
        result = run(["pactl", "load-module", "module-null-sink", f"sink_name={SINK_NAME}", f"sink_properties=device.description={SINK_NAME}"], capture=True)
        if result.returncode != 0:
            print("[HALAudio] Failed to load module null sink", file=sys.stderr)
            print(result.stderr, file=sys.stderr); raise SystemExit(1)
    else:
        info(f"Sink {SINK_NAME} already present")
    info(f"Setting default sink to {SINK_NAME}")
    result = run(["pactl", "set-default-sink", SINK_NAME])
    if result.returncode != 0:
        print("[HALAudio] Warning could not set default sink", file=sys.stderr)


def android_sink_spec():
    """Return the actual Pulse sample spec selected for AndroidSink."""
    result = run(["pactl", "list", "sinks"], capture=True)
    if result.returncode != 0:
        raise RuntimeError("cannot query PulseAudio sinks")

    in_sink = False
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if line.startswith("Name:"):
            in_sink = line.split(":", 1)[1].strip() == SINK_NAME
            continue
        if not in_sink or not line.startswith("Sample Specification:"):
            continue
        match = re.search(r"(\S+)\s+(\d+)ch\s+(\d+)Hz", line)
        if not match:
            break
        return {
            "format": match.group(1).lower(),
            "channels": int(match.group(2)),
            "rate": int(match.group(3)),
        }

    raise RuntimeError(f"PulseAudio did not expose a sample spec for {SINK_NAME}")


def ensure_android_source(spec):
    fmt = spec["format"]
    rate = int(spec["rate"])
    channels = int(spec["channels"])
    channel_map = spec.get("map", "")
    if channel_map == "-":
        channel_map = ""

    wanted = f"{fmt} {channels}ch {rate}Hz"

    info(
        f"Ensuring source {SOURCE_NAME} "
        f"format={fmt} rate={rate} channels={channels} "
        f"map={channel_map or '-'}"
    )

    result = run(["pactl", "list", "short", "sources"], capture=True)

    existing = False
    matching = False

    for line in result.stdout.splitlines():
        fields = line.split("\t")
        if len(fields) < 4:
            continue
        if fields[1].strip() != SOURCE_NAME:
            continue

        existing = True
        if fields[3].strip() == wanted:
            matching = True
        break

    if existing and matching:
        info(f"Source {SOURCE_NAME} already matches {wanted}")
        run(["pactl", "set-default-source", SOURCE_NAME])
        return True

    if existing:
        info(f"Source {SOURCE_NAME} exists with wrong sample spec; recreating")
        # AEC consumes AndroidSource as its master.  Remove only LSA's named
        # module before changing that master source's sample specification.
        disable_echo_cancel(restore_defaults=False)

        mods = run(["pactl", "list", "short", "modules"], capture=True)

        for line in mods.stdout.splitlines():
            fields = line.split("\t", 2)
            if len(fields) < 3:
                continue

            module_id, module_name, args = fields

            if (
                module_name == "module-pipe-source"
                and f"source_name={SOURCE_NAME}" in args
            ):
                run(["pactl", "unload-module", module_id])
                break

    # module-pipe-source owns creation of its FIFO.
    # Remove any stale path before loading the module.
    try:
        os.unlink(SOURCE_FIFO)
    except FileNotFoundError:
        pass


    args = [
        "pactl",
        "load-module",
        "module-pipe-source",
        f"source_name={SOURCE_NAME}",
        f"file={SOURCE_FIFO}",
        f"format={fmt}",
        f"rate={rate}",
        f"channels={channels}",
        f"source_properties=device.description={SOURCE_NAME}",
    ]

    if channel_map:
        args.append(f"channel_map={channel_map}")

    result = run(args, capture=True)

    if result.returncode != 0:
        print("[HALAudio] Failed to create AndroidSource", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return False

    result = run(["pactl", "set-default-source", SOURCE_NAME])

    if result.returncode != 0:
        print("[HALAudio] Warning could not set default source", file=sys.stderr)

    info(f"Source {SOURCE_NAME} ready as {wanted}")
    return True
