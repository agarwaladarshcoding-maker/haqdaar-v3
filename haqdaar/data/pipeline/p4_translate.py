"""haqdaar/data/pipeline/p4_translate.py

Plan item 1.9 (D4) — Hindi and Marathi by Sarvam Translate, not Groq.

Groq's free daily budget is small and a live phone call needs it more than the pipeline does, so
the five spoken texts per scheme (the four cards plus the summary) are written once in English
and translated here. p2 no longer writes a Hindi or Marathi summary of its own: anything this
step does not produce stays empty, which is honest, rather than filled with ungated machine text.

Probed against the live API on 20 Sep 2026 (see .agent/NOTES.md):
  - model `sarvam-translate:v1`
  - `input` is capped at 2000 characters; 2001 returns a 400
  - `numerals_format="international"` keeps 6000 as 6000 instead of spelling it out

This file does not gate the result. p5 does that. What it does guarantee is that a text is either
translated in full or recorded as a failure — a half-translated card is never written out.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

import httpx
import yaml
from dotenv import load_dotenv

from haqdaar.contracts import tunables
from haqdaar.data.pipeline.p2_derive import (
    BASE_DIR,
    DERIVED_DIR,
    EXTRACT_CACHE_DIR,
    REPORTS_DIR,
    read_from_cache,
    write_to_cache,
)

# The five texts a call reads out, in the order p6 lays them down. `name` is NOT here: D4 keeps
# the Groq-written Hindi/Marathi names as they are and sends them to the owner's review sheet.
TRANSLATED_FIELDS = ("summary", "benefit_text", "who_can_apply", "documents", "how_to_apply")

# Sarvam's own language codes, not ours. Our snapshots say "hi"/"mr".
TARGET_LANGS = {"hi": "hi-IN", "mr": "mr-IN"}
SOURCE_LANG = "en-IN"


class TranslateError(Exception):
    """A translation could not be completed. The text is left empty rather than half-written."""

    # Set on the instances worth trying again: a timeout, a 429, a 5xx. A 402 or a 400 is not.
    transient: bool = False


def _transient(message: str) -> TranslateError:
    error = TranslateError(message)
    error.transient = True
    return error


class SarvamTranslator:
    """Single-caller client for Sarvam Translate.

    Counts characters as well as requests: Sarvam bills per character, so `make pipeline-cost`
    needs the character total, and a request count alone would hide a long text.
    """

    def __init__(self, api_key: Optional[str] = None, ledger_path: Optional[Path] = None):
        if api_key is None:
            load_dotenv()
            api_key = os.environ.get("SARVAM_API_KEY")
        if not api_key:
            raise ValueError("SARVAM_API_KEY must be set in environment or .env")
        self.api_key = api_key
        self.endpoint = "https://api.sarvam.ai/translate"
        self._last_call_time: float = 0.0
        self.ledger_path: Path = (
            Path(ledger_path) if ledger_path is not None
            else BASE_DIR / tunables.REPORTS_DIR / "sarvam_usage.jsonl"
        )
        self.requests: int = 0
        self.chars: int = 0

    def _write_ledger(self, slug: str, lang: str, field: str, chars: int) -> None:
        """Append one usage line. A ledger write must never break a translate run."""
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            "slug": slug,
            "lang": lang,
            "field": field,
            "chars": chars,
        }
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def translate(self, text: str, lang: str, slug: str = "", field: str = "") -> str:
        """Translate one English text into `lang` ("hi" or "mr").

        Anything longer than the API's 2000-character cap is split on sentence ends and sent in
        pieces. Cards are far shorter than that, so this is a guard, not the usual path.
        """
        text = (text or "").strip()
        if not text:
            return ""
        if lang not in TARGET_LANGS:
            raise TranslateError(f"unknown target language {lang!r}")

        parts = _split_for_limit(text, tunables.TRANSLATE_CHAR_LIMIT)
        out: list[str] = []
        for part in parts:
            out.append(self._one_request(part, lang, slug, field))
        return " ".join(piece for piece in out if piece).strip()

    def _one_request(self, text: str, lang: str, slug: str, field: str) -> str:
        """Send one piece, retrying only what is worth retrying.

        A real refusal (402 no credits, 400 bad input) is final: repeating it just spends time
        and would still fail. A timeout or a 5xx/429 is the network or the far end having a bad
        moment, and on the first real run exactly one read timed out — losing a whole scheme to
        that is what the retry is here to stop.
        """
        last_error: Optional[TranslateError] = None
        for attempt in range(tunables.TRANSLATE_MAX_ATTEMPTS):
            if attempt:
                time.sleep(tunables.TRANSLATE_RETRY_BACKOFF_S * attempt)
            try:
                return self._attempt(text, lang, slug, field)
            except TranslateError as e:
                if not getattr(e, "transient", False):
                    raise
                last_error = e
        assert last_error is not None
        raise TranslateError(
            f"{last_error} (gave up after {tunables.TRANSLATE_MAX_ATTEMPTS} attempts)"
        )

    def _attempt(self, text: str, lang: str, slug: str, field: str) -> str:
        # One caller at a time: space the calls so a burst never trips the rate limit.
        gap = time.monotonic() - self._last_call_time
        if gap < tunables.TRANSLATE_MIN_GAP_S:
            time.sleep(tunables.TRANSLATE_MIN_GAP_S - gap)

        payload = {
            "input": text,
            "source_language_code": SOURCE_LANG,
            "target_language_code": TARGET_LANGS[lang],
            "model": tunables.TRANSLATE_MODEL,
            # D4: digits stay in international numerals, so G1 can match the English multiset.
            "numerals_format": "international",
        }
        try:
            response = httpx.post(
                self.endpoint,
                headers={"api-subscription-key": self.api_key, "Content-Type": "application/json"},
                json=payload,
                timeout=tunables.TRANSLATE_TIMEOUT_S,
            )
        except Exception as e:
            raise _transient(f"sarvam request failed: {type(e).__name__}: {e}") from e
        finally:
            self._last_call_time = time.monotonic()

        if response.status_code != 200:
            message = f"sarvam returned {response.status_code}: {response.text[:200]}"
            if response.status_code == 429 or response.status_code >= 500:
                raise _transient(message)
            raise TranslateError(message)

        try:
            translated = response.json()["translated_text"]
        except Exception as e:
            raise TranslateError(f"sarvam sent no translated_text: {e}") from e
        if not isinstance(translated, str) or not translated.strip():
            raise TranslateError("sarvam sent an empty translation")

        self.requests += 1
        self.chars += len(text)
        self._write_ledger(slug, lang, field, len(text))
        return translated.strip()


def _split_for_limit(text: str, limit: int) -> list[str]:
    """Split `text` into pieces of at most `limit` characters, preferring sentence ends."""
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    rest = text
    while len(rest) > limit:
        window = rest[:limit]
        cut = max(window.rfind(". "), window.rfind("। "), window.rfind("\n"))
        if cut <= 0:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit  # one unbroken run of characters: cut it bluntly rather than loop forever
        else:
            cut += 1
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].lstrip()
    if rest:
        pieces.append(rest)
    return [p for p in pieces if p]


def translate_scheme(
    slug: str,
    source_sha256: str,
    english: dict[str, str],
    lang: str,
    translator: Optional[SarvamTranslator] = None,
    cache_dir: Optional[Path] = None,
) -> tuple[dict[str, str], bool]:
    """Translate one scheme's five texts into `lang`.

    Returns (texts, from_cache). The cache key carries p2's PROMPT_VERSIONS entry, so bumping
    `translate_hi`/`translate_mr` there (after a model or numeral-format change) invalidates the
    old rows instead of silently reusing them.
    """
    cache_dir = cache_dir if cache_dir is not None else EXTRACT_CACHE_DIR
    task = f"translate_{lang}"

    cached = read_from_cache(source_sha256, task, cache_dir)
    if cached is not None and all(field in cached for field in TRANSLATED_FIELDS):
        return {field: cached[field] for field in TRANSLATED_FIELDS}, True

    if translator is None:
        translator = SarvamTranslator()

    texts: dict[str, str] = {}
    for field in TRANSLATED_FIELDS:
        texts[field] = translator.translate(english.get(field, ""), lang, slug=slug, field=field)

    write_to_cache(source_sha256, task, texts, cache_dir)
    return texts, False


def _clear_untranslated(record: dict[str, Any], lang: Optional[str] = None) -> None:
    """Empty the Hindi/Marathi spoken texts this run did not produce.

    Before D4, p2 wrote Hindi and Marathi summaries straight from Groq with no gate (finding F2),
    and those rows are still sitting in schemes.jsonl. A scheme we decline to translate must not
    keep them: an ungated summary that says "पाँच लाख" where the source says 5,00,000 is exactly
    the lie this step removes. Empty is honest; stale is not. `name` is left alone, because D4
    keeps the Groq scheme names and sends them to the owner's review sheet instead.
    """
    chunks = record.setdefault("chunks", {})
    for target_lang in ((lang,) if lang else tuple(TARGET_LANGS)):
        texts = chunks.setdefault(target_lang, {})
        for field in TRANSLATED_FIELDS:
            texts[field] = ""
        record[f"{target_lang}_sections_origin"] = None
        record[f"{target_lang}_summary_origin"] = None


def _english_texts(record: dict[str, Any], card_row: Optional[dict[str, Any]]) -> dict[str, str]:
    """The English a scheme is translated from: p3's gated cards, plus p2's summary."""
    chunks = record.get("chunks") or {}
    english = dict(chunks.get("en") or {})
    out = {"summary": (english.get("summary") or "").strip()}
    cards = (card_row or {}).get("cards") or {}
    for field in TRANSLATED_FIELDS:
        if field == "summary":
            continue
        # The spoken card is the thing read on a call, never the raw source section.
        out[field] = (cards.get(field) or "").strip()
    return out


def run_translate(
    derived_dir: Optional[Path] = None,
    cards_path: Optional[Path] = None,
    reports_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
) -> int:
    """Translate every scheme's five texts into Hindi and Marathi, and write them back."""
    derived_dir = derived_dir if derived_dir is not None else DERIVED_DIR
    reports_dir = reports_dir if reports_dir is not None else REPORTS_DIR
    cache_dir = cache_dir if cache_dir is not None else EXTRACT_CACHE_DIR
    cards_path = cards_path if cards_path is not None else BASE_DIR / tunables.CARDS_FILE

    schemes_path = derived_dir / "schemes.jsonl"
    if not schemes_path.exists():
        print(f"no schemes at {schemes_path}; run the derive step first")
        return 1

    with open(schemes_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    cards_by_slug: dict[str, dict[str, Any]] = {}
    if cards_path.exists():
        with open(cards_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    cards_by_slug[row["slug"]] = row

    translator: Optional[SarvamTranslator] = None
    failures: list[dict[str, Any]] = []
    translated_count = 0

    for record in records:
        slug = record.get("scheme_id", "")
        card_row = cards_by_slug.get(slug)
        english = _english_texts(record, card_row)

        # A scheme whose cards failed p3's gates has nothing trustworthy to translate. Spending
        # money to render bad English into two more languages helps nobody.
        if card_row is not None and not card_row.get("ok", False):
            failures.append({"slug": slug, "error": "cards did not pass p3 gates; not translated"})
            _clear_untranslated(record)
            continue

        # The English chunk must BE the gated cards, not p2's raw sections. Without this the
        # call speaks the card while p5 gates the raw section, and every number the card
        # rightly dropped reads as "missing from the translation" (78 such false alarms on
        # the 12). One English, spoken and gated.
        en_chunk = (record.setdefault("chunks", {})).setdefault("en", {})
        for field, value in english.items():
            if value:
                en_chunk[field] = value

        for lang in TARGET_LANGS:
            try:
                if translator is None and read_from_cache(
                    record.get("source_sha256", ""), f"translate_{lang}", cache_dir,
                ) is None:
                    # The key is only needed once something misses cache, so a fully warm run
                    # needs no SARVAM_API_KEY at all.
                    translator = SarvamTranslator()
                texts, _from_cache = translate_scheme(
                    slug,
                    record.get("source_sha256", ""),
                    english,
                    lang,
                    translator=translator,
                    cache_dir=cache_dir,
                )
            except Exception as e:
                failures.append({"slug": slug, "lang": lang, "error": str(e)})
                _clear_untranslated(record, lang)
                continue

            chunks = record.setdefault("chunks", {})
            target = chunks.setdefault(lang, {})
            for field, value in texts.items():
                target[field] = value
            record[f"{lang}_sections_origin"] = "machine"
            record[f"{lang}_summary_origin"] = "machine"
            translated_count += 1

    tmp = schemes_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    tmp.replace(schemes_path)

    reports_dir.mkdir(parents=True, exist_ok=True)
    with open(reports_dir / "translate.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "schemes": len(records),
                "translated": translated_count,
                "requests": translator.requests if translator is not None else 0,
                "chars": translator.chars if translator is not None else 0,
                "failures": failures,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"schemes: {len(records)}")
    print(f"translated (scheme x language): {translated_count}")
    print(f"sarvam requests: {translator.requests if translator is not None else 0}")
    print(f"sarvam chars: {translator.chars if translator is not None else 0}")
    if failures:
        print(f"failures: {len(failures)} (see {reports_dir / 'translate.json'})")
    return 0


# --- the fixed lines -------------------------------------------------------------------------
#
# lines.yaml holds the English of every fixed line; Hindi and Marathi come from here and are
# written back into the same file. A line is only written if it passes the same four text gates
# p5 holds a scheme to (numbers, promises, length, script) and keeps every {slot} unchanged.
# A line that fails is left empty and named in the report, for a person to write by hand.

_SLOT_RE = re.compile(r"\{[a-z0-9_]+\}")


def _line_sha(english: str) -> str:
    """The cache key of one line is its English, so editing a line re-translates only that line."""
    return hashlib.sha256(english.encode("utf-8")).hexdigest()


def _pinned_ids(lines_path: Path) -> set[str]:
    """Lines an owner has corrected by hand. p4 never touches them."""
    with open(lines_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {
        line_id for line_id, value in (data.get("lines") or {}).items()
        if isinstance(value, dict) and value.get("pinned")
    }


def _restore_slot(english: str, translated: str) -> str:
    """Put a line's one {slot} name back when Sarvam translated it ({scheme_1} -> {स्कीम_1}).

    Only for a line with exactly one slot, where the match cannot be wrong. With two or more the
    order could have changed, so those are left for gate_line to stop.
    """
    en_slots = _SLOT_RE.findall(english)
    tr_slots = re.findall(r"\{[^{}]+\}", translated)
    if len(en_slots) == 1 and len(tr_slots) == 1 and tr_slots[0] != en_slots[0]:
        return translated.replace(tr_slots[0], en_slots[0])
    return translated


def gate_line(english: str, translated: str, lang: str) -> list[str]:
    """Why a translated line may not be spoken; empty if it may."""
    from haqdaar.data.pipeline import p5_gates

    reasons: list[str] = []
    if sorted(_SLOT_RE.findall(translated)) != sorted(_SLOT_RE.findall(english)):
        reasons.append("a {slot} was changed or lost")
    # Slots are filled with already-translated text at play time, so they are not judged here.
    en_bare = _SLOT_RE.sub(" ", english)
    tr_bare = _SLOT_RE.sub(" ", translated)
    reasons += p5_gates.gate_numbers(en_bare, tr_bare)
    reasons += p5_gates.gate_forbidden(tr_bare, lang)
    reasons += p5_gates.gate_length(en_bare, tr_bare)
    reasons += p5_gates.gate_script(en_bare, tr_bare)
    return reasons


def _write_line_texts(lines_path: Path, new: dict[str, dict[str, str]]) -> None:
    """Add `hi:`/`mr:` under each line's English, keeping the file's comments and order.

    A YAML round trip would drop every comment in the file, and the comments are the house style,
    so the new keys are inserted as text. A JSON string is a valid YAML double-quoted string.
    """
    with open(lines_path, "r", encoding="utf-8") as f:
        rows = f.read().split("\n")
    for line_id, texts in new.items():
        start = rows.index(f"  {line_id}:")
        end = start + 1
        while end < len(rows) and rows[end].startswith("    ") and not rows[end].strip().startswith("#"):
            end += 1
        added = [f"    {lang}: {json.dumps(text, ensure_ascii=False)}" for lang, text in texts.items()]
        rows[end:end] = added
    tmp = lines_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(rows))
    tmp.replace(lines_path)


def run_translate_lines(
    lines_path: Optional[Path] = None,
    reports_dir: Optional[Path] = None,
    cache_dir: Optional[Path] = None,
) -> int:
    """Translate every fixed line that has no Hindi or Marathi yet, gate it, and write it back."""
    from haqdaar.audio import lines as lines_mod

    lines_path = Path(lines_path) if lines_path is not None else lines_mod.LINES_PATH
    reports_dir = reports_dir if reports_dir is not None else REPORTS_DIR
    cache_dir = cache_dir if cache_dir is not None else EXTRACT_CACHE_DIR

    lines_mod.load_lines.cache_clear()
    lines = lines_mod.load_lines(lines_path)
    pinned = _pinned_ids(lines_path)

    translator: Optional[SarvamTranslator] = None
    new: dict[str, dict[str, str]] = {}
    failures: list[dict[str, Any]] = []

    for line_id, texts in lines.items():
        # One recording in all three languages; its Hindi and Marathi parts are written by hand.
        if line_id == lines_mod.TRILINGUAL_LINE_ID or line_id in pinned:
            continue
        english = texts["en"]
        sha = _line_sha(english)
        for lang in TARGET_LANGS:
            if texts.get(lang):
                continue
            task = f"line_translate_{lang}"
            try:
                cached = read_from_cache(sha, task, cache_dir)
                if cached is not None:
                    translated = cached["text"]
                else:
                    if translator is None:
                        translator = SarvamTranslator()
                    translated = translator.translate(english, lang, slug=line_id, field="line")
                    write_to_cache(sha, task, {"en": english, "text": translated}, cache_dir)
            except Exception as e:
                failures.append({"line": line_id, "lang": lang, "error": str(e)})
                continue
            translated = _restore_slot(english, translated)
            reasons = gate_line(english, translated, lang)
            if reasons:
                failures.append({"line": line_id, "lang": lang, "text": translated, "reasons": reasons})
                continue
            new.setdefault(line_id, {})[lang] = translated

    if new:
        _write_line_texts(lines_path, new)
        lines_mod.load_lines.cache_clear()

    written = sum(len(t) for t in new.values())
    reports_dir.mkdir(parents=True, exist_ok=True)
    with open(reports_dir / "lines_translate.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "written": written,
                "requests": translator.requests if translator is not None else 0,
                "chars": translator.chars if translator is not None else 0,
                "failures": failures,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"fixed lines written (line x language): {written}")
    print(f"sarvam requests: {translator.requests if translator is not None else 0}")
    print(f"sarvam chars: {translator.chars if translator is not None else 0}")
    if failures:
        print(f"failures: {len(failures)} (see {reports_dir / 'lines_translate.json'})")
    return 0


if __name__ == "__main__":
    code = run_translate()
    sys.exit(code or run_translate_lines())
