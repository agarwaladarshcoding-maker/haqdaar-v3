"""tests/test_door_a.py

Unit tests and offline top-1 accuracy verification for Door A:
1. Normalization and Devanagari transliteration.
2. Candidate count routing:
   - 1 match -> action="read"
   - 2 matches -> action="keypad_pick"
   - >=3 matches -> action="downgrade_to_b"
   - 0 matches -> action="downgrade_to_b"
3. LLM top-10 shortlist.
4. Offline top-1 benchmark across 90 utterances (3 forms × 30 schemes) >= 95%.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from haqdaar.data.door_a_sources import load_repo_scheme_entries, quarantined_slugs
from haqdaar.engine.door_a import (
    DoorA,
    DoorAResult,
    SchemeEntry,
    devanagari_to_latin,
    normalize_text,
    unmatched_content,
)

BASE_DIR = Path(__file__).resolve().parent.parent


def test_devanagari_to_latin():
    """Verify phonetic transliteration of Devanagari characters and abbreviations."""
    assert "pm" in devanagari_to_latin("पीएम किसान")
    assert "kisan" in devanagari_to_latin("पीएम किसान")
    assert "atal" in devanagari_to_latin("अटल")
    assert "pension" in devanagari_to_latin("पेंशन")
    assert "mgnrega" in devanagari_to_latin("मनरेगा")
    assert "kcc" in devanagari_to_latin("केसीसी")
    assert "mudra" in devanagari_to_latin("मुद्रा")
    assert "ayushman" in devanagari_to_latin("आयुष्मान")
    assert "bima" in devanagari_to_latin("विमा")


def test_normalize_text():
    """Verify text normalization, punctuation removal, and Devanagari danda stripping."""
    norm = normalize_text("  मुझे पीएम किसान योजना चाहिए।!  ")
    assert norm == "मुझे पीएम किसान योजना चाहिए"
    assert "।" not in norm
    assert "!" not in norm

    norm_mr = normalize_text("कृपया मला सांगा॥")
    assert "॥" not in norm_mr
    assert norm_mr == "कृपया मला सांगा"


def test_door_a_single_match_read():
    """1 match -> action='read', scheme_ids has length 1."""
    door_a = DoorA(scheme_entries=load_repo_scheme_entries())
    res = door_a.match("I want to apply for PM Kisan Samman Nidhi", lang="en")
    assert res.action == "read"
    assert res.scheme_ids == ("pm-kisan",)
    assert res.confidence > 0.5
    assert len(res.shortlist) <= 10
    assert "pm-kisan" in res.shortlist


def test_door_a_disambiguation_keypad_pick():
    """2 tied candidates -> action='keypad_pick', scheme_ids has length 2."""
    entries = [
        SchemeEntry(slug="scheme-a", aliases=["kisan credit"]),
        SchemeEntry(slug="scheme-b", aliases=["kisan credit"]),
        SchemeEntry(slug="scheme-c", aliases=["other benefit"]),
    ]
    custom_matcher = DoorA(scheme_entries=entries)
    res = custom_matcher.match("kisan credit")
    assert res.action == "keypad_pick"
    assert set(res.scheme_ids) == {"scheme-a", "scheme-b"}


def test_door_a_downgrade_on_three_or_more_candidates():
    """>=3 ambiguous candidates -> action='downgrade_to_b'."""
    entries = [
        SchemeEntry(slug="scheme-a", aliases=["bima scheme"]),
        SchemeEntry(slug="scheme-b", aliases=["bima scheme"]),
        SchemeEntry(slug="scheme-c", aliases=["bima scheme"]),
    ]
    custom_matcher = DoorA(scheme_entries=entries)
    res = custom_matcher.match("bima scheme")
    assert res.action == "downgrade_to_b"
    assert len(res.scheme_ids) >= 3


def test_door_a_downgrade_on_zero_candidates():
    """0 matches -> action='downgrade_to_b', scheme_ids is empty."""
    door_a = DoorA(scheme_entries=load_repo_scheme_entries())
    res = door_a.match("I am a 19 year old student looking for scholarships")
    assert res.action == "downgrade_to_b"
    assert res.scheme_ids == ()


def test_door_a_top_10_shortlist():
    """The shortlist returned for LLM has at most 10 items."""
    door_a = DoorA(scheme_entries=load_repo_scheme_entries())
    shortlist = door_a.shortlist("pension scheme", k=10)
    assert isinstance(shortlist, tuple)
    assert 0 < len(shortlist) <= 10


class MockCorpus:
    def __init__(self):
        self._scheme_ids = ("S1", "S2")
        self._alias_maps = {
            "en": {"kcc": ("S1",), "atal pension": ("S2",)},
            "hi": {"केसीसी": ("S1",)},
            "mr": {},
        }

    def alias_lookup(self, text: str, lang: str = "en") -> tuple[str, ...]:
        return self._alias_maps.get(lang, {}).get(text.strip().lower(), ())

    def alias_set(self, lang: str) -> dict[str, tuple[str, ...]]:
        return self._alias_maps.get(lang, {})

    def specificity(self, scheme_ix: int) -> int:
        return 2


def test_door_a_corpus_exact_match():
    """Corpus fast-path lookup triggers directly when alias matches in corpus."""
    fake_corpus = MockCorpus()
    door_a = DoorA.from_corpus(fake_corpus)
    res = door_a.match("kcc", lang="en")
    assert res.confidence == 1.0
    assert res.scheme_ids == ("S1",)
    assert res.action == "read"


def test_door_a_offline_benchmark_accuracy():
    """Verify offline top-1 accuracy on 3 forms × 27 servable schemes >= 95%.

    Quarantined schemes have no fixture utterances (unservable: Door B's job).
    Single-token namings ("mudra") downgrade here — the model arbitrates
    those live (T12 search #2).
    """
    fixtures_path = BASE_DIR / "fixtures" / "door_a_utterances.json"
    assert fixtures_path.exists(), "fixtures/door_a_utterances.json missing"

    utterances = json.loads(fixtures_path.read_text(encoding="utf-8"))
    assert len(utterances) == 81, f"Expected 81 utterances, got {len(utterances)}"

    door_a = DoorA(scheme_entries=load_repo_scheme_entries())
    hits = 0
    for u in utterances:
        expected = u["slug"]
        res = door_a.match(u["transcript"], lang=u["lang"])
        pred = res.scheme_ids[0] if (res.action == "read" and res.scheme_ids) else ""
        if pred == expected and res.action == "read":
            hits += 1

    accuracy = hits / len(utterances)
    assert accuracy >= 0.95, f"Door A offline accuracy {accuracy*100:.2f}% fell below 95% threshold"


def test_repo_entries_exclude_quarantined_slugs():
    """The roster loader never presents unservable (quarantined) schemes."""
    quarantined = quarantined_slugs()
    assert quarantined == {"ab-pmjay", "pmsby", "pm-sym"}
    slugs = {e.slug for e in load_repo_scheme_entries()}
    assert not (slugs & quarantined)
    assert len(slugs) == 27


def test_door_a_single_token_overlap_downgrades():
    """A single shared word ("agriculture", "krishi") is a need-statement, not
    a naming: the code pass must downgrade so the model arbitrates (T12 #2)."""
    door_a = DoorA(scheme_entries=load_repo_scheme_entries())
    for lang, text in (("en", "I am looking for agriculture schemes"),
                       ("hi", "मुझे कृषि योजना चाहिए"),
                       ("mr", "मला कृषी योजना हवी आहे")):
        res = door_a.match(text, lang=lang)
        assert res.action == "downgrade_to_b", (lang, res)
        assert res.scheme_ids == ()


def test_door_a_bare_constructor_raises():
    """AUDIT #5: Engine reads no disk — DoorA() without entries or corpus refuses."""
    with pytest.raises(ValueError, match="scheme_entries or corpus"):
        DoorA()


def test_unmatched_content_clean_vs_mixed():
    """Clean namings carry no extra content; mixed utterances keep their box facts."""
    assert unmatched_content("PM Kisan", "pm kisan") is False
    assert unmatched_content("PM Kisan yojana", "pm kisan") is False
    assert unmatched_content("I am a farmer from Bihar, tell me about PM Kisan", "pm kisan") is True
    assert unmatched_content("mujhe PM Kisan chahiye", "pm kisan") is False
    assert unmatched_content("kcc", None) is True
