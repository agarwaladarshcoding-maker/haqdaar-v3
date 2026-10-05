"""haqdaar/engine/talk_kind.py

Step 1.3a: the kind of turn, by code. Four kinds, checked in this order:
  1. "held_scheme"   the caller names a scheme we hold (name match)
  2. "not_held_scheme" the caller names a well-known scheme we do not hold
  3. "question"      a straight question about the scheme in talk
  4. "situation"     anything else: clarify first, never answer first.
Pure: no model, no I/O.
"""
from __future__ import annotations

from typing import Any

from haqdaar.data import scheme_names

HELD_SCHEME = "held_scheme"
NOT_HELD_SCHEME = "not_held_scheme"
QUESTION = "question"
SITUATION = "situation"

# Words that make a turn a straight question (Hindi, Marathi, English).
# Plain auxiliaries ("is", "hai") are NOT here: "my husband was a farmer"
# is a situation, not a question.
QUESTION_WORDS: tuple[str, ...] = (
    "क्या", "कैसे", "कितना", "कितनी", "कितने", "कब", "कहाँ", "कहां", "कौन", "क्यों", "किस",
    "काय", "कसे", "किती", "कधी", "कुठे", "कोण", "का",
    "what", "how", "how much", "how many", "when", "where", "which", "who", "why",
)

def is_question(text: str) -> bool:
    """A straight question: a question mark, or a question word naming nothing else."""
    lowered = " " + str(text).lower() + " "
    if "?" in lowered:
        return True
    return any(scheme_names.contains_word(lowered, w) for w in QUESTION_WORDS)


def kind(text: str, index: Any) -> str:
    """The kind of this turn. `index` is the scheme search (only its name match counts)."""
    try:
        top = index.search(text, 1)
    except Exception:
        top = []
    if top and top[0].by == "name":
        return HELD_SCHEME
    if scheme_names.find_not_held(text):
        return NOT_HELD_SCHEME
    if is_question(text):
        return QUESTION
    return SITUATION
