import sys
from .transport import send_cmd

def sink_cmd(args):
    if not args:
        print("usage: androidctl sink start [--format FMT --rate HZ --channels N]|stop", file=sys.stderr); raise SystemExit(1)
    if args[0] == "start":
        values = {}
        tail = args[1:]
        if len(tail) % 2:
            print("sink start options require values", file=sys.stderr); raise SystemExit(1)
        for flag, value in zip(tail[::2], tail[1::2]):
            key = {"--format": "format", "--rate": "rate", "--channels": "channels"}.get(flag)
            if key is None:
                print("usage: androidctl sink start [--format FMT --rate HZ --channels N]", file=sys.stderr); raise SystemExit(1)
            values[key] = value
        command = "AUDIOSINK_START" + "".join(f" {key}={value}" for key, value in values.items())
        print(send_cmd(command))
    elif args[0] == "stop":
        print(send_cmd("AUDIOSINK_STOP"))
    else:
        print("usage: androidctl sink start [--format FMT --rate HZ --channels N]|stop", file=sys.stderr); raise SystemExit(1)

def cpu_cmd(args):
    if not args:
        print("usage: androidctl cpu <low|cap900|normal|get>", file=sys.stderr); raise SystemExit(1)
    table = {"low":"CPU_LOW", "cap900":"CPU_CAP900", "normal":"CPU_NORMAL", "get":"CPU_GET"}
    cmd = table.get(args[0])
    if cmd is None:
        print("usage: androidctl cpu <low|cap900|normal|get>", file=sys.stderr); raise SystemExit(1)
    print(send_cmd(cmd))

# ============================================================
# LSA_MODE_CONTROLLER
# ============================================================

def mode_cmd(mode):
    """
    Public CLI contract:

        androidctl full
        androidctl shared
        androidctl mode
    """

    if mode == "mode":
        resp = send_cmd("MODE_GET")
    elif mode in ("full", "shared"):
        resp = send_cmd("MODE_SET " + mode)
    else:
        print(
            "usage: androidctl full|shared|mode",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if resp.startswith("OK "):
        print(resp[3:])
        return

    print(resp, file=sys.stderr)
    raise SystemExit(1)
