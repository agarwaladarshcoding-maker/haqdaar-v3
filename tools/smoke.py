"""tools/smoke.py

Plan 5.3: `make smoke` prints the checklist to run before a real call or a demo.

The first part is checked here, offline and free (no key is ever printed, only its name).
The second part is by hand: it needs a real phone, so the owner ticks it.
Exit code 1 when a checked item fails.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import dotenv_values

from haqdaar.data.corpus import Corpus
from haqdaar.data.pipeline import muse

SET_BY_MAKE_RUN = {"NGROK_DOMAIN"}  # `make run` fills this from the live tunnel

BY_HAND = (
    "`make run` is up: logs/server.log shows the tunnel address and no error",
    "Call the number: the greeting starts in about 2 s, with no trial notice cutting it",
    "Press 1 / 2 / 3: the language changes, and the first question plays",
    "Finish one keypad call: a scheme is read, then the goodbye, then it hangs up",
    "Finish one spoken call: it repeats your answer and asks you to press 1",
    "Say a scheme's name at the opener: that scheme is read in under 20 s",
    "Drill 1, Wi-Fi dies mid-call: the call ends, the server stays up, the next call works",
    "Drill 2, the process is killed (`pkill -f uvicorn`): it is back in a few seconds, the next call works",
    "Drill 3, 30 minutes idle: the next call is answered as fast as the first",
    "After the calls: `make calls` shows no provider warning; `python tools/judge.py logs/` says PASS",
)


def _check_python() -> str:
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError(f"python is {sys.version_info.major}.{sys.version_info.minor}, the runtime is pinned to 3.11")
    return "python 3.11"


def _check_snapshot() -> str:
    corpus = Corpus.load("CURRENT")  # raises if any clip the snapshot names is missing or corrupt
    return f"snapshot {corpus.snapshot_id} loads, every clip it names is on disk"


def _check_keys(base_dir: Path = BASE_DIR) -> str:
    example = base_dir / ".env.example"
    names = [n for n in dotenv_values(example) if n not in SET_BY_MAKE_RUN]
    have = {k for k, v in dotenv_values(base_dir / ".env").items() if v}
    missing = [n for n in names if n not in have and not os.environ.get(n)]
    if missing:
        raise RuntimeError(f"keys not set in .env: {', '.join(missing)}")
    return f"{len(names)} keys set in .env (names from .env.example)"


def _check_logs(base_dir: Path = BASE_DIR) -> str:
    logs = base_dir / "logs"
    logs.mkdir(exist_ok=True)
    if not os.access(logs, os.W_OK):
        raise RuntimeError("logs/ is not writable")
    return "logs/ is writable"


def _check_muse() -> str:
    today = muse.muse_day()
    state = "blocked" if muse.blocked_day() == today else "open"
    return f"Muse spend today ₹{muse.spent_today_inr():.2f}, {state} (a live call never uses Muse)"


CHECKS: tuple[Callable[[], str], ...] = (_check_python, _check_snapshot, _check_keys, _check_logs, _check_muse)


def run_smoke(checks: Sequence[Callable[[], str]] = CHECKS, say: Callable[[str], None] = print) -> int:
    failed = 0
    say("HAQDAAR smoke checklist")
    say("")
    say("Checked now (offline, free):")
    for check in checks:
        try:
            say(f"  [ok]   {check()}")
        except Exception as e:  # a failed check is a line on the sheet, never a traceback
            failed += 1
            say(f"  [FAIL] {e}")
    say("")
    say("By hand (owner, with a real phone):")
    for item in BY_HAND:
        say(f"  [ ] {item}")
    say("")
    say(f"{failed} checked item(s) failed." if failed else "All checked items are fine. The rest is by hand.")
    return 1 if failed else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    return run_smoke()


if __name__ == "__main__":
    sys.exit(main())
