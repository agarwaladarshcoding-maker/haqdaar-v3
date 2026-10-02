"""tools/muse_guard.py

The Muse money guard, in one place. Calls nothing paid; reads and writes two small files.

    python -m tools.muse_guard            show today's spend, the caps, and any block
    python -m tools.muse_guard block      refuse every Muse call for the rest of today
    python -m tools.muse_guard unblock    lift the block (owner's word only)

The rules themselves live in haqdaar/data/pipeline/muse.py (`_check_budget`), the one gate
every Muse call in this repo passes. This guard cannot see Muse used outside this repo.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from haqdaar.contracts import tunables
from haqdaar.data.pipeline import muse


def status(ledger_path: Optional[Path] = None) -> bool:
    """Print the state. True when a Muse call would be let through right now."""
    ledger = Path(ledger_path) if ledger_path is not None else muse.LEDGER
    today = muse.muse_day()
    spent_today = muse.spent_today_inr(ledger)
    spent_all = muse.spent_inr(ledger)
    blocked = muse.blocked_day(ledger) == today
    is_open = not blocked and spent_today < tunables.MUSE_DAILY_CAP_INR and spent_all < tunables.MUSE_CAP_INR
    print(f"Muse guard, spend day {today} (India time, rolls at {tunables.MUSE_DAY_START_HOUR_IST:02d}:00)")
    print(f"  today:    ₹{spent_today:.2f} / ₹{tunables.MUSE_DAILY_CAP_INR:.0f} daily cap")
    print(f"  all time: ₹{spent_all:.2f} / ₹{tunables.MUSE_CAP_INR:.0f} cap")
    print(f"  block:    {'ON for today' if blocked else 'off'}")
    print(f"  Muse is {'OPEN' if is_open else 'SHUT'}")
    return is_open


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Muse daily money guard")
    parser.add_argument("action", nargs="?", default="status", choices=["status", "block", "unblock"])
    parser.add_argument("--reason", default="owner: quota done for today")
    args = parser.parse_args(argv)

    if args.action == "block":
        day = muse.block_today(reason=args.reason)
        print(f"Muse blocked for {day}.")
    elif args.action == "unblock":
        muse.unblock()
        print("Muse block lifted.")
    status()
    return 0


if __name__ == "__main__":
    sys.exit(main())
