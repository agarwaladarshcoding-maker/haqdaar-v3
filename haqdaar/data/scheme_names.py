"""haqdaar/data/scheme_names.py

Step 1.3a: the names people SAY for each scheme (short forms, letters, Hindi
and Latin), and the well-known schemes we do NOT hold.

The snapshot rows carry the written names + aliases; what callers actually say
("मनरेगा", "केसीसी", "pm awas") is often shorter than those, and the name
match scores a short sentence against a long name low. So each scheme carries
its short names here, next to the scheme data: the name search reads them by
scheme id, so 100 schemes can carry theirs the same way.
Step 1.3b: the lists live in fixtures/scheme_short_names.json (fixtures, not
the snapshot folder: one source for every snapshot, always on disk for tests,
no snapshot-version copies to keep in step). This module stays the only reader.
Pure: no model; the one file read happens at import.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


def _load() -> dict:
    try:
        path = Path(__file__).resolve().parents[2] / "fixtures" / "scheme_short_names.json"
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_DATA = _load()

# scheme id -> short spoken forms (bare names, letters, Hindi and Latin).
SHORT_NAMES: dict[str, tuple[str, ...]] = {
    key: tuple(names) for key, names in _DATA.get("short_names", {}).items()}

# Well-known schemes we do NOT hold: canonical id -> words that name it.
# A turn naming one of these is its own kind of turn ("I do not have that one
# yet"), not a situation to ask questions about. Kept here, next to SHORT_NAMES.
NOT_HELD: dict[str, tuple[str, ...]] = {
    key: tuple(names) for key, names in _DATA.get("not_held", {}).items()}

# A short name that is also a common word ("मुद्रा", "आजीविका"): it only names
# its scheme with योजना / लोन / scheme / loan next to it.
NEEDS_MARKER: tuple[str, ...] = tuple(_DATA.get("needs_marker", ()))
MARKERS: tuple[str, ...] = ("योजना", "लोन", "scheme", "schemes", "loan", "loans")

_ASCII_WORD = re.compile(r"^[a-z ]+$")
_DEVA = r"\u0900-\u097F"
# Vowel signs (matras) are marks, not letters: `\w` drops them, which cut
# "केसीसी" and "किसी से" to the same bare letters. They stay in the words.
_PUNCT = re.compile(r"[^\w\s\u0900-\u097F]", re.UNICODE)
_SAME = str.maketrans({"\u0901": "\u0902", "\u200c": None, "\u200d": None, "\u093c": None})


def _norm(text: str) -> str:
    """Same cut as the name search: punctuation out, lowercased, words apart.
    Vowel signs kept; nukta, chandrabindu and ZWJ/ZWNJ spellings made equal."""
    text = str(text).lower().translate(_SAME)
    return " ".join(_PUNCT.sub(" ", text).split())


def norm(text: str) -> str:
    return _norm(text)


def needs_marker(name: str) -> bool:
    """A normalized name that is also a common word: no match without a marker."""
    return _norm(name) in {_norm(w) for w in NEEDS_MARKER}


def has_marker(query_words: list[str]) -> bool:
    """A योजना / लोन / scheme / loan word standing whole in the query words."""
    for marker in MARKERS:
        seq = _norm(marker).split()
        if any(query_words[i:i + len(seq)] == seq
               for i in range(len(query_words) - len(seq) + 1)):
            return True
    return False


def short_names_for(scheme_id: str) -> tuple[str, ...]:
    """The short spoken forms of one scheme, () when it carries none."""
    return SHORT_NAMES.get(str(scheme_id), ())


def contains_word(text: str, word: str) -> bool:
    """The word in the text, not inside a longer word of the same script."""
    if _ASCII_WORD.match(word):
        return re.search(rf"\b{re.escape(word)}\b", text) is not None
    return re.search(rf"(?<![{_DEVA}]){re.escape(word)}(?![{_DEVA}])", text) is not None


def _has(text: str, word: str) -> bool:
    return contains_word(text, word)


def find_not_held(text: str) -> str:
    """The not-held scheme the caller's words name, or "".

    At most one can match: these are four different schemes, and a turn naming
    two of them is answered about the first one named.
    """
    lowered = " " + str(text).lower() + " "
    for key, words in NOT_HELD.items():
        if any(_has(lowered, w) for w in words):
            return key
    return ""
