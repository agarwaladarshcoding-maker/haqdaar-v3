"""haqdaar/audio/lang_words.py

Step 7.5a — which language did the caller say? A plain lookup, no model call.

The greeting offers its languages by key (LANGS_OFFERED). A caller may say the language
instead: its name, or the number of its key. A language the greeting does not offer is never
picked. Anything that is not clearly one offered language gives None, and the engine asks for
a key again. A wrong pick is worse than a second ask.
"""
from __future__ import annotations

import re

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Lang

# Names the speech service may write, in Latin and Devanagari. Matched on the start of a word,
# so "मराठीत" (in Marathi) counts too. Every name is long enough that this cannot hit a common word.
NAMES: dict[Lang, tuple[str, ...]] = {
    "hi": ("hindi", "hindee", "हिंदी", "हिन्दी"),
    "mr": ("marathi", "marati", "मराठी"),
    "en": ("english", "inglish", "angrezi", "angrazi", "ingrezi", "अंग्रेजी", "अँग्रेजी", "इंग्रजी", "इंग्लिश", "इंग्लीश"),
}

# The key numbers, by position in LANGS_OFFERED. Only counted in a very short reply ("two",
# "number two", "दो दबाओ"): in a longer sentence "do" or "one" is an ordinary word.
NUMBERS: dict[str, tuple[str, ...]] = {
    "1": ("1", "one", "ek", "एक"),
    "2": ("2", "two", "don", "दो", "दोन"),
    "3": ("3", "three", "teen", "तीन"),
}
SHORT_REPLY_WORDS = 2

_NON_WORD = re.compile(r"[^\w\u0900-\u0963\u0966-\u097f]+")


def _plain(text: str) -> str:
    """Lower case, no nukta, chandrabindu as anusvara: "अंग्रेज़ी" and "अँग्रेजी" are one word."""
    return text.lower().replace("\u093c", "").replace("\u0901", "\u0902")


_STEMS = {lang: tuple(_plain(n) for n in names) for lang, names in NAMES.items()}


def language_from_words(text: str) -> Lang | None:
    """The one offered language `text` names, or None if it names none or more than one."""
    words = _NON_WORD.sub(" ", _plain(text)).split()
    keys = tunables.turn0_keys()
    found: set[str] = set()
    for word in words:
        for lang, stems in _STEMS.items():
            if word.startswith(stems):
                found.add(lang)
    if len(words) <= SHORT_REPLY_WORDS:
        for key, spoken in NUMBERS.items():
            if key in keys and any(w in spoken for w in words):
                found.add(keys[key])
    found &= set(keys.values())
    return found.pop() if len(found) == 1 else None
