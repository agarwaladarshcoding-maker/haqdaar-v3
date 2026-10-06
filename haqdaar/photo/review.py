"""M6: what is kept when a person answers a held SMS photo. Words only: no picture, no phone number."""
import json
import os
import time
from pathlib import Path
from typing import Any, Optional


def labels_path() -> Path:
    return Path(os.environ.get("REVIEW_LABELS_FILE", "logs/review_labels.jsonl"))


def _norm(text: str) -> str:
    return " ".join(str(text or "").split()).lower()


def write_label(info: dict[str, Any], model_say: str, answer: str, kind: str) -> bool:
    """One line for one answered case. False (never raises) when it could not be written."""
    line = {
        "t": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kind": kind,                                   # approve | not_clear
        "same": kind == "approve" and _norm(model_say) == _norm(answer),
        "model": str(model_say or "")[:300],
        "answer": str(answer or "")[:300],
        "widths": [int(w) for w in info.get("widths", [])],
        "sent": info.get("sent"), "whole": info.get("whole"),
        "sure": info.get("sure"), "reasons": list(info.get("reasons", [])),
    }
    try:
        path = labels_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


def counts(path: Optional[Path] = None) -> dict[int, dict[str, int]]:
    """Per narrowest picture width: how many cases a person answered, and how many of them agreed with the model."""
    out: dict[int, dict[str, int]] = {}
    p = Path(path) if path else labels_path()
    if not p.exists():
        return out
    for raw in p.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        w = min(row.get("widths") or [0])
        c = out.setdefault(int(w), {"n": 0, "same": 0})
        c["n"] += 1
        c["same"] += 1 if row.get("same") else 0
    return out
