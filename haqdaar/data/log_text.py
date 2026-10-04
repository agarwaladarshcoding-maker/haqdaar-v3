"""haqdaar/data/log_text.py

The words behind a call's log, so a person (and later the model) can read the call as text.

Two parts:
- `lookup(snapshot_id)`: token -> the words the caller heard, in a language or in English. Built
  from the same pipeline texts the call viewer uses (lines, chips, bands, keys, scheme chunks),
  once per snapshot. A token it does not know gives "", never an error.
- `log_text(rows, max_chars)`: the call's log rows as short English lines, oldest first. Pure:
  no files, no model.
Nothing here may raise into a call: the engine calls `said_words` while the caller is on the line.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from haqdaar.contracts import tunables

Lookup = Callable[[str, str], str]

_TABLES: dict[tuple[str, str], dict[tuple[str, str], str]] = {}  # (folder, snapshot) -> (ref, lang) -> text
LINE_CHARS = 240  # one line of the short text; a scheme chunk is far longer than this
_NOT_SPEECH = ("name:", "end:")  # engine marks, not speech


def _table(snapshot_id: str, snapshots_dir: Path | str | None = None) -> dict[tuple[str, str], str]:
    folder = Path(snapshots_dir or tunables.SNAPSHOTS_DIR)
    key = (str(folder), snapshot_id)
    if key not in _TABLES:
        from haqdaar.data.pipeline.texts import all_texts  # lazy: the pipeline is not needed by a call that never says anything

        schemes: list[dict[str, Any]] = []
        bands: dict[str, Any] = {}
        try:  # a sim on the test fixture has no snapshot on disk: the fixed lines still resolve
            snap = folder / snapshot_id
            schemes = [json.loads(x) for x in (snap / "schemes.jsonl").read_text("utf-8").splitlines() if x.strip()]
            boxes = json.loads((snap / "vocab.json").read_text("utf-8")).get("boxes", {})
            bands = {box: meta["bands"] for box, meta in boxes.items() if "bands" in meta}
        except Exception:
            pass
        try:
            _TABLES[key] = {(t.ref, t.lang): t.text for t in all_texts(schemes, bands)}
        except Exception:
            _TABLES[key] = {}
    return _TABLES[key]


def lookup(snapshot_id: str, snapshots_dir: Path | str | None = None) -> Lookup:
    """token, lang -> text. "" when the token has no text in that language."""
    try:
        table = _table(snapshot_id, snapshots_dir)
    except Exception:
        table = {}

    def find(token: str, lang: str) -> str:
        if token.startswith("scheme:"):
            token = "/".join(token.split(":", 2)[1:])
        return table.get((token, lang)) or table.get((token, "all")) or ""

    return find


def _menu_box() -> dict[str, str]:
    from haqdaar.audio.phone import MENU_BOX  # the audio owns which prompt brings which menu

    return MENU_BOX


def said_words(tokens: Iterable[str], lang: str, find: Lookup, corpus: Any = None) -> str:
    """What the caller heard for these tokens, in `lang`. A prompt that brings a key menu gets the
    list too ("press 1 for ..."). Never raises."""
    try:
        parts: list[str] = []
        for token in tokens:
            if token.startswith(_NOT_SPEECH):
                continue
            text = find(token, lang)
            if text:
                parts.append(text)
            box = _menu_box().get(token)
            if box and corpus is not None:
                items = []
                for n, value in enumerate(corpus.values(box), start=1):
                    chip = find(f"chip_{box}_{value}", lang)
                    if chip:
                        items.append(f"press {n} for {chip}")
                suffix = find("keypad_unknown_suffix", lang)
                parts.append(", ".join(items) + (f". {suffix}" if suffix else ""))
        return " ".join(p for p in parts if p)
    except Exception:
        return ""


# --- rows -> short text --------------------------------------------------------------

def _cut(text: str, n: int = LINE_CHARS) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def _line(row: dict[str, Any], answer_said: bool) -> Optional[str]:
    ev = row.get("ev")
    if ev == "said":
        words = row.get("en") or row.get("text") or ", ".join(row.get("tokens") or [])
        return f'AGENT: "{_cut(words)}"'
    if ev == "key":
        means = row.get("means")
        return f"CALLER pressed {row.get('key')}" + (f" ({means})" if means else "")
    if ev == "cut":
        what = f' "{_cut(row["en"], 80)}"' if row.get("en") else f" {row.get('clip', '')}"
        return f"CALLER cut in by {row.get('by')} during{what} after {row.get('heard_ms')} ms"
    if ev == "blocked":
        return f'ANSWER REFUSED ({row.get("rule")}): asked "{_cut(row.get("question", ""), 120)}", refused "{_cut(row.get("text", ""), 120)}"'
    if ev is not None:
        return None
    cls = row.get("class")
    n = row.get("turn_n")
    if cls == "ANSWER":
        if row.get("box"):
            return f"TURN {n}: answer {row['box']} = {row.get('value')}"
        return f"TURN {n}: language chosen {row.get('transcript')}"
    if cls == "PROPOSAL":
        return f"TURN {n}: heard {row.get('box')} = {row.get('value')}, asked to confirm"
    if cls == "QUESTION":
        said = f'CALLER asked: "{_cut(row.get("transcript", ""), 120)}"'
        return said if answer_said else said + f'\nAGENT answered: "{_cut(row.get("answer", ""))}"'
    if cls in ("UNCLEAR", "NOISE"):
        heard = row.get("discarded_transcript") or row.get("transcript")
        return f"TURN {n}: not understood" + (f' ("{_cut(heard, 80)}")' if heard else "")
    if cls == "SILENCE":
        return f"CALLER silent (silence {row.get('silence_n')})"
    if "slug" in row:
        return f"READ OUT: {row['slug']} ({row.get('ending')}; {', '.join(row.get('sections') or [])})"
    if "stop" in row:
        return f"CALL ENDED: {row['stop']}, mode {row.get('mode')}"
    if "lang" in row and "call_id" not in row:
        return f"LANGUAGE: {row['lang']} ({row.get('lang_source')})"
    if "call_id" in row:
        return f"CALL STARTED: {row['call_id']}"
    if "opener_menu" in row:
        return f"KEY LIST played ({row['opener_menu']})"
    if "mode" in row:
        return f"MODE: {row['mode']}"
    return None


def log_text(rows: Iterable[dict[str, Any]], max_chars: int = 0) -> str:
    """The call as one short English line per event, oldest first. Over `max_chars` (0 = no cap),
    the OLDEST lines go and the newest stay. Pure."""
    rows = [r for r in rows if isinstance(r, dict)]
    answer_said = any(r.get("ev") == "said" and r.get("tokens") == ["answer"] for r in rows)
    lines = [x for x in (_line(r, answer_said) for r in rows) if x]
    if max_chars and max_chars > 0:
        while len(lines) > 1 and len("\n".join(lines)) > max_chars:
            lines.pop(0)
        if lines and len(lines[0]) > max_chars:
            lines[0] = lines[0][-max_chars:]
    return "\n".join(lines)


def read_rows(path: Path | str) -> list[dict[str, Any]]:
    """The rows of one call log file. A half-written last line is skipped."""
    rows: list[dict[str, Any]] = []
    for raw in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(raw)
        except Exception:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows

