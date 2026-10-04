"""haqdaar/model/confirm.py

Spoken confirmation matcher for HAQDAAR v2.
T09: Model owns language.
Matches caller affirmative / rejection utterances across Hindi, Marathi, and English.
"""
from __future__ import annotations

import unicodedata
from typing import Optional

CONFIRM_YES_TOKENS: dict[str, tuple[str, ...]] = {
    "en": ("1", "yes", "yeah", "yep", "correct", "right", "sure", "true", "ok", "okay"),
    "hi": ("1", "haan", "ha", "sahi", "sahi hai", "theek", "theek hai", "ji haan", "ha ji",
           "हाँ", "हां", "जी हाँ", "जी हां", "सही", "सही है", "ठीक", "ठीक है"),
    "mr": ("1", "ho", "hoy", "barobar", "khare", "barobar aahe", "nakkich", "chalel",
           "हो", "होय", "बरोबर", "बरोबर आहे", "खरे", "नक्की", "चालेल"),
}

CONFIRM_NO_TOKENS: dict[str, tuple[str, ...]] = {
    "en": ("2", "no", "nope", "wrong", "incorrect", "fix", "change", "not this"),
    "hi": ("2", "nahi", "na", "galat", "galat hai", "badlo", "nahin", "nahi hai",
           "नहीं", "नही", "ना", "गलत", "गलत है", "बदलो"),
    "mr": ("2", "nahi", "naahi", "chuki", "chuki che", "badla", "nako",
           "नाही", "नको", "चुकीचे", "बदला"),
}

# Common words in the other language: "हो" is Hindi "are", "ना" is a Hindi filler. They count only
# as the whole utterance in their own language, never as one word inside a longer sentence.
_OWN_LANG_ONLY: frozenset[str] = frozenset(("हो", "ना"))

ALL_YES_TOKENS: frozenset[str] = frozenset(
    token for tokens in CONFIRM_YES_TOKENS.values() for token in tokens
) - _OWN_LANG_ONLY
ALL_NO_TOKENS: frozenset[str] = frozenset(
    token for tokens in CONFIRM_NO_TOKENS.values() for token in tokens
) - _OWN_LANG_ONLY


def _normalise(text: str) -> str:
    """Lower-case and blank out punctuation. Devanagari vowel signs are not \\w to `re`, so a
    regex clean-up would cut "हाँ" into pieces; test the Unicode category instead."""
    cleaned = "".join(
        " " if unicodedata.category(c)[0] in "PS" else c
        for c in unicodedata.normalize("NFC", text.strip().lower())
    )
    return " ".join(cleaned.split())


def _match_words(norm: str, yes: frozenset[str], no: frozenset[str]) -> Optional[bool]:
    if norm in yes:
        return True
    if norm in no:
        return False
    words = norm.split()
    if any(w in yes for w in words) and not any(w in no for w in words):
        return True
    if any(w in no for w in words) and not any(w in yes for w in words):
        return False
    return None


def match_confirm(text: str, lang: Optional[str] = None, english: bool = False) -> Optional[bool]:
    """Classify a confirmation utterance as True (accept), False (reject), or None (unclear).

    Checks the specified language tokens first, and falls back to cross-language tokens.
    When `english` is True the text is an English translation of the speech: the English
    list goes first, then everything above.
    """
    if not text:
        return None
    norm = _normalise(text)
    if not norm:
        return None

    if english:
        en_hit = _match_words(norm, frozenset(CONFIRM_YES_TOKENS["en"]), frozenset(CONFIRM_NO_TOKENS["en"]))
        if en_hit is not None:
            return en_hit

    # 1. Exact match in target language
    if lang and lang in CONFIRM_YES_TOKENS:
        if norm in CONFIRM_YES_TOKENS[lang] or any(norm == t for t in CONFIRM_YES_TOKENS[lang]):
            return True
        if norm in CONFIRM_NO_TOKENS[lang] or any(norm == t for t in CONFIRM_NO_TOKENS[lang]):
            return False

    # 2. Exact match across all languages
    if norm in ALL_YES_TOKENS:
        return True
    if norm in ALL_NO_TOKENS:
        return False

    # 3. Check individual tokens / words if multi-word utterance
    words = norm.split()
    if any(w in ALL_YES_TOKENS for w in words) and not any(w in ALL_NO_TOKENS for w in words):
        return True
    if any(w in ALL_NO_TOKENS for w in words) and not any(w in ALL_YES_TOKENS for w in words):
        return False

    return None
