"""haqdaar/data/scheme_search.py

Step 7.3: pick the schemes a caller's question is about by plain word overlap with each
scheme's card. Stdlib only, no embeddings, no index on disk. Never raises.
"""
from __future__ import annotations

import unicodedata
from typing import Mapping

MIN_SHARED_WORDS = 2

# Words that show up in almost every question or card and say nothing about which scheme.
_STOP: frozenset[str] = frozenset("""
the and for are you your with that this what how can does will who which from have has not any
about get got need want tell give scheme schemes yojana please also into than then them they
their there when where why would should could may might must only some such very more most
mujhe mera meri kya kaise kitna kitni hai hain ke ki ka ko se me mein par aur ya bhi koi
मुझे मेरा मेरी क्या कैसे कितना कितनी है हैं के की का को से में पर और या भी कोई योजना
""".split())


def _words(text: str) -> set[str]:
    # Devanagari vowel signs are not \w, so cut on punctuation/symbol categories instead.
    cleaned = "".join(" " if unicodedata.category(c)[0] in "PSZC" else c.lower() for c in text)
    return {w for w in cleaned.split() if len(w) >= 3 and w not in _STOP}


def find_schemes(question: str, cards: Mapping[str, str], k: int) -> list[str]:
    """Up to `k` scheme ids whose card shares at least MIN_SHARED_WORDS content words with
    the question, best first (ties keep the order of `cards`). [] when none does."""
    try:
        q = _words(question)
        if not q or k <= 0:
            return []
        scored: list[tuple[int, int, str]] = []
        for pos, (sid, card) in enumerate(cards.items()):
            # Drop the "[id]" line and each "field:" label; only the card's own words count.
            body = " ".join(line.split(": ", 1)[-1] for line in (card or "").splitlines()[1:])
            n = len(q & _words(body))
            if n >= MIN_SHARED_WORDS:
                scored.append((-n, pos, sid))
        scored.sort()
        return [sid for _, _, sid in scored[:k]]
    except Exception:
        return []
