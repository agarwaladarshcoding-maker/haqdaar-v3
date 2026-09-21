"""tests/test_cards.py

Step 1.9 — spoken cards (p3_cards.py). Every test runs offline: Groq is mocked the same way
tests/test_groq_ledger.py mocks it.
"""
import json
from pathlib import Path

import httpx
import pytest

from haqdaar.contracts import tunables
from haqdaar.data.pipeline import p3_cards
from haqdaar.data.pipeline.p2_derive import GroqClient
from haqdaar.data.pipeline.p3_cards import (
    CARD_FIELDS,
    CSC_SENTENCE_EN,
    build_card_prompts,
    derive_cards,
    gate_card_en,
    run_cards,
)


class _FakeResponse:
    def __init__(self, payload: dict):
        self.status_code = 200
        self.headers: dict = {}
        self.text = json.dumps(payload)
        self._payload = payload

    def json(self):
        return self._payload


class _FakeHttpxClient:
    def __init__(self, payloads: list[dict], counter: dict):
        # A list so a test can give the first call and the re-ask different answers. The last
        # payload repeats, which keeps the single-answer tests unchanged.
        self._payloads = payloads
        self._counter = counter

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def post(self, *args, **kwargs):
        index = min(self._counter["posts"], len(self._payloads) - 1)
        self._counter["posts"] += 1
        return _FakeResponse(self._payloads[index])


