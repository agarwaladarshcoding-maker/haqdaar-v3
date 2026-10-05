"""haqdaar/engine/words_no_answer.py

Step 1.3a: "I do not know" / "I will not say" in the caller's words. Either
one sets the asked box to not known at once, and it is never asked again.
("Why do you ask?" is answered by the model with one sentence of reason; it
needs no list here.) Hindi, Marathi, English. Pure: no model, no I/O.
"""
from __future__ import annotations

DONT_KNOW: tuple[str, ...] = (
    # Hindi
    "पता नहीं",
    "पता नही",
    "मालूम नहीं",
    "मालूम नही",
    "नहीं पता",
    "नही पता",
    "याद नहीं",
    "याद नही",
    # Marathi
    "माहित नाही",
    "माहीत नाही",
    "आठवत नाही",
    # English
    "don't know",
    "dont know",
    "do not know",
    "not sure",
    "no idea",
    "i forgot",
)

WONT_SAY: tuple[str, ...] = (
    # Hindi
    "नहीं बताऊंगा",
    "नहीं बताऊँगा",
    "नहीं बताऊंगी",
    "नहीं बताऊँगी",
    "नहीं बताना",
    "नही बताना",
    "बताना नहीं है",
    "मत पूछो",
    # Marathi
    "सांगणार नाही",
    "सांगायचे नाही",
    # English
    "won't say",
    "wont say",
    "will not say",
    "would not say",
    "rather not say",
    "don't want to say",
    "dont want to say",
)

DONT_KNOW_TAG = "dont_know"
WONT_SAY_TAG = "wont_say"


def no_answer(text: str) -> str:
    """DONT_KNOW_TAG / WONT_SAY_TAG when the caller will not answer, else ""."""
    lowered = " " + str(text).lower() + " "
    if any(phrase in lowered for phrase in WONT_SAY):
        return WONT_SAY_TAG
    if any(phrase in lowered for phrase in DONT_KNOW):
        return DONT_KNOW_TAG
    return ""
