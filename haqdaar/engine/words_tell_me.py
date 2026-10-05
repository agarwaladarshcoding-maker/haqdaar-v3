"""haqdaar/engine/words_tell_me.py

Step 1.3a: "just tell me" in the caller's words. When the caller says this,
asking stops for the rest of the call; the 2 best schemes left are shown.
Hindi, Marathi, English. Pure: no model, no I/O.
"""
from __future__ import annotations

from types import SimpleNamespace

from haqdaar.engine import talk_words

# Every box value counts as allowed: only "is any need or work word said" matters.
_ANY = SimpleNamespace(values=lambda box: talk_words.WORDS.get(box, {}))

# The whole phrase must be in the turn (every entry has 2+ words, or a
# distinctive spelling, so a plain substring is enough).
# 1.3b: a plain "tell me about X" ("मुझे किसान योजना बता दो") is NOT here:
# only words that mean "stop asking, just tell me" stop the questions.
JUST_TELL_ME: tuple[str, ...] = (
    # Hindi
    "बस योजना बता दो",
    "बस बता दो",
    "बस बताइए",
    "सीधे बताइए",
    "bas bata do",
    "seedha batao",
    "सीधे बताओ",
    "सीधा बताओ",
    "सवाल मत पूछो",
    "बिना सवाल",
    # Marathi
    "फक्त योजना सांगा",
    "थेट सांगा",
    "सरळ सांगा",
    "प्रश्न विचारू नका",
    "प्रश्न नको",
    # English
    "just tell me",
    "tell me directly",
    "tell me straight",
    "just tell me the scheme",
    "no more questions",
    "don't ask",
    "dont ask",
    "do not ask",
    "skip the questions",
    "stop asking",
)


def is_just_tell_me(text: str) -> bool:
    """The caller wants the schemes now, no more questions."""
    lowered = " " + str(text).lower() + " "
    if any(phrase in lowered for phrase in JUST_TELL_ME):
        return True
    # Bare "tell me (a scheme)" only with no topic named ("कोई भी योजना बता
    # दो"), never "X योजना बता दो" / "X योजना सांगा". A need or work word
    # ("कोई किसान योजना बता दो") is a topic: the caller wants that kind.
    if not ("योजना बता दो" in lowered and "कोई" in lowered
            or "योजना सांगा" in lowered and "कोणत" in lowered):
        return False
    return not talk_words.spot_all(text, _ANY)
