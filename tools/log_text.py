"""tools/log_text.py

`python -m tools.log_text <call id or file>` (or `make log-text ID=<call id>`): prints one call's
log as short English text, one line per event, oldest first. It only reads the file.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from haqdaar.contracts import tunables
from haqdaar.data.log_text import log_text, read_rows


def find_log(target: str) -> Path | None:
    """A file path, or a call id looked up in the call log folders."""
    path = Path(target)
    if path.is_file():
        return path
    for folder in (tunables.CALL_LOGS_DIR, "logs", "logs/calls"):
        found = Path(folder) / f"{target}.jsonl"
        if found.is_file():
            return found
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Print one call's log as short text.")
    parser.add_argument("call", help="a call id or the path of a call log file")
    parser.add_argument("--max-chars", type=int, default=0, help="keep only the newest lines that fit (0 = all)")
    args = parser.parse_args()
    path = find_log(args.call)
    if path is None:
        print(f"no call log found for {args.call!r}", file=sys.stderr)
        return 1
    print(log_text(read_rows(path), max_chars=args.max_chars, times=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
