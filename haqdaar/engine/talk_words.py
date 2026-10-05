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
        "farming": ("खेती", "शेती", "किसान", "शेतकरी", "फार्मर", "फार्मिंग", "फ़ार्मर", "फसल", "कृषि", "kheti", "kisan", "farmer",
                    "farmers", "farming", "crop", "crops", "agriculture"),
        "business_loans": ("लोन", "कर्ज", "कर्ज़", "ऋण", "व्यापार", "बिज़नेस", "बिजनेस", "दुकान", "धंधा", "कारोबार", "loan",
                           "loans", "business", "shop"),
        "jobs_skills": ("नौकरी", "नोकरी", "रोज़गार", "रोजगार", "जॉब", "ट्रेनिंग", "प्रशिक्षण", "job", "jobs", "employment",
                        "training", "skill", "skills"),
        "health": ("इलाज", "अस्पताल", "बीमारी", "बीमार", "दवा", "हेल्थ", "स्वास्थ्य", "health", "hospital", "treatment",
                   "sick"),
        "housing": ("मकान", "आवास", "घर", "घर बना", "पक्का घर", "ghar", "house", "housing", "home"),
        "pension": ("पेंशन", "पेन्शन", "बुढ़ापा", "बुढ़ापे", "pension", "old age"),
        "education": ("पढ़ाई", "छात्रवृत्ति", "स्कॉलरशिप", "शिक्षा", "education", "scholarship", "study"),
        "women_children": ("गर्भवती", "डिलीवरी", "प्रसव", "स्वयं सहायता समूह", "pregnant", "delivery", "self help group"),
        "welfare_disability": ("विकलांग", "दिव्यांग", "अपंग", "disabled", "disability"),
    },
    "occupation": {
        "farmer": ("किसान", "शेतकरी", "फार्मर", "फ़ार्मर", "खेती करता", "खेती करती", "farmer", "kisan"),
        "street_vendor": ("ठेला", "ठेले", "रेहड़ी", "फेरी", "street vendor", "vendor", "cart", "hawker"),
        "weaver": ("बुनकर", "weaver"),
        "artisan": ("कारीगर", "artisan"),
        "apprentice": ("अप्रेंटिस", "apprentice"),
        "worker": ("मज़दूरी", "मजदूरी", "मज़दूर", "मजदूर", "मज़दूरों", "मजदूरों", "दिहाड़ी", "labour", "labourer",
                   "labourers", "labor", "worker", "workers", "daily wage"),
    },
    "gender": {
        # 1.3a: mother/daughter/wife/sister words name a female beneficiary
        # ("मेरी माँ के लिए पेंशन"). The male side is deliberately NOT mirrored:
        # "my husband/father" usually narrates the household (a widow's own
        # pension), it must not wipe her female away.
        "female": ("महिला", "औरत", "विधवा", "गर्भवती", "माँ", "मां", "बेटी", "पत्नी", "बहन",
                   "मुलगी", "बहीण", "बायको",
                   "woman", "widow", "female", "pregnant", "mother", "daughter", "wife", "sister", "mom"),
        "male": ("पुरुष", "आदमी", "male"),
    },
}

_ASCII = re.compile(r"^[a-z' ]+$")

# 1.3a: a word with one of these right by it is unset. The Hindi ones usually
# come after the word ("किसान नहीं"), the English ones before ("not a farmer").
# 1.3b: Latin "nahi / nahin / mat" count too ("main kisan nahi hoon").
NEGATORS = frozenset({"नहीं", "नही", "न", "मत", "not", "no", "don't", "dont",
                      "nahi", "nahin", "mat", "नाही", "नको", "nako", "naahi"})
