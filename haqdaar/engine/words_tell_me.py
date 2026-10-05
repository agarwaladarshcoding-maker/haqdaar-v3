"""haqdaar/engine/words_tell_me.py

Step 1.3a: "just tell me" in the caller's words. When the caller says this,
asking stops for the rest of the call; the 2 best schemes left are shown.
Hindi, Marathi, English. Pure: no model, no I/O.
"""
from __future__ import annotations

# The whole phrase must be in the turn (every entry has 2+ words, or a
# distinctive spelling, so a plain substring is enough).
JUST_TELL_ME: tuple[str, ...] = (
    # Hindi
    "बस योजना बता दो",
    "योजना बता दो",
    "बस बता दो",
    "सीधे बताओ",
    "सीधा बताओ",
    "सवाल मत पूछो",
    "कोई सवाल नहीं",
    "बिना सवाल",
    # Marathi
    "फक्त योजना सांगा",
    "योजना सांगा",
    "थेट सांगा",
    "सरळ सांगा",
    "प्रश्न विचारू नका",
    "प्रश्न नको",
    # English
    "just tell me",
    "tell me directly",
    "tell me straight",
    "just tell me the scheme",
    "no questions",
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
    return any(phrase in lowered for phrase in JUST_TELL_ME)
