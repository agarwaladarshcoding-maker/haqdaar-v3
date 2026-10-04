"""haqdaar/data/scheme_text.py

Scheme text for caller questions (step 7.1). Reads a snapshot's schemes.jsonl once and
hands out one plain-text card per scheme and language. Stdlib + contracts only.
Never raises: a missing file, bad line, unknown id or unknown language gives "".
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from haqdaar.contracts import tunables


class SchemeText:
    def __init__(self, rows: dict[str, dict[str, Any]]) -> None:
        self._rows = rows

    @classmethod
    def load(cls, snapshot_id: str) -> "SchemeText":
        snapshots_path = Path(tunables.SNAPSHOTS_DIR)
        rows: dict[str, dict[str, Any]] = {}
        try:
            if snapshot_id == "CURRENT":
                snapshot_id = (snapshots_path / "CURRENT").read_text(encoding="utf-8").strip()
            with open(snapshots_path / snapshot_id / "schemes.jsonl", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        rows[str(row["scheme_id"])] = row
                    except (ValueError, KeyError, TypeError):
                        continue
        except OSError:
            pass
        return cls(rows)

    def card(self, scheme_id: str, lang: str) -> str:
        """The six chunk fields plus the exclusion notes, as plain text."""
        try:
            row = self._rows.get(scheme_id)
            chunk = (row.get("chunks") or {}).get(lang) if row else None
            if not chunk:
                return ""
            lines = [f"[{scheme_id}]"]
            lines += [f"{k}: {v}" for k, v in chunk.items()]
            lines.append("exclusions: " + " ".join(row.get("gate_notes") or []))
            return "\n".join(lines)
        except Exception:
            return ""