# Tokens that may sit between the negator and the word without breaking it.
_FILLERS = frozenset({"a", "an", "the", "to", "एक", "ही", "भी"})
# "I do not want a loan": the negator scopes over what comes after want/need.
_WANT_VERBS = frozenset({"want", "wants", "wanna", "need", "needs"})
# A clause ends here; negation and "who said it" never cross it.
_CLAUSES = re.compile(r"[।?!;,]+")
_TOK = re.compile(r"[a-z']+|[\u0900-\u097f]+")
# 1.3b: a new self part starts here. What comes before one of these is said
# about someone else ("my wife died I am a farmer"; "भाई मैं किसान हूँ").
# "मेरी / my" is NOT one: "मेरी माँ के लिए" is said about her, plainly.
_SELF_START = frozenset({"मैं", "मै", "मी", "main", "mein", "i", "i'm", "im"})
# 1.3b: "I have no X" is a need, not a no ("मेरे पास नौकरी नहीं है",
# "मुझे लोन नहीं मिला"). Only "I am not X" / "I do not want X" takes X away.
_HAVE = frozenset({"पास", "paas", "pas", "have", "has", "had"})
_GOT = frozenset({"मिला", "मिली", "मिले", "मिलती", "मिलता", "मिलते", "get", "got"})
# "घर नहीं है" / "ghar nahi hai": a negator then है is "there is none".
_IS = frozenset({"है", "हैं", "hai", "hain"})
# 1.3b: words said FOR someone ("मेरी माँ के लिए", "for my mother") keep that
# person's gender and work; plain narration about them does not.
_FOR = frozenset({"लिए", "हेतु", "वास्ते", "for", "साठी", "liye"})

# Bare "घर" is two things: "a house" (a housing need) and "at home" (a place).
# With a locative right after it ("घर में कोई कमाने वाला नहीं") it is the
# place, not the need, and the turn stays a situation. ("घर के लिए" still
# counts: लिए makes it the thing wanted.)
_HOME_POST = frozenset({"में", "पर", "का", "की", "के", "से", "तक", "वाला", "वाले", "वाली",
                        "mein", "me", "par", "ka", "ki", "ke", "se"})
_HOME_WANT = frozenset({"लिए", "हेतु", "वास्ते"})


def _kept(word: str, toks: list[str], at: int) -> bool:
    if word not in ("घर", "ghar"):
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
    "bhai", "behen", "pati", "patni", "beta", "beti", "maa", "pita", "papa", "baap",
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


# The tail a Devanagari token may add to a whole word ("महिलाओं" is still
# महिला, "किसानों" still किसान): vowel signs and the anusvara only. A tail
# with a consonant in it ("मांगना" after "मां") is another word.
_TAIL = re.compile(r"^[\u0900-\u0903\u093e-\u094c]*$")


def _occurrences(word: str, toks: list[str], whole: bool = False) -> list[int]:
    """Token places where the word starts. A Devanagari token may carry an
    ending ("किसानों" still names किसान); an ASCII token must match exactly.
    With `whole` (gender words) the ending must be vowel signs only, so "मां"
    is not found inside "मांगना"."""
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
            elif whole and k == len(parts) - 1 and not (
                    tok == part or (tok.startswith(part) and bool(_TAIL.match(tok[len(part):])))):
                ok = False
                break
            elif part not in tok:
                ok = False
                break
        if ok:
            out.append(i)
    return out


# Every token of every word form, for the "नहीं belongs to the word before
# it" rule in _negated_at.
_VOCAB_TOKENS = frozenset(
    t for forms in WORDS.values() for words in forms.values() for word in words
    for t in _TOK.findall(word.lower()))


def _negated_at(toks: list[str], at: int, span: int) -> bool:
    """A negator right by the word at `at` (length `span` tokens)."""
    for i in range(max(0, at - 2), min(len(toks), at + span + 2)):
        if i in range(at, at + span) or toks[i] not in NEGATORS:
            continue
        if i < at and i > 0 and toks[i - 1] in _VOCAB_TOKENS:
            continue  # 1.3b: "किसान नहीं मज़दूर": the नहीं unsets किसान, not मज़दूर
        between = toks[i + 1:at] if i < at else toks[at + span:i]
        if all(t in _FILLERS for t in between):
            return True
    for i, tok in enumerate(toks):
        if tok in _WANT_VERBS and any(
                toks[j] in NEGATORS for j in range(max(0, i - 1), i)):
            for k in range(i + 1, min(len(toks), i + 4)):
                if toks[k] in ("a", "the", "any"):
                    continue
                if k == at:
                    return True
                break
    return False


# "किसान नहीं है" is a no about someone, not a lack: work words never take the है rule.
_WORK_TOKENS = frozenset(
    t for words in WORDS["occupation"].values() for w in words for t in _TOK.findall(w.lower())
) | frozenset({"किसान", "शेतकरी", "kisan", "farmer"})


