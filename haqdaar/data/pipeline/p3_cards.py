"""haqdaar/data/pipeline/p3_cards.py

Step 1.9 (D3) — spoken cards.

A scheme's source sections run to thousands of characters. Read aloud at about 13 characters a
second that is minutes per section, which no caller will sit through. This step turns each
scheme's four spoken sections into short English cards that a phone call can read out.

The model writes the cards; this file does not trust them. `gate_card_en` re-checks each card
against the raw source (numbers, facet numbers, forbidden phrases, length, word overlap) and
records every failure. There is no retry: a failing card is for a human to read in
`data_cache/reports/cards.json`, not for the pipeline to paper over.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from haqdaar.contracts import tunables, vocab
from haqdaar.data.pipeline.p2_derive import (
    BASE_DIR,
    DERIVED_DIR,
    EXTRACT_CACHE_DIR,
    RAW_CACHE_DIR,
    REPORTS_DIR,
    GroqClient,
    make_llm_client,
    read_from_cache,
    write_to_cache,
)
from haqdaar.data.pipeline.p6_snapshot import _parse_range_value

# The four sections a call reads out. `name` and `summary` already come short from p2.
CARD_FIELDS = ("benefit_text", "who_can_apply", "documents", "how_to_apply")

# Appended in code, never asked of the model: the paper list changes at the counter, and the
# honest thing to say on a call is that the centre has the full list.
CSC_SENTENCE_EN = "The CSC centre will tell you the full list of papers."

# The five raw sections, in the order the prompt shows them.
RAW_SECTIONS = ("benefits", "eligibility", "exclusions", "documents", "apply")

_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_WORD_RE = re.compile(r"[a-z]+")

# Common words carry no evidence, so counting them would let a fluent card pass on filler alone.
_STOP_WORDS = {
    "this", "that", "with", "from", "have", "will", "they", "their", "them", "which", "also",
    "into", "under", "scheme", "after", "before", "other", "there", "these", "those", "such",
    "must", "should", "would", "could", "about", "more", "than", "your", "when", "where", "what",
}

# The model is asked for CARD_TARGET_WORDS, not the hard cap. Asking for the cap itself put
# nine of the twelve schemes a few words over it (56..89 against a 55 cap); asking for a
# shorter target leaves the model room to run long and still land inside the gate.
CARD_TARGET_WORDS = 45

SYSTEM_PROMPT = (
    "You write short spoken cards about one Indian government scheme. They are read aloud on a phone call to people with little schooling.\n"
    "Use only facts that are in the SOURCE. Do not add any fact, amount, date, age, limit or condition that is not in the SOURCE.\n"
    "Write plain, short English sentences. No lists, no bullet marks, no brackets, no web links.\n"
    "Write every number with the same digits as the SOURCE. Do not change 200000 to 2 lakh or the other way.\n"
    "Never say \"you\" or \"your\". Do not say the listener is eligible, qualifies, will get, or will receive anything.\n"
    "Write about the scheme and the people in it instead:\n"
    "  not \"you will get 6000 rupees\" but \"the scheme pays 6000 rupees a year\";\n"
    "  not \"you will receive a loan\" but \"banks give a loan\";\n"
    "  not \"if you are a farmer\" but \"farmers who own land\".\n"
    f"HARD LIMIT: each of the four cards is at most {CARD_TARGET_WORDS} words. Count the words before answering. A card over the limit is thrown away.\n"
    "Leave out the least important detail to stay inside the limit. Four short cards beat four long ones.\n"
    "Return JSON only: {\"benefit_text\": \"...\", \"who_can_apply\": \"...\", \"documents\": \"...\", \"how_to_apply\": \"...\"}"
)

# One bounded re-ask. The model is told exactly which cards failed and why, and is asked to
# rewrite only those. There is still no silent papering over: if the retry also fails, the
# reasons go to the report as before.
RETRY_PROMPT_HEAD = (
    "Your last answer was rejected. These cards broke the rules:\n"
)
RETRY_PROMPT_TAIL = (
    "\nWrite all four cards again. Keep the cards that were fine as they were. "
    f"Fix the ones listed above. Every card must be at most {CARD_TARGET_WORDS} words "
    "and must never say \"you\" or \"your\".\n"
    "Return JSON only, the same four keys."
)


def build_retry_prompt(user_prompt: str, cards: dict[str, str], gates: dict[str, list[str]]) -> str:
    """The user prompt for the single re-ask, naming each failed card and its reasons."""
    problems = []
    for field in CARD_FIELDS:
        reasons = gates.get(field) or []
        if reasons:
            problems.append(f"{field}: {'; '.join(reasons)}\n  you wrote: {cards.get(field, '')}")
    return f"{user_prompt}\n\n{RETRY_PROMPT_HEAD}" + "\n".join(problems) + RETRY_PROMPT_TAIL


def _rule_text(record: dict[str, Any], box: str) -> tuple[str, str]:
    """(min, max) of a range facet as prompt text; 'none' when the scheme is unconstrained."""
    try:
        rng = _parse_range_value(record.get("scheme_id", ""), box, record.get(box))
    except ValueError:
        rng = None
    if rng is None:
        return "none", "none"
    lo, hi = rng
    return ("none" if lo is None else str(lo), "none" if hi is None else str(hi))


def _or_none(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return text if text else "none"


def build_card_prompts(raw: dict[str, Any], record: dict[str, Any]) -> tuple[str, str]:
    """Return (system, user) prompts for one scheme's four cards."""
    age_min, age_max = _rule_text(record, "age")
    income_min, income_max = _rule_text(record, "income_band")

    user_prompt = (
        f"SCHEME: {_or_none(record.get('scheme_name_en'))}\n"
        f"AGE RULE: {age_min} to {age_max} years\n"
        f"INCOME RULE: {income_min} to {income_max} rupees a year\n"
        "\n"
        "benefit_text = what the scheme gives, with the amounts.\n"
        "who_can_apply = who can apply, in 2 or 3 sentences. If there is an AGE RULE or INCOME RULE above, say those numbers.\n"
        "documents = only the 3 to 5 most important papers.\n"
        "how_to_apply = the first steps: where to go and what to take.\n"
        "\n"
        f"SOURCE BENEFITS:\n{_or_none(raw.get('benefits'))}\n"
        "\n"
        f"SOURCE ELIGIBILITY:\n{_or_none(raw.get('eligibility'))}\n"
        "\n"
        f"SOURCE EXCLUSIONS:\n{_or_none(raw.get('exclusions'))}\n"
        "\n"
        f"SOURCE DOCUMENTS:\n{_or_none(raw.get('documents'))}\n"
        "\n"
        f"SOURCE HOW TO APPLY:\n{_or_none(raw.get('apply'))}\n"
    )
    return SYSTEM_PROMPT, user_prompt


