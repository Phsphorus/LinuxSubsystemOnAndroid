import sys
from .transport import send_cmd

def mic_cmd(args):
    if not args or args[0] not in ("start", "stop", "status"):
        print("usage: androidctl mic start|stop|status", file=sys.stderr)
        raise SystemExit(1)

    action = args[0]

    if action == "start":
        resp = send_cmd("MIC_START")
    elif action == "stop":
        resp = send_cmd("MIC_STOP")
    else:
        resp = send_cmd("MIC_STATUS")

    if resp.startswith("ERR"):
        print(resp, file=sys.stderr)
        raise SystemExit(1)

    print(resp)