def _lacked_at(toks: list[str], at: int, span: int) -> bool:
    """1.3b: the negated word is a need, not a no. "मेरे पास नौकरी नहीं है",
    "I have no job" (have + no by it), "मुझे लोन नहीं मिला" (no + got)."""
    lo, hi = max(0, at - 2), min(len(toks), at + span + 2)
    for i in range(lo, hi):
        if i in range(at, at + span):
            continue
        tok = toks[i]
        if tok in _HAVE:
            if tok in ("पास", "paas", "pas") or (i < at and at - i <= 3 and any(
                    t in NEGATORS for t in toks[i + 1:at])):
                return True
        if tok in _IS and i > 0 and toks[i - 1] in NEGATORS and not (
                set(toks[at:at + span]) & _WORK_TOKENS):
            return True
        if tok in _GOT and any(
                toks[n] in NEGATORS for n in range(max(0, i - 1), min(len(toks), i + 2))
                if n != i):
            return True
    return False


def _self_parts(toks: list[str]) -> list[list[str]]:
    """1.3b: split the tokens before every "I" word. The first part is said
    about someone else; the rest is the caller's own."""
    out = [[], ]
    for tok in toks:
        if tok in _SELF_START and out[-1]:
            out.append([])
        out[-1].append(tok)
    return [p for p in out if p]


def _value_clauses(forms: tuple[str, ...], text: str, whole: bool = False) -> list[list[str]]:
    """Token parts where any form is said plain: kept, not negated (a lack is
    not a no), and no short form hiding inside a negated longer one ("vendor"
    inside "not a street vendor")."""
    lowered = " " + str(text).lower() + " "
    if not any(_has(lowered, word) for word in forms):
        return []
    out = []
    for clause in _CLAUSES.split(lowered):
        for toks in _self_parts(_toks(clause)):
            if not toks:
                continue
            long_negated: set[int] = set()
            for form in sorted(forms, key=lambda f: -len(_TOK.findall(f.lower()))):
                parts = _TOK.findall(form.lower())
                if not parts:
                    continue
                for at in _occurrences(form, toks, whole):
                    span = len(parts)
                    neg = _negated_at(toks, at, span) and not _lacked_at(toks, at, span)
                    if neg:
                        if span > 1:
                            long_negated.update(range(at, at + span))
                    elif _kept(form, toks, at) and not (span == 1 and at in long_negated):
                        out.append(toks)
                        break
                else:
                    continue
                break
    return out


def _clean_occurrences(word: str, text: str) -> list[str]:
    """The clauses where the word is said plain: not negated there."""
    return [" ".join(toks) for toks in _value_clauses((word,), text)]


# The need follows "I want": "मुझे लोन चाहिए", "I need a loan", "मला कर्ज हवे".
_WANT_MARKS = frozenset({"चाहिए", "चाहिये", "चाहता", "चाहती", "चाहते", "चाहूँगा", "चाहूंगा", "चाहूँगी", "चाहूंगी",
                         "हवे", "हवा", "हवी", "हवेत", "पाहिजे", "need", "needs", "want", "wants", "wanna"})
# Said between a word and the "want" word, they put the word in someone else's sentence
# ("मेरी मां बीमार है मुझे लोन चाहिए": the illness is hers, the loan is wanted).
_BREAKS = _IS | frozenset({"मुझे", "मैं", "मै", "मला", "मी", "i", "me", "is", "was", "थी", "था", "आहे"})


def _wanted(toks: list[str], value: str) -> bool:
    """The value's word stands right by a "want" word, in the same sentence of the talk."""
    marks = [i for i, t in enumerate(toks) if t in _WANT_MARKS]
    for word in WORDS["category"][value]:
        for at in _occurrences(word, toks):
            for m in marks:
                lo, hi = (at + 1, m) if at < m else (m + 1, at)
                if hi - lo <= 3 and not any(t in _BREAKS for t in toks[lo:hi]):
                    return True
    return False


