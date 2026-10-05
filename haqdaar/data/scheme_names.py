"""haqdaar/data/scheme_names.py

Step 1.3a: the names people SAY for each scheme (short forms, letters, Hindi
and Latin), and the well-known schemes we do NOT hold.

The snapshot rows carry the written names + aliases; what callers actually say
("मनरेगा", "केसीसी", "pm awas") is often shorter than those, and the name
match scores a short sentence against a long name low. So each scheme carries
its short names here, next to the scheme data: the name search reads them by
scheme id, so 100 schemes can carry theirs the same way.
Pure: no model, no I/O.
"""
from __future__ import annotations

import re

# scheme id -> short spoken forms (bare names, letters, Hindi and Latin).
SHORT_NAMES: dict[str, tuple[str, ...]] = {
    "pm-kisan": ("पीएम किसान", "pm kisan", "किसान सम्मान निधि", "kisan samman nidhi"),
    "mgnrega": ("मनरेगा", "mgnrega", "नरेगा", "nrega"),
    "kcc": ("केसीसी", "kcc"),
    "pmay-g": ("pm awas", "pmay", "पीएम आवास", "आवास योजना", "pm awas yojana"),
    "pmfby": ("pmfby", "पीएमएफबीवाई", "फसल बीमा", "fasal bima", "crop insurance"),
    "apy": ("apy", "अटल पेंशन", "atal pension"),
    "day-nrlm": ("nrlm", "आजीविका मिशन", "आजीविका", "livelihood mission"),
    "ignwps": ("ignwps", "विधवा पेंशन", "widow pension"),
    "igndps": ("igndps", "दिव्यांग पेंशन", "विकलांग पेंशन", "disability pension"),
    "jsy1": ("jsy", "जेएसवाई", "जननी सुरक्षा", "janani suraksha"),
    "nfbs": ("nfbs", "पारिवारिक लाभ", "family benefit"),
    "pm-svanidhi": ("स्वनिधि", "svanidhi", "पीएम स्वनिधि", "pm svanidhi"),
    "pmmy": ("pmmy", "मुद्रा", "mudra", "मुद्रा लोन", "mudra loan", "मुद्रा योजना", "mudra yojana"),
    "naps": ("naps", "अप्रेंटिसशिप", "apprenticeship"),
    "nps-tsep": ("व्यापारी पेंशन", "trader pension", "traders pension"),
    "pmegp": ("pmegp", "रोजगार सृजन", "employment generation"),
    "smam": ("smam", "एसएमएएम", "कृषि मशीनरी", "कृषि यंत्र"),
}

# Well-known schemes we do NOT hold: canonical id -> words that name it.
# A turn naming one of these is its own kind of turn ("I do not have that one
# yet"), not a situation to ask questions about. Kept here, next to SHORT_NAMES.
NOT_HELD: dict[str, tuple[str, ...]] = {
    "ayushman": ("आयुष्मान", "ayushman", "आयुष्मान भारत", "ayushman bharat"),
    "ration_card": ("राशन कार्ड", "ration card", "राशन", "ration"),
    "ladli_behna": ("लाडली बहना", "ladli behna", "लाड़ली बहना", "ladli bahan"),
    "ujjwala": ("उज्ज्वला", "ujjwala", "उज्ज्वला योजना", "ujjwala yojana"),
}

_ASCII_WORD = re.compile(r"^[a-z ]+$")
_DEVA = r"\u0900-\u097F"


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