def _patch_groq(monkeypatch: pytest.MonkeyPatch, *cards: dict) -> dict:
    """Answer Groq calls with `cards` in order, the last one repeating.

    Returns a counter of HTTP posts made.
    """
    counter = {"posts": 0}
    payloads = [
        {
            "choices": [{"message": {"content": json.dumps(c)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        for c in cards
    ]
    monkeypatch.setattr(
        httpx, "Client", lambda timeout=None: _FakeHttpxClient(payloads, counter)
    )
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr(tunables, "GROQ_POLITE_DELAY_S", 0.0)
    return counter


# A source whose words the good cards below are built from.
RAW = {
    "myscheme_slug": "demo-scheme",
    "source_sha256": "a" * 64,
    "benefits": "The scheme gives farmers 6000 rupees every year in three equal payments.",
    "eligibility": "Farmers aged 18 to 40 years who own farmland can apply for this help.",
    "exclusions": "Income tax payers cannot apply.",
    "documents": "Aadhaar card, bank passbook and land papers are needed.",
    "apply": "Visit the nearest CSC centre with your papers and fill the form.",
}

RECORD = {
    "scheme_id": "demo-scheme",
    "myscheme_slug": "demo-scheme",
    "source_sha256": "a" * 64,
    "scheme_name_en": "Demo Farmer Scheme",
    "age": {"min": 18, "max": 40},
    "income_band": "ANY",
}

GOOD_CARDS = {
    "benefit_text": "The scheme gives farmers 6000 rupees every year in three equal payments.",
    "who_can_apply": "Farmers aged 18 to 40 years who own farmland can apply.",
    "documents": "Aadhaar card, bank passbook and land papers are needed.",
    "how_to_apply": "Visit the nearest CSC centre with your papers and fill the form.",
}


def _write_inputs(tmp_path: Path, records=None, raws=None) -> tuple[Path, Path, Path, Path]:
    derived = tmp_path / "derived"
    raw_dir = tmp_path / "raw"
    cache = tmp_path / "extract"
    reports = tmp_path / "reports"
    for d in (derived, raw_dir, cache, reports):
        d.mkdir(parents=True, exist_ok=True)

    records = records if records is not None else [RECORD]
    raws = raws if raws is not None else [RAW]
    with open(derived / "schemes.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    for raw in raws:
        with open(raw_dir / f"{raw['myscheme_slug']}.json", "w", encoding="utf-8") as f:
            json.dump(raw, f)
    return derived, raw_dir, cache, reports


# --- gates ---------------------------------------------------------------


def test_good_cards_pass_every_gate():
    for field in CARD_FIELDS:
        text = GOOD_CARDS[field]
        if field == "documents":
            text = f"{text} {CSC_SENTENCE_EN}"
        assert gate_card_en(field, text, RAW, RECORD) == []


def test_number_not_in_source_fails():
    reasons = gate_card_en(
        "benefit_text", "The scheme gives farmers 9000 rupees every year.", RAW, RECORD
    )
    assert any("9000" in r for r in reasons)


def test_number_in_source_with_commas_passes():
    raw = dict(RAW, benefits="The scheme gives farmers 1,20,000 rupees every year.")
    reasons = gate_card_en(
        "benefit_text", "The scheme gives farmers 120000 rupees every year.", raw, RECORD
    )
    assert not any("numbers not in source" in r for r in reasons)


def test_missing_facet_number_fails_who_can_apply():
    reasons = gate_card_en(
        "who_can_apply", "Farmers who own farmland can apply for this help.", RAW, RECORD
    )
    assert any("age min 18" in r for r in reasons)
    assert any("age max 40" in r for r in reasons)


def test_facet_numbers_only_checked_on_who_can_apply():
    reasons = gate_card_en(
        "benefit_text", "The scheme gives farmers 6000 rupees every year.", RAW, RECORD
    )
    assert not any("age min" in r for r in reasons)


def test_forbidden_phrase_fails():
    text = "You are eligible for 6000 rupees every year."
    reasons = gate_card_en("benefit_text", text, RAW, RECORD)
    assert any("forbidden phrase" in r for r in reasons)


def test_over_length_fails():
    long_card = " ".join(["farmers"] * (tunables.CARD_MAX_WORDS + 5))
    reasons = gate_card_en("benefit_text", long_card, RAW, RECORD)
    assert any("word cap" in r for r in reasons)


def test_low_overlap_fails():
    text = "Cricket players receive brilliant trophies during marvellous tournaments abroad."
    reasons = gate_card_en("benefit_text", text, RAW, RECORD)
    assert any("overlap" in r for r in reasons)


def test_csc_sentence_is_not_judged_by_the_gates():
    """The CSC sentence is ours, so its own words must not be counted against the source."""
    reasons = gate_card_en("documents", CSC_SENTENCE_EN, RAW, RECORD)
    assert reasons == []


# --- derive --------------------------------------------------------------


def test_csc_sentence_appended_once_on_miss_and_on_cache(tmp_path: Path, monkeypatch):
    counter = _patch_groq(monkeypatch, GOOD_CARDS)
    cache = tmp_path / "extract"

    cards, from_cache = derive_cards(RAW, RECORD, client=GroqClient(), cache_dir=cache)
    assert from_cache is False
    assert cards["documents"].count(CSC_SENTENCE_EN) == 1
    assert counter["posts"] == 1

    # No client at all: a cached scheme must not need one.
    cards2, from_cache2 = derive_cards(RAW, RECORD, cache_dir=cache)
    assert from_cache2 is True
    assert cards2["documents"].count(CSC_SENTENCE_EN) == 1
    assert counter["posts"] == 1, "a cached scheme must make no request"


def test_cached_file_does_not_contain_the_csc_sentence(tmp_path: Path, monkeypatch):
    _patch_groq(monkeypatch, GOOD_CARDS)
    cache = tmp_path / "extract"
    derive_cards(RAW, RECORD, client=GroqClient(), cache_dir=cache)
    cached = json.loads(next(cache.glob("*_cards_v*.json")).read_text(encoding="utf-8"))
    assert CSC_SENTENCE_EN not in cached["documents"]


def test_prompt_carries_the_age_rule_and_every_source_section():
    system, user = build_card_prompts(RAW, RECORD)
    assert f"at most {p3_cards.CARD_TARGET_WORDS} words" in system
    assert "AGE RULE: 18 to 40 years" in user
    assert "INCOME RULE: none to none rupees a year" in user
    for section in ("benefits", "eligibility", "exclusions", "documents", "apply"):
        assert RAW[section] in user


# --- run_cards -----------------------------------------------------------


def test_run_cards_writes_one_line_per_scheme_and_warm_run_makes_no_request(
    tmp_path: Path, monkeypatch, capsys
):
    counter = _patch_groq(monkeypatch, GOOD_CARDS)
    derived, raw_dir, cache, reports = _write_inputs(tmp_path)
    cards_file = tmp_path / "cards.jsonl"
    monkeypatch.setattr(p3_cards, "BASE_DIR", tmp_path)
    monkeypatch.setattr(tunables, "CARDS_FILE", "cards.jsonl")

    assert run_cards(derived, raw_dir, cache, reports) == 0
    rows = [json.loads(l) for l in cards_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["ok"] is True
    assert rows[0]["slug"] == "demo-scheme"
    assert rows[0]["prompt_version"] == 1
    assert set(rows[0]["cards"]) == set(CARD_FIELDS)
    assert counter["posts"] == 1
    assert "groq requests: 1" in capsys.readouterr().out

    # Warm run: same inputs, nothing should reach the network.
    assert run_cards(derived, raw_dir, cache, reports) == 0
    assert counter["posts"] == 1
    assert "groq requests: 0" in capsys.readouterr().out


def test_one_scheme_failing_still_writes_the_others(tmp_path: Path, monkeypatch):
    _patch_groq(monkeypatch, GOOD_CARDS)
    broken = dict(RECORD, scheme_id="missing-raw", myscheme_slug="missing-raw")
    derived, raw_dir, cache, reports = _write_inputs(
        tmp_path, records=[broken, RECORD], raws=[RAW]
    )
    cards_file = tmp_path / "cards.jsonl"
    monkeypatch.setattr(p3_cards, "BASE_DIR", tmp_path)
    monkeypatch.setattr(tunables, "CARDS_FILE", "cards.jsonl")

    assert run_cards(derived, raw_dir, cache, reports) == 0
    rows = [json.loads(l) for l in cards_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 2
    by_slug = {r["slug"]: r for r in rows}
    assert by_slug["missing-raw"]["ok"] is False
    assert by_slug["demo-scheme"]["ok"] is True

    report = json.loads((reports / "cards.json").read_text(encoding="utf-8"))
    assert report["schemes"] == 2
    assert report["ok"] == 1
    assert any(f["slug"] == "missing-raw" for f in report["failures"])


def test_a_gate_failure_is_re_asked_once_and_then_reported(tmp_path: Path, monkeypatch):
    """One re-ask, and no more. A card that fails twice is reported, never papered over."""
    bad = dict(GOOD_CARDS, benefit_text="The scheme gives farmers 9999 rupees every year.")
    counter = _patch_groq(monkeypatch, bad)  # the re-ask answers just as badly
    derived, raw_dir, cache, reports = _write_inputs(tmp_path)
    cards_file = tmp_path / "cards.jsonl"
    monkeypatch.setattr(p3_cards, "BASE_DIR", tmp_path)
    monkeypatch.setattr(tunables, "CARDS_FILE", "cards.jsonl")

    assert run_cards(derived, raw_dir, cache, reports) == 0
    row = json.loads(cards_file.read_text(encoding="utf-8").splitlines()[0])
    assert row["ok"] is False
    assert any("9999" in r for r in row["gates"]["benefit_text"])
    assert counter["posts"] == 2, "exactly one re-ask, not a retry loop"


def test_a_good_re_ask_replaces_the_failed_card(tmp_path: Path, monkeypatch):
    over_cap = dict(GOOD_CARDS, benefit_text=GOOD_CARDS["benefit_text"] + " also " * 60)
    counter = _patch_groq(monkeypatch, over_cap, GOOD_CARDS)
    derived, raw_dir, cache, reports = _write_inputs(tmp_path)
    cards_file = tmp_path / "cards.jsonl"
    monkeypatch.setattr(p3_cards, "BASE_DIR", tmp_path)
    monkeypatch.setattr(tunables, "CARDS_FILE", "cards.jsonl")

    assert run_cards(derived, raw_dir, cache, reports) == 0
    row = json.loads(cards_file.read_text(encoding="utf-8").splitlines()[0])
    assert row["ok"] is True
    assert row["cards"]["benefit_text"] == GOOD_CARDS["benefit_text"]
    assert counter["posts"] == 2


def test_a_worse_re_ask_does_not_replace_a_clean_card(tmp_path: Path, monkeypatch):
    """The re-ask rewrites all four cards. A card that was already fine must survive."""
    over_cap = dict(GOOD_CARDS, benefit_text=GOOD_CARDS["benefit_text"] + " also " * 60)
    spoiled = dict(GOOD_CARDS, documents="Papers such as 4242 and 7777 are needed.")
    counter = _patch_groq(monkeypatch, over_cap, spoiled)
    cache = tmp_path / "extract"

    cards, _ = derive_cards(RAW, RECORD, client=GroqClient(), cache_dir=cache)
    assert "4242" not in cards["documents"], "an invented number must not ride in on a re-ask"
    assert cards["benefit_text"] == GOOD_CARDS["benefit_text"]
    assert counter["posts"] == 2


def test_the_retry_prompt_names_the_failed_card_and_its_reason():
    gates = {"benefit_text": ["78 words, over the 55-word cap"], "who_can_apply": [],
             "documents": [], "how_to_apply": []}
    prompt = p3_cards.build_retry_prompt("USER", GOOD_CARDS, gates)
    assert "USER" in prompt
    assert "benefit_text" in prompt
    assert "78 words" in prompt
    assert "who_can_apply:" not in prompt, "a card that passed is not named as a problem"


def test_a_plural_of_a_source_word_counts_as_overlap():
    """apy's true card said "citizens/payers/aged" where the source says "citizen/payer/age"."""
    raw = dict(RAW, exclusions="Any citizen who is an income tax payer cannot join.")
    text = "People aged 18 to 40 can join. Citizens who are income tax payers cannot join."
    assert not any("overlap" in r for r in gate_card_en("who_can_apply", text, raw, RECORD))


def test_stemming_does_not_merge_different_words():
    assert p3_cards._stem("income") == "income"
    assert p3_cards._stem("bus") == "bus"        # too short to strip
    assert p3_cards._stem("farmers") == "farmer"
    assert p3_cards._stem("families") == "family"