def _ordered(text: str, box: str, values: list[str]) -> list[str]:
    """1.3b: the named values first-named first ("खेती और घर": farming, then
    housing). The talk takes the first and keeps the rest for later.
    A category said right by a "want" word goes before the others (the need
    follows "मुझे ... चाहिए", not the illness of the mother)."""
    toks = _toks(" " + str(text).lower() + " ")
    whole = box == "gender"

    def _pos(value: str) -> int:
        best = len(toks)
        for word in WORDS[box][value]:
            for at in _occurrences(word, toks, whole):
                best = min(best, at)
        return best

    return sorted(values, key=lambda v: (box == "category" and not _wanted(toks, v), _pos(v)))


def spot_all(text: str, corpus: Any) -> dict[str, list[str]]:
    """Every named value per box (1.3a: two needs name two values of one box;
    spot() then leaves that box out, and the other need is kept here)."""
    out: dict[str, list[str]] = {}
    for box, values in WORDS.items():
        allowed = corpus.values(box)
        named = [v for v, words in values.items()
                 if v in allowed and _value_clauses(words, text, whole=box == "gender")]
        if named:
            out[box] = _ordered(text, box, named)
    # Another person's words are not the caller's: they are not "named" at all.
    return _person_filter(text, out)


def spot(text: str, corpus: Any) -> dict[str, str]:
    """Box values the caller's words name outright. Two values of one box named -> that box is left out."""
    return {box: values[0] for box, values in spot_all(text, corpus).items() if len(values) == 1}


def _person_filter(text: str, out: dict[str, list[str]]) -> dict[str, list[str]]:
    """1.3b: another person's gender and work are not the caller's. Each stays
    only when said plain in a part with no other person in it, or said FOR
    them ("मेरी माँ के लिए पेंशन", "for my mother")."""
    for box in ("occupation", "gender"):
        named = out.get(box, [])
        for value in list(named):
            self_said = any(
                not any(t in OTHER_PEOPLE for t in toks) or any(t in _FOR for t in toks)
                for toks in _value_clauses(WORDS[box][value], text, whole=box == "gender")
            )
            if not self_said:
                named = [v for v in named if v != value]
        if named:
            out[box] = named
        else:
            out.pop(box, None)
    return out


# Marathi "Xसाठी" (for X) is one token: the person word carries the साठी tail.
_SAATHI_PEOPLE = ("आई", "वडील", "वडिलां", "भाऊ", "बहीण", "मुलगा", "मुलगी", "नवरा", "बायको")


_SELF_FOR = frozenset({"मेरे", "अपने", "खुद", "mere", "apne", "me", "myself", "माझ्या", "स्वतः"})


def other_person(text: str) -> str:
    """1.3b: who the help is for, when it is someone else ("for my mother",
    "मेरी माँ के लिए", "माझ्या आईसाठी"): the person word, else "". The person must
    stand by the "for" word, so "भाई, मेरे लिए योजना बताओ" names no one."""
    toks = _toks(" " + str(text).lower() + " ")
    for i, tok in enumerate(toks):
        for p in _SAATHI_PEOPLE:
            if p in tok and tok != p:
                return p
        if tok not in _FOR:
            continue
        if i and toks[i - 1] in _SELF_FOR or toks[i + 1:i + 2] in (["me"], ["myself"]):
            continue
        for near in toks[max(0, i - 2):i] + toks[i + 1:i + 3]:
            if near in OTHER_PEOPLE:
                return near
    return ""


# "मैं किसान हूँ": work said about oneself, not a kind of help asked for.
_AM = frozenset({"हूँ", "हूं", "hoon", "hu", "am", "i'm", "im", "आहे", "आहोत"})
_WORK_FORMS = frozenset(w for words in WORDS["occupation"].values() for w in words)


def work_only(text: str, value: str) -> bool:
    """The category `value` is named only by a work word in an "I am" sentence ("मैं किसान हूँ"),
    with no "want" word. That is the work box, not a new need."""
    forms = WORDS["category"][value]
    clauses = _value_clauses(forms, text)
    if not clauses:
        return False
    for toks in clauses:
        hit = [f for f in forms if _occurrences(f, toks)]
        if not hit or any(f not in _WORK_FORMS for f in hit):
            return False
        if not any(t in _AM for t in toks) or any(t in _WANT_MARKS for t in toks):
            return False
    return True


def new_person(text: str) -> bool:
    return bool(other_person(text))
