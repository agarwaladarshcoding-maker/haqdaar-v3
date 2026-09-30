"""haqdaar/audio/lines.py

Step 1.13 (plan 1.11) — read the fixed lines.

`lines.yaml` holds the English of every fixed line. Hindi and Marathi arrive later, through
the same p4/p5 path as the scheme cards, and are written back into the same file. This module
is the only way the rest of the code reads that file, so there is one place that knows its
shape and one place that checks it.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from haqdaar.contracts.types import FIXED_LINE_IDS

LINES_PATH = Path(__file__).with_name("lines.yaml")

# greeting_trilingual is one recording that plays Hindi, then Marathi, then English, so it is
# the one line that is not per-language. p6_snapshot gives it the "all" render key.
TRILINGUAL_LINE_ID = "greeting_trilingual"


@lru_cache(maxsize=None)
def load_lines(path: Path | str | None = None) -> dict[str, dict[str, str]]:
    """{line_id: {lang: text}} for every fixed line.

    Raises ValueError if the file and FIXED_LINE_IDS disagree, because a line that exists in
    one and not the other is an id nobody can render or an id nobody will ever speak.
    """
    path = Path(path) if path is not None else LINES_PATH
    with open(path, "r", encoding="utf-8") as f:
        data: Any = yaml.safe_load(f) or {}

    lines = data.get("lines") or {}
    if not isinstance(lines, dict):
        raise ValueError(f"{path}: 'lines' must be a mapping")

    expected = set(FIXED_LINE_IDS)
    found = set(lines)
    missing = sorted(expected - found)
    extra = sorted(found - expected)
    if missing:
        raise ValueError(f"{path}: missing fixed lines: {', '.join(missing)}")
    if extra:
        raise ValueError(f"{path}: unknown line ids: {', '.join(extra)}")

    out: dict[str, dict[str, str]] = {}
    for line_id, value in lines.items():
        if not isinstance(value, dict):
            raise ValueError(f"{path}: {line_id} must be a mapping of language to text")
        texts = {
            lang: str(text).strip()
            for lang, text in value.items()
            if lang != "pinned" and str(text).strip()
        }
        if not texts.get("en"):
            raise ValueError(f"{path}: {line_id} has no English text")
        out[line_id] = texts
    return out


def line_text(line_id: str, lang: str, path: Path | str | None = None) -> str:
    """One line in one language, falling back to English while hi/mr are still being filled.

    The fallback is deliberate and loud at the edges: an English line played into a Hindi call
    is wrong, but silence is worse, and `untranslated()` is what the build gate reads.
    """
    texts = load_lines(path)[line_id]
    return texts.get(lang) or texts["en"]


# Band labels are built from a template, not written out, because the bands themselves are
# built per snapshot from whatever the corpus constrains (p6_snapshot.build_range_bands). There
# is no fixed list of ages or incomes to author, and a hand-written label would go stale the
# moment a scheme changes. Only the open top band and the closed band differ, so two templates
# per box per language cover every band the snapshot can produce.
BAND_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "age": {
        "en": {"closed": "{lo} to {hi} years", "open": "{lo} years and above"},
        "hi": {"closed": "{lo} से {hi} साल", "open": "{lo} साल और उससे ऊपर"},
        "mr": {"closed": "{lo} ते {hi} वर्षे", "open": "{lo} वर्षे आणि त्याहून अधिक"},
    },
    "income_band": {
        "en": {
            "closed": "{lo} to {hi} rupees a year",
            "open": "{lo} rupees a year and above",
        },
        "hi": {
            "closed": "{lo} से {hi} रुपये साल में",
            "open": "{lo} रुपये साल में और उससे ऊपर",
        },
        "mr": {
            "closed": "{lo} ते {hi} रुपये वर्षाला",
            "open": "{lo} रुपये वर्षाला आणि त्याहून अधिक",
        },
    },
}


def band_label(box: str, lo: int, hi: int | None, lang: str = "en") -> str:
    """Speak one keypad band, e.g. "18 to 40 years" or "60 years and above".

    `hi=None` is the open top band the snapshot always ends with.
    """
    try:
        templates = BAND_TEMPLATES[box]
    except KeyError:
        raise ValueError(f"no band template for box {box!r}") from None
    shapes = templates.get(lang) or templates["en"]
    if hi is None:
        return shapes["open"].format(lo=lo)
    return shapes["closed"].format(lo=lo, hi=hi)


# After each chip in a keypad menu: "Farmer — press 1." One short clip per key per language
# (27 in all) instead of one per chip per position, so the menu can be any order or length.
KEY_TEMPLATES: dict[str, str] = {
    "en": "press {n}.",
    "hi": "{n} दबाएँ।",
    "mr": "{n} दाबा.",
}
MENU_KEYS: tuple[int, ...] = tuple(range(1, 10))


def key_label(n: int, lang: str = "en") -> str:
    return (KEY_TEMPLATES.get(lang) or KEY_TEMPLATES["en"]).format(n=n)


def untranslated(path: Path | str | None = None) -> list[tuple[str, str]]:
    """Every (line_id, lang) that still has no text. Empty once p4 has run over the lines."""
    missing: list[tuple[str, str]] = []
    for line_id, texts in load_lines(path).items():
        if line_id == TRILINGUAL_LINE_ID:
            continue  # one recording, already all three languages
        for lang in ("hi", "mr"):
            if not texts.get(lang):
                missing.append((line_id, lang))
    return missing
