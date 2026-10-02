"""tools/keep_running.py

Plan 5.3: `make run` restarts the server after a crash.

    python -m tools.keep_running <command ...>

Runs the command; when it stops for any reason other than the owner's Ctrl-C, waits
RESTART_WAIT_S and runs it again. A server that keeps dying at once (a bad import, a busy
port) is not restarted for ever: RESTART_MAX_STOPS stops inside RESTART_WINDOW_S and it
gives up with exit code 1. One caller at a time: a restart drops the live call, nothing else.
"""
from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from haqdaar.contracts import tunables


def _say(text: str) -> None:
    print(f"keep_running: {text}", flush=True)


def _run(cmd: Sequence[str]) -> int:
    """Run the server and wait. If we are told to stop, the server is stopped too, never orphaned."""
    proc = subprocess.Popen(cmd)
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()  # harmless when Ctrl-C already reached it
        proc.wait()
        raise


def _stop(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt()


def keep_running(
    cmd: Sequence[str],
    run: Callable[[Sequence[str]], int] = _run,
    sleep: Callable[[float], Any] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    say: Callable[[str], Any] = _say,
) -> int:
    stops: list[float] = []
    while True:
        try:
            code = run(cmd)
            now = clock()
            stops = [t for t in stops if now - t < tunables.RESTART_WINDOW_S] + [now]
            if len(stops) >= tunables.RESTART_MAX_STOPS:
                say(
                    f"server stopped {len(stops)} times in {tunables.RESTART_WINDOW_S:.0f} s "
                    f"(last exit code {code}); giving up. Read logs/server.log."
                )
                return 1
            say(f"server stopped (exit code {code}); starting it again in {tunables.RESTART_WAIT_S:.0f} s")
            sleep(tunables.RESTART_WAIT_S)
        except KeyboardInterrupt:
            say("stopped by the owner (Ctrl-C or kill); not restarting")
            return 0


def main(argv: Sequence[str] | None = None) -> int:
    cmd = list(sys.argv[1:] if argv is None else argv)
    if not cmd:
        print("usage: python -m tools.keep_running <command ...>", file=sys.stderr)
        return 2
    # `kill` on this process and Ctrl-C mean the same thing: stop, and do not restart.
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    return keep_running(cmd)


if __name__ == "__main__":
    sys.exit(main())