def derive_cards(
    raw: dict[str, Any],
    record: dict[str, Any],
    client: Optional[GroqClient] = None,
    cache_dir: Path = EXTRACT_CACHE_DIR,
) -> tuple[dict[str, str], bool]:
    """Four cards for one scheme. Returns (cards, from_cache).

    The CSC sentence is appended here, after the model, so it is never part of what the model
    is asked to justify and never double-appended from a cached answer.
    """
    sha = raw["source_sha256"]
    cached = read_from_cache(sha, "cards", cache_dir)
    if cached is None:
        if client is None:
            raise ValueError("Cache miss and no Groq client provided")
        system_prompt, user_prompt = build_card_prompts(raw, record)
        slug = raw.get("myscheme_slug", record.get("scheme_id", ""))
        answer = client.call(system_prompt, user_prompt, task="cards", slug=slug)
        cards = {field: str(answer.get(field, "") or "").strip() for field in CARD_FIELDS}

        # One re-ask when the first answer breaks a gate. Gating here (on the un-appended
        # cards, the same text gate_card_en judges after the CSC sentence is stripped) is what
        # lets the model see its own reasons. Whatever comes back is cached and gated again by
        # the caller, so a failing retry is reported, never hidden.
        gates = {f: gate_card_en(f, cards[f], raw, record) for f in CARD_FIELDS}
        if any(gates.values()):
            retry_prompt = build_retry_prompt(user_prompt, cards, gates)
            try:
                retry = client.call(system_prompt, retry_prompt, task="cards", slug=slug)
            except Exception:
                # A failed re-ask must not lose the first answer; it is still gated and reported.
                retry = None
            if retry is not None:
                retried = {f: str(retry.get(f, "") or "").strip() for f in CARD_FIELDS}
                retry_gates = {f: gate_card_en(f, retried[f], raw, record) for f in CARD_FIELDS}
                # Keep the retry only if it is genuinely better, per card. A rewrite that
                # fixes the length but invents a number must not replace a clean card.
                for field in CARD_FIELDS:
                    if retried[field] and not retry_gates[field] and gates[field]:
                        cards[field] = retried[field]

        write_to_cache(sha, "cards", cards, cache_dir)
        from_cache = False
    else:
        cards = {field: str(cached.get(field, "") or "").strip() for field in CARD_FIELDS}
        from_cache = True

    documents = cards["documents"]
    cards["documents"] = f"{documents} {CSC_SENTENCE_EN}".strip() if documents else CSC_SENTENCE_EN
    return cards, from_cache


def _numbers(text: str) -> list[str]:
    return [m.group(0).replace(",", "") for m in _NUMBER_RE.finditer(text)]


