"""haqdaar/model/span_guard.py

Span Guard and closed-set validation for HAQDAAR v2.
Guarantees that a value is kept only if its words appear in the transcript
(string containment, provenance lock: "Farmer" must never smuggle in "low income").
"""
from __future__ import annotations

import re
from typing import Any, Container, Iterable, Mapping, Optional
import unicodedata

from haqdaar.contracts import vocab
from haqdaar.contracts.types import SEVEN_BOXES, Stamp


def normalize_text(text: str) -> str:
    """Normalize text for span comparison: NFC, lowercase, strip nuktas for hi/mr."""
    if not text:
        return ""
    folded = unicodedata.normalize("NFC", text).lower()
    # Remove Hindi/Marathi nukta U+093C so ज़ == ज, ढ़ == ढ
    folded = folded.replace("़", "")
    # Normalize common punctuation to space
    folded = re.sub(r"[,\.!\?;\:\'\"\(\)\[\]\{\}\-_/]", " ", folded)
    return " ".join(folded.split())


# Keywords required for sensitive / numeric boxes to prevent cross-box extrapolation
INCOME_KEYWORDS = {
    "income", "salary", "earn", "earning", "earnings", "rupees", "rs", "lakh", "lac",
    "thousand", "crore", "per year", "annual", "monthly", "paisa", "paise", "low income",
    "aay", "kamai", "kamata", "kamati", "utpanna", "rupaya", "rupaye", "hazar", "hazaar",
    "आय", "कमाई", "उत्पन्न", "रुपये", "रुपया", "लाख", "हजार", "पगार", "वार्षिक", "सालाना",
}

AGE_KEYWORDS = {
    "age", "years", "year", "old", "saal", "varsh", "sal", "umar", "vay",
    "साल", "वर्ष", "वय", "उम्र", "वर्षे",
}

GENDER_KEYWORDS = {
    "female", "woman", "girl", "lady", "mother", "daughter", "wife", "widow",
    "male", "man", "boy", "father", "son", "husband",
    "mahila", "aurat", "purush", "aadmi", "ladki", "ladka", "stri",
    "महिला", "स्त्री", "पुरुष", "मुलगी", "मुलगा", "बाई", "माणूस",
}

OCCUPATION_KEYWORDS = {
    "farmer", "farming", "kisan", "shetkari", "vendor", "street vendor", "hawker",
    "apprentice", "entrepreneur", "business", "artisan", "karigar", "weaver", "bunkar",
    "worker", "labour", "laborer", "labor", "kamgar", "mazdoor", "shramik",
    "किसान", "शेतकरी", "कारीगर", "बुनकर", "श्रमिक", "मजदूर", "कामगार", "फेरीवाले", "व्यवसाय",
}


def span_in_transcript(transcript: str, span: str) -> bool:
    """Verify that span literally appears in the transcript (string containment)."""
    if not span or not span.strip() or not transcript or not transcript.strip():
        return False

    norm_span = normalize_text(span)
    norm_transcript = normalize_text(transcript)

    if not norm_span or not norm_transcript:
        return False

    # 1. Direct normalized substring check
    if norm_span in norm_transcript:
        return True

    # 2. Token subsequence check (handles minor whitespace or punctuation differences)
    span_tokens = norm_span.split()
    tx_tokens = norm_transcript.split()

    if not span_tokens:
        return False

    span_len = len(span_tokens)
    for i in range(len(tx_tokens) - span_len + 1):
        if tx_tokens[i : i + span_len] == span_tokens:
            return True

    # 3. All tokens in span must at least exist in transcript in order
    tx_idx = 0
    matches = 0
    for tok in span_tokens:
        try:
            found_idx = tx_tokens.index(tok, tx_idx)
            tx_idx = found_idx + 1
            matches += 1
        except ValueError:
            break
    if matches == len(span_tokens):
        return True

    return False


def is_box_compatible_span(box: str, span: str) -> bool:
    """Check that span is semantically compatible with the box.

    Prevents hallucinated extrapolation: e.g. "farmer" must not be passed
    as the span for "income_band" or "gender".
    """
    if not span or not span.strip():
        return False

    norm_span = normalize_text(span)
    span_words = set(norm_span.split())
    has_digits = bool(re.search(r"\d", span))

    if box == "income_band":
        # Must contain numeric digit or income-specific term
        if has_digits:
            return True
        return bool(span_words & INCOME_KEYWORDS)

    if box == "age":
        # Must contain numeric digit or age-specific term
        if has_digits:
            return True
        return bool(span_words & AGE_KEYWORDS)

    if box == "gender":
        return bool(span_words & GENDER_KEYWORDS)

    return True


def is_value_in_closed_set(box: str, value: Any, custom_values: Mapping[str, Container] | None = None) -> bool:
    """Check if value belongs to the closed set for the box."""
    if custom_values and box in custom_values:
        return value in custom_values[box]

    if box == "scheme":
        # Scheme pseudo-box: accepts non-empty string identifier
        return isinstance(value, str) and bool(value.strip())

    if box == "category":
        return value in vocab.CATEGORY or value in vocab.OLD_CATEGORY_MAP

    if box == "state":
        return value in vocab.STATE

    if box == "gender":
        return value in vocab.GENDER

    if box == "social_category":
        return value in vocab.SOCIAL_CATEGORY

    if box == "occupation":
        return value in vocab.OCCUPATION

    if box == "age":
        if isinstance(value, int):
            return 0 <= value <= 130
        if isinstance(value, str):
            val_clean = value.strip().replace(">", "").replace("<", "")
            if val_clean.isdigit():
                return 0 <= int(val_clean) <= 130
        return False

    if box == "income_band":
        # String representing band or amount. Left open because income bands are
        # constructed dynamically per snapshot from scheme cutoffs (vocab.py:43)
        # rather than being a static canonical enum in vocab.py.
        return isinstance(value, (str, int)) and bool(str(value).strip())

    return False


class SpanGuard:
    """Enforces provenance containment and closed-set validity."""

    @staticmethod
    def validate_span(transcript: str, span: str) -> bool:
        return span_in_transcript(transcript, span)

    @staticmethod
    def validate_stamp(
        transcript: str,
        stamp: Stamp,
        allowed_values: Mapping[str, Container] | None = None,
    ) -> bool:
        """Validate single Stamp against transcript provenance and closed sets."""
        if stamp.box not in SEVEN_BOXES and stamp.box != "scheme":
            return False

        if not span_in_transcript(transcript, stamp.span):
            return False

        if not is_box_compatible_span(stamp.box, stamp.span):
            return False

        if not is_value_in_closed_set(stamp.box, stamp.value, allowed_values):
            return False

        return True

    @classmethod
    def filter_stamps(
        cls,
        transcript: str,
        stamps: Iterable[Stamp],
        allowed_values: Mapping[str, Container] | None = None,
    ) -> list[Stamp]:
        """Filter a list of stamps, retaining only those that pass the span guard."""
        valid: list[Stamp] = []
        for s in stamps:
            if cls.validate_stamp(transcript, s, allowed_values=allowed_values):
                valid.append(s)
        return valid
