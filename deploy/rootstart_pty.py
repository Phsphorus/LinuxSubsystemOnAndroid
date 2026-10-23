#!/usr/bin/env python3
"""Keep RootStart attached to a real pseudo-terminal after deployment.

RootStart deliberately owns an interactive ModChroot session.  A bare nohup
launch has no controlling TTY, which makes the chroot shell exit immediately.
This small generic supervisor owns the PTY master, streams child output to an
LSA runtime log, and forwards normal termination to the RootStart process
group.  It contains no Android-device or model policy.
"""
from __future__ import annotations

import os
import pty
import signal
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 4:
        print(f"usage: {sys.argv[0]} LOG COMMAND [ARG ...]", file=sys.stderr)
        return 2

    log_path = Path(sys.argv[1])
    command = sys.argv[2:]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    pid, master_fd = pty.fork()
    if pid == 0:
        os.execv(command[0], command)

    stopping = False

    def forward(signum: int, _frame) -> None:
        nonlocal stopping
        stopping = True
        try:
            os.killpg(pid, signum)
        except ProcessLookupError:
            pass

    signal.signal(signal.SIGTERM, forward)
    signal.signal(signal.SIGINT, forward)

    with log_path.open("ab", buffering=0) as log:
        while True:
            try:
                chunk = os.read(master_fd, 65536)
            except OSError:
                chunk = b""
            if not chunk:
                break
            log.write(chunk)
            if stopping:
                # Continue draining until RootStart performs its own teardown.
                continue

    _, status = os.waitpid(pid, 0)
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
