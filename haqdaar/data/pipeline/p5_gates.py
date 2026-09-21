"""Plan item 1.10 — the five gates (decision D5).

p4 translates. It does not judge. This file judges: for every scheme and every
language it runs five gates and writes a pass/fail row. Nothing downstream
(rendering, the snapshot, a real call) may use a scheme/language that failed,
because a wrong number or a false promise spoken down a phone line is the one
failure this project cannot take back.

The five gates, exactly as D5 states them:

  G1 Numbers   — the translation carries the same numbers as the English.
  G2 Forbidden — no second-person promise ("you are eligible"). Single honest
                 words like "पात्र" are fine and must NOT trip this gate.
  G3 Length    — Hindi/Marathi at most GATE_LENGTH_RATIO_MAX times the English.
  G4 Script    — at least GATE_SCRIPT_MIN Devanagari, and not a copy of the English.
  G5 Complete  — all six sections, in all three languages, non-empty.

One thing learned the hard way and recorded in .agent/NOTES.md (20 Sep): Sarvam
renders a small English digit as a Devanagari *word* — "3 equal installments"
comes back as "तीन". A gate that demands a digit for every English digit fails
every scheme. So G1 only insists on numbers big enough that no translator spells
them out (see `GATE_NUMBER_MIN`), and it always rejects a number the translation
invented.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

from haqdaar.contracts import tunables, vocab
from haqdaar.data.pipeline.p2_derive import DERIVED_DIR, REPORTS_DIR

# The six spoken sections. `name` is here because a scheme with no name in a
# language cannot be announced at all.
SECTION_FIELDS = (
    "name",
    "summary",
    "benefit_text",
    "who_can_apply",
    "documents",
    "how_to_apply",
)

SOURCE_LANG = "en"
TARGET_LANGS = ("hi", "mr")
ALL_LANGS = (SOURCE_LANG,) + TARGET_LANGS

# Same shape as p3's number regex: a digit run, commas allowed inside, optional
# decimal. "5,00,000" is one number, not three.
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")

# Devanagari proper, plus the Devanagari digits. Used by G4.
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")

# A web address stays in Latin in every language — "agrimachinery.nic.in" cannot
# be written in Devanagari and still work. G4 takes these out before it measures
# the script, or every scheme that names a portal fails for being honest.
_URL_RE = re.compile(
    r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:nic\.in|gov\.in|com|org|net|in)\b"
)


def _numbers(text: str) -> list[str]:
    """Every number in `text`, commas removed, as written.

    Kept as strings and not floats: "6000" and "6000.0" are different things to
    say out loud, and we only ever compare like with like.
    """
    out = []
    for raw in _NUMBER_RE.findall(text or ""):
        cleaned = raw.replace(",", "").rstrip(".")
        if cleaned:
            out.append(cleaned)
    return out


def _value(number: str) -> float:
    """The size of a number string, for the G1 spell-out allowance."""
    try:
        return float(number)
    except ValueError:  # pragma: no cover - the regex cannot produce this
        return 0.0


def _letters(text: str) -> str:
    """Letters only — no spaces, digits or punctuation.

    G4 measures the script of the *words*. Counting the digits and spaces would
    let a mostly-English line pass just because it is full of rupee amounts.
    """
    without_urls = _URL_RE.sub(" ", text or "")
    return "".join(
        c for c in unicodedata.normalize("NFC", without_urls) if c.isalpha()
    )


def gate_numbers(english: str, translated: str) -> list[str]:
    """G1 — the same numbers, allowing small ones to be spelled out."""
    reasons: list[str] = []
    en_numbers = _numbers(english)
    tr_numbers = _numbers(translated)

    remaining = list(tr_numbers)
    for number in en_numbers:
        if number in remaining:
            remaining.remove(number)
        elif _value(number) >= tunables.GATE_NUMBER_MIN:
            # Big enough that a translator would never write it as a word.
            reasons.append(f"number missing from the translation: {number}")

    # Anything left over was invented by the translator. Always a failure,
    # whatever its size — a number nobody wrote is a number nobody can trust.
    for number in remaining:
        reasons.append(f"number not in the English: {number}")
    return reasons


def gate_forbidden(text: str, lang: str) -> list[str]:
    """G2 — no second-person promise. The list lives in vocab.py, only there."""
    phrase = vocab.find_forbidden(text, lang)
    return [f"forbidden phrase: {phrase}"] if phrase else []


def gate_length(english: str, translated: str) -> list[str]:
    """G3 — a translation far longer than its English has drifted or padded.

    Measured in words, not characters. Devanagari spells a word with more
    characters than English does, so a character ratio flags honest translations:
    pm-kisan's three-item document list came back as 1.8x by character and 1.0x
    by word. Words are what the caller actually hears.

    Short text is exempt below GATE_LENGTH_MIN_WORDS. Turning a bare list
    ("Aadhaar Card.") into a spoken sentence has to add words, and on a line that
    short one added clause blows past any ratio.
    """
    en_words = len((english or "").split())
    if en_words < tunables.GATE_LENGTH_MIN_WORDS:
        return []
    ratio = len((translated or "").split()) / en_words
    if ratio > tunables.GATE_LENGTH_RATIO_MAX:
        return [f"length {ratio:.2f}x the English, over {tunables.GATE_LENGTH_RATIO_MAX}"]
    return []


def gate_script(english: str, translated: str) -> list[str]:
    """G4 — really Devanagari, and really translated."""
    reasons: list[str] = []
    letters = _letters(translated)
    if letters:
        share = len(_DEVANAGARI_RE.findall(letters)) / len(letters)
        if share < tunables.GATE_SCRIPT_MIN:
            reasons.append(
                f"only {share:.2f} Devanagari, under {tunables.GATE_SCRIPT_MIN}"
            )
    if (translated or "").strip() and translated.strip() == (english or "").strip():
        reasons.append("identical to the English")
    return reasons


def gate_complete(chunks: dict) -> list[str]:
    """G5 — every section, every language, non-empty.

    This is the one gate that looks across all three languages at once, so it is
    reported against the scheme rather than against a single language.
    """
    reasons: list[str] = []
    for lang in ALL_LANGS:
        texts = chunks.get(lang) or {}
        for field in SECTION_FIELDS:
            if not (texts.get(field) or "").strip():
                reasons.append(f"{lang}.{field} is empty")
    return reasons


def gate_language(chunks: dict, lang: str) -> dict[str, list[str]]:
    """Run G1–G4 over one language, field by field. Returns field -> reasons."""
    english = chunks.get(SOURCE_LANG) or {}
    texts = chunks.get(lang) or {}
    result: dict[str, list[str]] = {}

    for field in SECTION_FIELDS:
        en_text = (english.get(field) or "").strip()
        tr_text = (texts.get(field) or "").strip()
        reasons: list[str] = []

        if tr_text:
            reasons += gate_numbers(en_text, tr_text)
            reasons += gate_forbidden(tr_text, lang)
            reasons += gate_length(en_text, tr_text)
            reasons += gate_script(en_text, tr_text)
        # An empty text is G5's business, not G1–G4's. Reporting it twice would
        # make one problem look like five.

        result[field] = reasons
    return result


def gate_english(chunks: dict) -> dict[str, list[str]]:
    """The English is the yardstick, so only G2 applies to it.

    Numbers, length and script have nothing to compare against, and p3 already
    checked the English cards against the scraped source.
    """
    texts = chunks.get(SOURCE_LANG) or {}
    return {
        field: gate_forbidden((texts.get(field) or "").strip(), SOURCE_LANG)
        for field in SECTION_FIELDS
    }


def gate_scheme(record: dict) -> dict:
    """Every gate for one scheme. Returns the row written to gates.jsonl."""
    chunks = record.get("chunks") or {}

    complete = gate_complete(chunks)
    languages = {SOURCE_LANG: gate_english(chunks)}
    for lang in TARGET_LANGS:
        languages[lang] = gate_language(chunks, lang)

    # A language passes when none of its fields has a reason AND the scheme is
    # complete: a missing section is a reason not to speak that language either.
    lang_ok = {
        lang: not complete and all(not r for r in fields.values())
        for lang, fields in languages.items()
    }

    return {
        "scheme_id": record.get("scheme_id"),
        "complete": complete,
        "languages": languages,
        "lang_ok": lang_ok,
        "ok": all(lang_ok.values()),
    }


def run_gates(derived_dir=None, reports_dir=None) -> int:
    """Gate every scheme in schemes.jsonl. Writes gates.jsonl and a report."""
    derived_dir = Path(derived_dir) if derived_dir is not None else DERIVED_DIR
    reports_dir = Path(reports_dir) if reports_dir is not None else REPORTS_DIR

    schemes_path = derived_dir / "schemes.jsonl"
    if not schemes_path.exists():
        print(f"no schemes at {schemes_path}; run the derive step first")
        return 1

    with schemes_path.open(encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    rows = [gate_scheme(record) for record in records]

    gates_path = derived_dir / "gates.jsonl"
    tmp = gates_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(gates_path)

    ok_count = sum(1 for row in rows if row["ok"])
    per_lang = {
        lang: sum(1 for row in rows if row["lang_ok"].get(lang)) for lang in ALL_LANGS
    }
    failures = [
        {
            "scheme_id": row["scheme_id"],
            "complete": row["complete"],
            "languages": {
                lang: {field: reasons for field, reasons in fields.items() if reasons}
                for lang, fields in row["languages"].items()
            },
        }
        for row in rows
        if not row["ok"]
    ]

    reports_dir.mkdir(parents=True, exist_ok=True)
    with (reports_dir / "gates.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "schemes": len(rows),
                "ok": ok_count,
                "per_language": per_lang,
                "failures": failures,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"schemes: {len(rows)}")
    print(f"ok (all 3 languages): {ok_count}")
    for lang in ALL_LANGS:
        print(f"  {lang}: {per_lang[lang]}")
    if failures:
        print(f"failures: {len(failures)} (see {reports_dir / 'gates.json'})")
    return 0


if __name__ == "__main__":
    sys.exit(run_gates())
