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
    # The other Sarvam languages. Only an offered language is ever picked by its name; being here
    # lets a talk call follow a caller into it (1.2) and start a talk in it at the greeting.
    "bn": ("bengali", "bangla", "बंगाली", "বাংলা"),
    "gu": ("gujarati", "गुजराती", "ગુજરાતી"),
    "kn": ("kannada", "कन्नड़", "ಕನ್ನಡ"),
    "ml": ("malayalam", "मलयालम", "മലയാളം"),
    "od": ("odia", "oriya", "उड़िया", "ओड़िया", "ଓଡ଼ିଆ"),
    "pa": ("punjabi", "panjabi", "पंजाबी", "ਪੰਜਾਬੀ"),
    "ta": ("tamil", "तमिल", "தமிழ்"),
    "te": ("telugu", "तेलुगु", "తెలుగు"),
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


def languages_named(text: str) -> set[str]:
    """Every language `text` names by its name ("Hindi", "मराठीत"), offered at the greeting or not."""
    words = _NON_WORD.sub(" ", _plain(text)).split()
    return {lang for lang, stems in _STEMS.items() if any(w.startswith(stems) for w in words)}


# The code the speech service sends back ("hi-IN", "mr-IN", "en-IN"): the language of a caller who
# spoke at the greeting without naming one. Any Sarvam language in NAMES is kept; any other code,
# or none, is Hindi.
def language_from_code(code: str) -> Lang:
    lang = (code or "").strip().lower().split("-")[0]
    return lang if lang in NAMES else "hi"  # type: ignore[return-value]


# A caller who only says "hello?" or "haan?" is checking the line is alive. Not a need: no first
# words, and the talk's own short hello answers. Every word must be one of these.
BARE_GREETINGS = frozenset({
    "hello", "hallo", "helo", "hi", "hey", "haan", "han", "haa", "ha", "ji", "jee",
    "हैलो", "हेलो", "हलो", "हाय", "हां", "हाँ", "हा", "जी", "जि", "हांजी", "हाँजी", "होय", "हो",
})


_BARE = frozenset(_plain(g) for g in BARE_GREETINGS)


def is_bare_greeting(text: str) -> bool:
    words = _NON_WORD.sub(" ", _plain(text)).split()
    return bool(words) and all(w in _BARE for w in words)
