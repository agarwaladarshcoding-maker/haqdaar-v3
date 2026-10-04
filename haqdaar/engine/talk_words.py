"""haqdaar/engine/talk_words.py

Plain word spotting for the talk loop (step 7.13). The model alone missed it on a real call:
the caller said "farmer schemes" twice and was asked "farming or business?" twice. So the clear
words are read by fixed code first: caller's words -> box values. A box is filled only when
exactly ONE of its values is named. The model's own facts still count on top of this.
Pure: no model, no I/O.
"""
from __future__ import annotations

import re
from typing import Any

WORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "category": {
        "farming": ("खेती", "किसान", "फार्मर", "फार्मिंग", "फ़ार्मर", "फसल", "कृषि", "kheti", "kisan", "farmer",
                    "farmers", "farming", "crop", "crops", "agriculture"),
        "business_loans": ("लोन", "कर्ज", "कर्ज़", "ऋण", "व्यापार", "बिज़नेस", "बिजनेस", "दुकान", "धंधा", "loan",
                           "loans", "business", "shop"),
        "jobs_skills": ("नौकरी", "रोज़गार", "रोजगार", "जॉब", "ट्रेनिंग", "प्रशिक्षण", "job", "jobs", "employment",
                        "training", "skill", "skills"),
        "health": ("इलाज", "अस्पताल", "बीमारी", "दवा", "हेल्थ", "स्वास्थ्य", "health", "hospital", "treatment"),
        "housing": ("मकान", "आवास", "घर बना", "पक्का घर", "house", "housing", "home"),
        "pension": ("पेंशन", "बुढ़ापा", "बुढ़ापे", "pension", "old age"),
        "education": ("पढ़ाई", "छात्रवृत्ति", "स्कॉलरशिप", "शिक्षा", "education", "scholarship", "study"),
        "women_children": ("गर्भवती", "डिलीवरी", "प्रसव", "स्वयं सहायता समूह", "pregnant", "delivery", "self help group"),
        "welfare_disability": ("विकलांग", "दिव्यांग", "अपंग", "disabled", "disability"),
    },
    "occupation": {
        "farmer": ("किसान", "फार्मर", "फ़ार्मर", "खेती करता", "खेती करती", "farmer", "kisan"),
        "street_vendor": ("ठेला", "ठेले", "रेहड़ी", "फेरी", "street vendor", "vendor", "cart", "hawker"),
        "weaver": ("बुनकर", "weaver"),
        "artisan": ("कारीगर", "artisan"),
        "apprentice": ("अप्रेंटिस", "apprentice"),
    },
    "gender": {
        "female": ("महिला", "औरत", "विधवा", "गर्भवती", "woman", "widow", "female", "pregnant"),
        "male": ("पुरुष", "आदमी", "male"),
    },
}

_ASCII = re.compile(r"^[a-z ]+$")


def _has(text: str, word: str) -> bool:
    if _ASCII.match(word):
        return re.search(rf"\b{re.escape(word)}\b", text) is not None
    return word in text


def spot(text: str, corpus: Any) -> dict[str, str]:
    """Box values the caller's words name outright. Two values of one box named -> that box is left out."""
    text = " " + str(text).lower() + " "
    out: dict[str, str] = {}
    for box, values in WORDS.items():
        allowed = corpus.values(box)
        named = [v for v, words in values.items() if v in allowed and any(_has(text, w) for w in words)]
        if len(named) == 1:
            out[box] = named[0]
    return out
