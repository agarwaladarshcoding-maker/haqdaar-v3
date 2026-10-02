"""haqdaar/data/trace.py

The timed story of one call, for the call page (`make calls-ui`).

The call LOG (T16) holds what the engine decided, and it carries no clock. The trace sits
beside it: every event line the server already prints ("-> say ...", "<- key ...") and a copy
of every LOG record, each with the seconds since the call started.

File: <logs_dir>/trace/<call_id>.jsonl, one JSON object per line:
    {"t": 0.0, "start": "<call_id>", "at": "2026-10-02T23:50:01", "snapshot": "<snapshot_id>"}
    {"t": 1.204, "line": "-> say greeting_trilingual (9.8 s)"}
    {"t": 12.9, "log": {"turn_n": 0, "class": "ANSWER", "transcript": "hi"}}

A trace never raises: a lost line is bad, a dead call is worse.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

TRACE_DIR = "trace"


class Trace:
    def __init__(self, call_id: str, logs_dir: Path | str, snapshot_id: str = "",
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._t0 = clock()
        self._lock = threading.Lock()
        self._file = None
        try:
            folder = Path(logs_dir) / TRACE_DIR
            folder.mkdir(parents=True, exist_ok=True)
            self._file = open(folder / f"{call_id}.jsonl", "a", encoding="utf-8")
        except Exception:
            pass
        self._write({"start": call_id, "at": datetime.now().isoformat(timespec="seconds"),
                     "snapshot": snapshot_id})

    def __call__(self, line: str) -> None:
        """One event line, as the server prints it."""
        self._write({"line": line})

    def record(self, rec: dict[str, Any]) -> None:
        """A copy of one LOG record."""
        self._write({"log": rec})

    def close(self) -> None:
        with self._lock:
            try:
                if self._file is not None:
                    self._file.close()
            except Exception:
                pass
            self._file = None

    def _write(self, row: dict[str, Any]) -> None:
        with self._lock:
            if self._file is None:
                return
            try:
                row = {"t": round(self._clock() - self._t0, 3), **row}
                self._file.write(json.dumps(row, ensure_ascii=False) + "\n")
                self._file.flush()
            except Exception:
                pass
