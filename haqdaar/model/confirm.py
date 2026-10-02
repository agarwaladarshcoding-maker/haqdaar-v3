"""haqdaar/model/confirm.py

Spoken confirmation matcher for HAQDAAR v2.
T09: Model owns language.
Matches caller affirmative / rejection utterances across Hindi, Marathi, and English.
"""
from __future__ import annotations

import re
from typing import Optional

CONFIRM_YES_TOKENS: dict[str, tuple[str, ...]] = {
    "en": ("1", "yes", "yeah", "yep", "correct", "right", "sure", "true", "ok", "okay"),
    "hi": ("1", "haan", "ha", "sahi", "sahi hai", "theek", "theek hai", "ji haan", "ha ji"),
    "mr": ("1", "ho", "hoy", "barobar", "khare", "barobar aahe", "nakkich", "chalel"),
}

CONFIRM_NO_TOKENS: dict[str, tuple[str, ...]] = {
    "en": ("2", "no", "nope", "wrong", "incorrect", "fix", "change", "not this"),
    "hi": ("2", "nahi", "na", "galat", "galat hai", "badlo", "nahin", "nahi hai"),
    "mr": ("2", "nahi", "naahi", "chuki", "chuki che", "badla", "nako"),
}

ALL_YES_TOKENS: frozenset[str] = frozenset(
    token for tokens in CONFIRM_YES_TOKENS.values() for token in tokens
)
ALL_NO_TOKENS: frozenset[str] = frozenset(
    token for tokens in CONFIRM_NO_TOKENS.values() for token in tokens
)


def match_confirm(text: str, lang: Optional[str] = None) -> Optional[bool]:
    """Classify a confirmation utterance as True (accept), False (reject), or None (unclear).

    Checks the specified language tokens first, and falls back to cross-language tokens.
    """
    if not text:
        return None
    cleaned = re.sub(r"[^\w\s]", " ", text.strip().lower())
    norm = " ".join(cleaned.split())
    if not norm:
        return None

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
