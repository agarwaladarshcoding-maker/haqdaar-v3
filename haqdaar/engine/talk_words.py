"""haqdaar/engine/talk_words.py

Plain word spotting for the talk loop (step 7.13). The model alone missed it on a real call:
the caller said "farmer schemes" twice and was asked "farming or business?" twice. So the clear
words are read by fixed code first: caller's words -> box values. A box is filled only when
exactly ONE of its values is named. The model's own facts still count on top of this.
Step 1.3a: the word "not" next to a word unsets it ("मैं किसान नहीं हूँ" is not
a farmer); another person's work is not the caller's ("my husband was a farmer").
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
        "housing": ("मकान", "आवास", "घर", "घर बना", "पक्का घर", "house", "housing", "home"),
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
        "worker": ("मज़दूरी", "मजदूरी", "मज़दूर", "मजदूर", "दिहाड़ी", "labour", "labor", "worker",
                   "daily wage"),
    },
    "gender": {
        "female": ("महिला", "औरत", "विधवा", "गर्भवती", "woman", "widow", "female", "pregnant"),
        "male": ("पुरुष", "आदमी", "male"),
    },
}

_ASCII = re.compile(r"^[a-z' ]+$")

# 1.3a: a word with one of these right by it is unset. The Hindi ones usually
# come after the word ("किसान नहीं"), the English ones before ("not a farmer").
NEGATORS = frozenset({"नहीं", "नही", "न", "मत", "not", "no", "don't", "dont"})
# Tokens that may sit between the negator and the word without breaking it.
_FILLERS = frozenset({"a", "an", "the", "to", "एक", "ही", "भी"})
# "I do not want a loan": the negator scopes over what comes after want/need.
_WANT_VERBS = frozenset({"want", "wants", "wanna", "need", "needs"})
# A clause ends here; negation and "who said it" never cross it.
_CLAUSES = re.compile(r"[।?!;,]+")
_TOK = re.compile(r"[a-z']+|[\u0900-\u097f]+")

# Bare "घर" is two things: "a house" (a housing need) and "at home" (a place).
# With a locative right after it ("घर में कोई कमाने वाला नहीं") it is the
# place, not the need, and the turn stays a situation. ("घर के लिए" still
# counts: लिए makes it the thing wanted.)
_HOME_POST = frozenset({"में", "पर", "का", "की", "के", "से", "तक", "वाला", "वाले", "वाली"})
_HOME_WANT = frozenset({"लिए", "हेतु", "वास्ते"})


def _kept(word: str, toks: list[str], at: int) -> bool:
    if word != "घर":
        return True
    nxt = toks[at + 1] if at + 1 < len(toks) else ""
    if nxt not in _HOME_POST:
        return True
    after = toks[at + 2] if at + 2 < len(toks) else ""
    return after in _HOME_WANT

# 1.3a: work named in the same clause as one of these is someone else's work,
# never the caller's occupation. Plain "my" / "मेरे" is NOT one: "मेरे को
# फार्मर स्कीम्स" is the caller's own need.
OTHER_PEOPLE = frozenset({
    "husband", "wife", "mother", "father", "son", "daughter", "brother", "sister",
    "mom", "dad",
    "पति", "पत्नी", "माँ", "मां", "माता", "माताजी", "पिता", "पिताजी",
    "बेटा", "बेटी", "बेटे", "भाई", "बहन", "मम्मी", "पापा",
    "आई", "वडील", "भाऊ", "बहीण", "मुलगा", "मुलगी", "नवरा", "बायको",
})


def _has(text: str, word: str) -> bool:
    if _ASCII.match(word):
        return re.search(rf"\b{re.escape(word)}\b", text) is not None
    return word in text


def _toks(clause: str) -> list[str]:
    return _TOK.findall(clause)


def _occurrences(word: str, toks: list[str]) -> list[int]:
    """Token places where the word starts. A Devanagari token may carry an
    ending ("किसानों" still names किसान); an ASCII token must match exactly."""
    parts = _TOK.findall(word.lower())
    if not parts:
        return []
    out = []
    for i in range(len(toks) - len(parts) + 1):
        ok = True
        for k, part in enumerate(parts):
            tok = toks[i + k]
            if _ASCII.match(part):
                if tok != part:
                    ok = False
                    break
            elif part not in tok:
                ok = False
                break
        if ok:
            out.append(i)
    return out


def _negated_at(toks: list[str], at: int, span: int) -> bool:
    """A negator right by the word at `at` (length `span` tokens)."""
    for i in range(max(0, at - 2), min(len(toks), at + span + 2)):
        if i in range(at, at + span) or toks[i] not in NEGATORS:
            continue
        between = toks[i + 1:at] if i < at else toks[at + span:i]
        if all(t in _FILLERS for t in between):
            return True
    for i, tok in enumerate(toks):
        if tok in _WANT_VERBS and any(
                toks[j] in NEGATORS for j in range(max(0, i - 1), i)):
            for k in range(i + 1, min(len(toks), i + 4)):
                if toks[k] in ("a", "the"):
                    continue
                if k == at:
                    return True
                break
    return False


def _clean_occurrences(word: str, text: str) -> list[str]:
    """The clauses where the word is said plain: not negated there."""
    lowered = " " + str(text).lower() + " "
    if not _has(lowered, word):
        return []
    out = []
    for clause in _CLAUSES.split(lowered):
        toks = _toks(clause)
        if not toks:
            continue
        for at in _occurrences(word, toks):
            if _kept(word, toks, at) and not _negated_at(toks, at, len(_TOK.findall(word.lower()))):
                out.append(clause)
                break
    return out


def spot_all(text: str, corpus: Any) -> dict[str, list[str]]:
    """Every named value per box (1.3a: two needs name two values of one box;
    spot() then leaves that box out, and the other need is kept here)."""
    out: dict[str, list[str]] = {}
    for box, values in WORDS.items():
        allowed = corpus.values(box)
        named = [v for v, words in values.items()
                 if v in allowed and any(_clean_occurrences(w, text) for w in words)]
        if named:
            out[box] = named
    return out


def spot(text: str, corpus: Any) -> dict[str, str]:
    """Box values the caller's words name outright. Two values of one box named -> that box is left out."""
    out: dict[str, str] = {}
    for box, values in spot_all(text, corpus).items():
        if len(values) != 1:
            continue
        out[box] = values[0]
    # Another person's work is not the caller's occupation (checked per clause).
    return _person_filter(text, out)


def _person_filter(text: str, out: dict[str, str]) -> dict[str, str]:
    """Another person's work is not the caller's: the occupation counts only
    when its word is said plain in a clause with no other person in it."""
    if "occupation" not in out:
        return out
    for word in WORDS["occupation"][out["occupation"]]:
        for clause in _clean_occurrences(word, text):
            if not any(t in OTHER_PEOPLE for t in _toks(clause)):
                return out
    del out["occupation"]
    return out
