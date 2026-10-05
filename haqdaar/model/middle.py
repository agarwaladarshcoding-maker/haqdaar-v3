"""haqdaar/model/middle.py

Reply half of English in the middle (step 1.4a + 1.4b). English reply in, caller
language out, one sentence at a time so the voice can start on the first.

- "en": each sentence comes back as it is, no network call.
- every other Sarvam language: each sentence goes through AnswerTranslator (sarvam-translate:v1).
- Any other code: one item with the text "not supported", marked failed.
- Fixed guard on every sentence, no model: numbers and units must match both ways in order,
  and a scheme name in the English must come out unchanged or in the target tongue.
- A failed sentence gets one more try. A still-failed sentence, a time-out, or a
  network error comes back marked failed and returns the English sentence, never wrong text.
- Never raises.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Iterator, Optional, Sequence
import unicodedata

from haqdaar.model.translate import TARGET_CODES, AnswerTranslator

logger = logging.getLogger(__name__)

LANGS = tuple(TARGET_CODES)

_SENTENCE_GAP = re.compile(r"(?<=[.!?।])\s+")
_SHORT_PIECE = 12

# The digits of every Indic script Sarvam may write (Devanagari to Malayalam: each block has 0-9 at
# offset 0x66, Tamil included), so "৬০০০" in Bengali counts as 6000 for the guard.
_TO_LATIN = str.maketrans({chr(base + 0x66 + d): str(d) for base in range(0x0900, 0x0D80, 0x80) for d in range(10)})

UNITS: dict[str, int] = {
    "हज़ार": 1_000,
    "हजार": 1_000,
    "thousand": 1_000,
    "लाख": 100_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "करोड़": 10_000_000,
    "करोड": 10_000_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
}

WORDS: dict[str, int] = {
    # Hindi and Marathi numbers
    "शून्य": 0, "एक": 1, "दो": 2, "दोन": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाच": 5,
    "छह": 6, "छः": 6, "सहा": 6, "सात": 7, "आठ": 8, "नौ": 9, "नऊ": 9, "दस": 10, "दहा": 10,
    "ग्यारह": 11, "अकरा": 11, "बारह": 12, "बारा": 12, "तेरह": 13, "तेरा": 13,
    "चौदह": 14, "चौदा": 14, "पंद्रह": 15, "पंधरा": 15, "सोलह": 16, "सोळा": 16,
    "सत्रह": 17, "सतरा": 17, "अठारह": 18, "अठरा": 18, "उन्नीस": 19, "एकोणीस": 19,
    "बीस": 20, "वीस": 20,
    "तीस": 30, "चालीस": 40, "चाळीस": 40, "पचास": 50, "पन्नास": 50,
    "साठ": 60, "सत्तर": 70, "अस्सी": 80, "ऐंशी": 80, "नब्बे": 90, "नव्वद": 90,
    "सौ": 100, "शंभर": 100,
    # Ordinals
    "पहला": 1, "पहिला": 1, "पहली": 1, "पहिले": 1, "first": 1,
    "दूसरा": 2, "दुसरा": 2, "दूसरी": 2, "दुसरे": 2, "second": 2,
    "तीसरा": 3, "तिसरा": 3, "तीसरी": 3, "तिसरे": 3, "third": 3,
    "चौथा": 4, "चौथी": 4, "चौथे": 4, "fourth": 4,
}

EN_UNIT_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_ALL_UNIT_WORDS = {**WORDS, **EN_UNIT_WORDS}

_UNITS_PAT = "|".join(re.escape(u) for u in sorted(UNITS.keys(), key=len, reverse=True))
_WORDS_PAT = "|".join(re.escape(w) for w in sorted(WORDS.keys(), key=len, reverse=True))
_UNIT_WORDS_PAT = "|".join(re.escape(w) for w in sorted(_ALL_UNIT_WORDS.keys(), key=len, reverse=True))

_COMBINED_NUM = re.compile(
    rf"(?P<num_unit>(?<!\w)(?:(?P<nu_val>\d+(?:\.\d+)?)|(?P<nu_word>{_UNIT_WORDS_PAT}))\s*(?P<unit>{_UNITS_PAT})\b)|"
    rf"(?P<ordinal>\b(?P<ord_val>\d+)(?:st|nd|rd|th)\b)|"
    rf"(?P<number>(?<!\w)\d+(?:,\d+)*(?:\.\d+)?(?!\w))|"
    rf"(?P<word>(?<!\w)(?P<w_val>{_WORDS_PAT})(?!\w))",
    re.I | re.UNICODE,
)


@dataclass
class Out:
    text: str  # what to say; English sentence when failed
    ok: bool  # True means it passed the guard and may be spoken
    ms: int  # time spent on this sentence


def split_sentences(text: str) -> list[str]:
    """Cut into sentences in order following haqdaar.engine.talk._sentences."""
    if not text:
        return []
    out: list[str] = []
    for piece in _SENTENCE_GAP.split(str(text).strip()):
        if out and len(out[-1]) < _SHORT_PIECE:
            out[-1] += " " + piece
        elif piece:
            out.append(piece)
    return out


def split_words(text: str) -> list[str]:
    """Split text into lower-cased words on whitespace and punctuation across scripts.
    Preserves Indic combining marks / vowel signs.
    """
    out: list[str] = []
    curr: list[str] = []
    for ch in str(text):
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("Z") or cat.startswith("S") or ch in " \t\n\r":
            if curr:
                out.append("".join(curr).lower())
                curr = []
        else:
            curr.append(ch)
    if curr:
        out.append("".join(curr).lower())
    return out


def _norm(text: str) -> str:
    return " ".join(split_words(text))


def deva_to_gu(text: str) -> str:
    """Devanagari to Gujarati Unicode character translation."""
    res = []
    for ch in text:
        o = ord(ch)
        if 0x0900 <= o <= 0x097F:
            res.append(chr(o + 0x0180))
        else:
            res.append(ch)
    return "".join(res)


DEVA_TO_TAMIL: dict[str, str] = {
    "क": "க", "ख": "க", "ग": "க", "घ": "க", "ङ": "ங",
    "च": "ச", "छ": "ச", "ज": "ஜ", "झ": "ஜ", "ञ": "ஞ",
    "ट": "ட", "ठ": "ட", "ड": "ட", "ढ": "ட", "ण": "ண",
    "त": "த", "थ": "த", "द": "த", "ध": "த", "न": "ந",
    "प": "ப", "फ": "ப", "ब": "ப", "भ": "ப", "म": "ம",
    "य": "ய", "र": "ர", "ल": "ல", "व": "வ",
    "श": "ச", "ष": "ஷ", "स": "ஸ", "ह": "ஹ",
    "अ": "அ", "आ": "ஆ", "इ": "இ", "ई": "ஈ", "उ": "உ", "ऊ": "ஊ",
    "ए": "எ", "ऐ": "ஐ", "ओ": "ஒ", "औ": "ஔ",
    "ा": "ா", "ि": "ி", "ी": "ீ", "ु": "ு", "ू": "ூ",
    "े": "ே", "ै": "ை", "ो": "ோ", "ौ": "ௌ",
    "्": "்", "ं": "ம்", "ँ": "ம்",
}


def deva_to_ta(text: str) -> str:
    """Devanagari to Tamil phonetic representation."""
    return "".join(DEVA_TO_TAMIL.get(ch, ch) for ch in text)


def _numbers(text: str) -> list[float]:
    """Every amount and number in the text in order of appearance.
    Understands units (lakh, crore, thousand, हज़ार), number words,
    Indian comma groups, ordinals (2nd, दूसरा), and phone numbers without dashes.
    """
    t = text.translate(_TO_LATIN)
    # Strip dashes between digits (e.g. phone numbers 9876-543-210)
    t = re.sub(r"(?<=\d)-(?=\d)", "", t)
    tokens: list[float] = []
    for m in _COMBINED_NUM.finditer(t):
        if m.group("num_unit"):
            val_str = m.group("nu_val")
            if val_str:
                v = float(val_str)
            else:
                v = float(_ALL_UNIT_WORDS[m.group("nu_word").lower()])
            u = UNITS[m.group("unit").lower()]
            tokens.append(round(v * u, 4))
        elif m.group("ordinal"):
            tokens.append(float(m.group("ord_val")))
        elif m.group("number"):
            s = m.group("number").replace(",", "")
            tokens.append(float(s))
        elif m.group("word"):
            tokens.append(float(WORDS[m.group("w_val").lower()]))
    return tokens


def scheme_names() -> list[dict]:
    """ONE place that reads the scheme names the data holds today.
    Takes names from haqdaar.data.scheme_names (short spoken names)
    plus snapshot full names and aliases.
    """
    try:
        from haqdaar.data.scheme_names import SHORT_NAMES, short_names_for

        root = os.environ.get("SNAPSHOTS_DIR", "snapshots")
        try:
            with open(os.path.join(root, "CURRENT"), encoding="utf-8") as f:
                sid = f.read().strip()
        except OSError:
            sid = ""

        out: list[dict] = []
        rows = []
        if sid:
            schemes_file = os.path.join(root, sid, "schemes.jsonl")
            if os.path.exists(schemes_file):
                with open(schemes_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                            if isinstance(row, dict) and row.get("scheme_id"):
                                rows.append(row)
                        except ValueError:
                            continue

        seen_sids = set()
        for row in rows:
            scheme_id = str(row["scheme_id"])
            seen_sids.add(scheme_id)
            item: dict = {"id": scheme_id}
            for lang in ("en", "hi", "mr", "gu", "ta"):
                names: list[str] = []
                raw = [row.get("scheme_name_" + lang)] + list(row.get("aliases_" + lang) or [])
                for name in raw:
                    normed = _norm(name or "")
                    if normed and normed not in names:
                        names.append(normed)
                item[lang] = names

            for sname in short_names_for(scheme_id):
                normed = _norm(sname)
                if not normed:
                    continue
                if any("\u0900" <= c <= "\u097F" for c in sname):
                    for lang in ("hi", "mr"):
                        if normed not in item[lang]:
                            item[lang].append(normed)
                else:
                    if normed not in item["en"]:
                        item["en"].append(normed)

            for h_name in list(item["hi"]):
                gu_name = _norm(deva_to_gu(h_name))
                if gu_name and gu_name not in item["gu"]:
                    item["gu"].append(gu_name)
                ta_name = _norm(deva_to_ta(h_name))
                if ta_name and ta_name not in item["ta"]:
                    item["ta"].append(ta_name)

            out.append(item)

        for scheme_id, snames in SHORT_NAMES.items():
            if scheme_id in seen_sids:
                continue
            item = {"id": scheme_id, "en": [], "hi": [], "mr": [], "gu": [], "ta": []}
            for sname in snames:
                normed = _norm(sname)
                if not normed:
                    continue
                if any("\u0900" <= c <= "\u097F" for c in sname):
                    for lang in ("hi", "mr"):
                        if normed not in item[lang]:
                            item[lang].append(normed)
                else:
                    if normed not in item["en"]:
                        item["en"].append(normed)

            for h_name in list(item["hi"]):
                gu_name = _norm(deva_to_gu(h_name))
                if gu_name and gu_name not in item["gu"]:
                    item["gu"].append(gu_name)
                ta_name = _norm(deva_to_ta(h_name))
                if ta_name and ta_name not in item["ta"]:
                    item["ta"].append(ta_name)
            out.append(item)

        return out
    except Exception:
        return []


def _matches_name(norm_text: str, name: str) -> bool:
    name_norm = _norm(name)
    if not name_norm:
        return False
    return f" {name_norm} " in f" {norm_text} "


def guard_ok(en: str, out: str, lang: str, names: list[dict] | None = None) -> bool:
    """Fixed guard for one sentence pair. True means the output may be spoken.
    Checks amounts/numbers in order, and scheme name consistency.
    """
    if _numbers(en) != _numbers(out):
        return False

    if names is None:
        names = scheme_names()

    norm_en = _norm(en)
    norm_out = _norm(out)
    want = lang if lang in ("hi", "mr", "gu", "ta") else ""

    for item in names:
        own_en = [_norm(n) for n in item.get("en", []) if _norm(n)]
        en_names_scheme = any(_matches_name(norm_en, n) for n in own_en)
        if not en_names_scheme:
            continue

        target_names = own_en + [_norm(n) for n in item.get(want, []) if _norm(n)]
        out_names_scheme = any(_matches_name(norm_out, n) for n in target_names)
        if not out_names_scheme:
            return False

    return True


def _timeout() -> float:
    try:
        return float(os.environ.get("MIDDLE_TIMEOUT_S", "3.0"))
    except ValueError:
        return 3.0


def _reply_timeout() -> float:
    try:
        return float(os.environ.get("MIDDLE_REPLY_TIMEOUT_S", "4.0"))
    except ValueError:
        return 4.0


def reply_in(reply_en: str, lang: str) -> Iterator[Out]:
    """English reply in, caller language out, one sentence at a time."""
    if not reply_en or not str(reply_en).strip():
        return

    if lang == "en":
        for sent in split_sentences(reply_en):
            yield Out(text=sent, ok=True, ms=0)
        return

    if lang not in LANGS:
        yield Out(text="not supported", ok=False, ms=0)
        return

    try:
        translator = AnswerTranslator(timeout=_timeout())
    except Exception:
        translator = None

    try:
        names = scheme_names()
    except Exception:
        names = []

    total_timeout = _reply_timeout()
    total_start = time.monotonic()

    for sent in split_sentences(reply_en):
        start = time.monotonic()
        elapsed_total = time.monotonic() - total_start
        if elapsed_total >= total_timeout:
            # Over whole-reply time limit: refused, return English sentence
            yield Out(text=sent, ok=False, ms=int((time.monotonic() - start) * 1000))
            continue

        text, ok = sent, False
        try:
            for _ in range(2):
                elapsed_total = time.monotonic() - total_start
                if elapsed_total >= total_timeout:
                    break
                got = None
                try:
                    if translator is not None:
                        got = translator.translate(sent, lang)
                except Exception:
                    got = None
                if got and got.strip() and guard_ok(sent, got, lang, names):
                    text, ok = got, True
                    break
        except Exception:
            text, ok = sent, False

        yield Out(text=text if ok else sent, ok=ok, ms=int((time.monotonic() - start) * 1000))
