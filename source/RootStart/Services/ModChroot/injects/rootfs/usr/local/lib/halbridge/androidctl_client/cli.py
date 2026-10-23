import sys
from .helptext import HELP_TEXT
from .microphone import mic_cmd
from .speaker import spk_play, spk_stop, vol_cmd
from .system import sink_cmd, cpu_cmd, mode_cmd  # LSA_MODE_CONTROLLER

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "--help", "-h"):
        print(HELP_TEXT)
        print()
        print("LSA ownership modes:")
        print("  androidctl full    Enter exclusive LSA mode")
        print("  androidctl shared  Return to Android + LSA shared mode")
        print("  androidctl mode    Print current mode")
        raise SystemExit(0)
    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd == "mic": mic_cmd(args)
    elif cmd == "spk-play": spk_play(args)
    elif cmd == "spk-stop": spk_stop()
    elif cmd == "vol": vol_cmd(args)
    elif cmd == "sink": sink_cmd(args)
    elif cmd == "cpu": cpu_cmd(args)

    # LSA_MODE_CONTROLLER
    elif cmd == "full": mode_cmd("full")
    elif cmd == "shared": mode_cmd("shared")
    elif cmd == "mode": mode_cmd("mode")

    else:
        print(f"unknown command {cmd}\n", file=sys.stderr)
        print(HELP_TEXT, file=sys.stderr)
        raise SystemExit(1)
