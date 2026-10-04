"""haqdaar/data/answer_store.py

Step 7.3: saved answers. A JSON-lines file in REPORTS_DIR, one line per answer that passed
every check. The key holds the snapshot id, so a new snapshot never serves an old answer.
Loaded once per process. Never raises: a bad file or line is just a miss.
"""
from __future__ import annotations

import json
from pathlib import Path
import unicodedata
from typing import Optional, Sequence

from haqdaar.contracts import tunables

BASE_DIR = Path(__file__).resolve().parent.parent.parent
_FILE = "saved_answers.jsonl"

_cache: dict[Path, dict[str, str]] = {}


def _path() -> Path:
    return BASE_DIR / tunables.REPORTS_DIR / _FILE


def _norm(question: str) -> str:
    kept = "".join(" " if unicodedata.category(c)[0] in "PS" else c for c in question.lower())
    return " ".join(kept.split())


def make_key(snapshot_id: str, lang: str, scheme_ids: Sequence[str], question: str) -> str:
    return "|".join((snapshot_id, lang, ",".join(sorted(scheme_ids)), _norm(question)))


def _load(path: Path) -> dict[str, str]:
    if path not in _cache:
        rows: dict[str, str] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        row = json.loads(line)
                        rows[str(row["key"])] = str(row["answer"])
                    except (ValueError, KeyError, TypeError):
                        continue
        except OSError:
            pass
        _cache[path] = rows
    return _cache[path]


def get(key: str) -> Optional[str]:
    try:
        return _load(_path()).get(key)
    except Exception:
        return None


def put(key: str, answer: str) -> None:
    try:
        path = _path()
        rows = _load(path)
        if rows.get(key) == answer:
            return
        rows[key] = answer
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "answer": answer}, ensure_ascii=False) + "\n")
    except Exception:
        pass