def _stem(word: str) -> str:
    """Crudest possible stem: drop a regular English ending.

    The overlap gate asks whether a card's words came from the source. Without this, apy's
    true card ("citizens ... payers ... aged") read as four unsourced words against a source
    saying "citizen ... payer ... age", and a correct card failed. Only the endings that
    change nothing about the meaning are stripped, so "income" and "incomplete" stay apart.
    """
    for suffix in ("ies", "es", "s", "ed", "ing"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            if suffix == "ies":
                return word[:-3] + "y"
            return word[: -len(suffix)]
    return word


def _content_words(text: str) -> set[str]:
    return {
        _stem(w)
        for w in _WORD_RE.findall(text.lower())
        if len(w) >= 4 and w not in _STOP_WORDS
    }


def _strip_csc(text: str) -> str:
    """The CSC sentence is ours, not the model's, so no gate is allowed to judge it."""
    return text.replace(CSC_SENTENCE_EN, "").strip()


def gate_card_en(
    field: str, text: str, raw: dict[str, Any], record: dict[str, Any]
) -> list[str]:
    """Every way this card fails the source. Empty list = the card is safe to speak."""
    reasons: list[str] = []
    body = _strip_csc(text)
    source = "\n".join(_or_none(raw.get(section)) for section in RAW_SECTIONS)

    source_numbers = set(_numbers(source))
    invented = [n for n in _numbers(body) if n not in source_numbers]
    if invented:
        reasons.append(f"numbers not in source: {', '.join(sorted(set(invented)))}")

    if field == "who_can_apply":
        card_numbers = set(_numbers(body))
        for box in ("age", "income_band"):
            try:
                rng = _parse_range_value(record.get("scheme_id", ""), box, record.get(box))
            except ValueError:
                rng = None
            if rng is None:
                continue
            for end, value in zip(("min", "max"), rng):
                if value is not None and str(value) not in card_numbers:
                    reasons.append(f"{box} {end} {value} missing from card")

    forbidden = vocab.find_forbidden(text, "en")
    if forbidden is not None:
        reasons.append(f"forbidden phrase: {forbidden}")

    words = len(body.split())
    if words > tunables.CARD_MAX_WORDS:
        reasons.append(f"{words} words, over the {tunables.CARD_MAX_WORDS}-word cap")

    card_words = _content_words(body)
    if card_words:
        shared = card_words & _content_words(source)
        overlap = len(shared) / len(card_words)
        if overlap < tunables.CARD_OVERLAP_MIN:
            missing = sorted(card_words - shared)
            reasons.append(
                f"overlap {overlap:.2f} under {tunables.CARD_OVERLAP_MIN} "
                f"(not in source: {', '.join(missing)})"
            )

    return reasons


def run_cards(
    derived_dir: Path | str = DERIVED_DIR,
    raw_dir: Path | str = RAW_CACHE_DIR,
    cache_dir: Path | str = EXTRACT_CACHE_DIR,
    reports_dir: Path | str = REPORTS_DIR,
) -> int:
    """Derive and gate cards for every derived scheme. Writes cards.jsonl and a report."""
    derived_dir = Path(derived_dir)
    raw_dir = Path(raw_dir)
    cache_dir = Path(cache_dir)
    reports_dir = Path(reports_dir)

    schemes_path = derived_dir / "schemes.jsonl"
    records: list[dict[str, Any]] = []
    with open(schemes_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    client: Optional[GroqClient] = None
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for record in records:
        slug = record.get("myscheme_slug") or record.get("scheme_id", "")
        try:
            with open(raw_dir / f"{slug}.json", "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            # A scheme we cannot read is reported and skipped; the other eleven still get cards.
            failures.append({"slug": slug, "error": f"raw source unreadable: {e}"})
            rows.append({
                "slug": slug,
                "source_sha256": record.get("source_sha256", ""),
                "prompt_version": None,
                "cards": {},
                "gates": {},
                "ok": False,
            })
            continue

        try:
            # The key is only needed once something actually misses cache, so a fully warm
            # run works with no GROQ_API_KEY at all.
            if client is None and read_from_cache(raw["source_sha256"], "cards", cache_dir) is None:
                client = make_llm_client()
            cards, _from_cache = derive_cards(raw, record, client=client, cache_dir=cache_dir)

        except Exception as e:
            failures.append({"slug": slug, "error": f"card derivation failed: {e}"})
            rows.append({
                "slug": slug,
                "source_sha256": raw.get("source_sha256", ""),
                "prompt_version": None,
                "cards": {},
                "gates": {},
                "ok": False,
            })
            continue

        gates = {field: gate_card_en(field, cards[field], raw, record) for field in CARD_FIELDS}
        ok = all(not reasons for reasons in gates.values())
        rows.append({
            "slug": slug,
            "source_sha256": raw["source_sha256"],
            "prompt_version": 1,
            "cards": cards,
            "gates": gates,
            "ok": ok,
        })
        if not ok:
            failures.append({
                "slug": slug,
                "gates": {f: r for f, r in gates.items() if r},
            })

    cards_path = BASE_DIR / tunables.CARDS_FILE
    cards_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cards_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    reports_dir.mkdir(parents=True, exist_ok=True)
    ok_count = sum(1 for row in rows if row["ok"])
    with open(reports_dir / "cards.json", "w", encoding="utf-8") as f:
        json.dump(
            {"schemes": len(rows), "ok": ok_count, "failures": failures},
            f,
            indent=2,
            ensure_ascii=False,
        )

    requests = client.requests if client is not None else 0
    print(f"schemes: {len(rows)}")
    print(f"ok: {ok_count}")
    print(f"groq requests: {requests}")
    return 0


if __name__ == "__main__":
    sys.exit(run_cards())
