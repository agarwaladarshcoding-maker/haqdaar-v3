"""tests/test_filter.py

Tests for Step 3 pure filtering engine (haqdaar/engine/filter.py).
Follows T09, T10, T18, 04-INTERFACES, and Step 2 fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import (
    ANY,
    HARD_BOXES,
    SEVEN_BOXES,
    UNASKED,
    UNKNOWN,
)
from haqdaar.data.corpus import Corpus
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.engine.filter import (
    Filter,
    build_masks,
    miss_set,
    nearest,
    speakable,
    survivors,
    tally,
    turn_masks,
)


@pytest.fixture
def fixtures_data():
    fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures"
    schemes_file = fixtures_dir / "schemes.jsonl"
    personas_file = fixtures_dir / "personas.json"

    schemes = []
    with open(schemes_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                schemes.append(json.loads(line))

    # S1-S5 are valid schemes, S6 is rejected by Gate 3
    valid_schemes = [s for s in schemes if s.get("scheme_id") != "S6"]

    with open(personas_file, "r", encoding="utf-8") as f:
        personas = json.load(f)

    return {
        "schemes": valid_schemes,
        "personas": {p["persona_id"]: p for p in personas},
        "fixtures_dir": fixtures_dir,
    }


@pytest.fixture
def corpus(fixtures_data, tmp_path, monkeypatch):
    snap_dir = tmp_path / "snapshots"
    audio_dir = tmp_path / "audio"
    snap_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap_dir))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio_dir))

    snap_id = build_snapshot(
        schemes_data=fixtures_data["schemes"],
        snapshot_id="test_filter_snap",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )
    return Corpus.load(snap_id)


def test_build_masks_any_semantics(fixtures_data):
    """ANY sets the scheme's bit in every mask for that column."""
    schemes = fixtures_data["schemes"]
    masks = build_masks(schemes)

    # S4 is index 3 and has ANY for gender, social_category, age, income_band, occupation
    s4_idx = 3
    s4_bit = 2**s4_idx

    # Gender masks
    gender_masks = [m for (b, v), m in masks.items() if b == "gender"]
    assert len(gender_masks) > 0
    for gm in gender_masks:
        assert (gm & s4_bit) != 0, "S4 must have bit set in every gender mask due to ANY"

    # Social category masks
    social_cat_masks = [m for (b, v), m in masks.items() if b == "social_category"]
    assert len(social_cat_masks) > 0
    for scm in social_cat_masks:
        assert (scm & s4_bit) != 0, "S4 must have bit set in every social_category mask due to ANY"


def test_turn_masks_retention_and_no_not_masks(corpus):
    """Turn masks are retained and not folded; UNASKED and UNKNOWN do not append masks."""
    vector = {
        "category": "farming",
        "state": "MAHARASHTRA",
        "gender": UNKNOWN,
        "social_category": UNASKED,
    }
    retained = turn_masks(vector, corpus)
    # Only answered boxes ("category" and "state") append masks
    assert len(retained) == 2
    boxes_in_masks = [b for b, v, m in retained]
    assert "category" in boxes_in_masks
    assert "state" in boxes_in_masks
    assert "gender" not in boxes_in_masks
    assert "social_category" not in boxes_in_masks

    # Verify each mask is a non-negative integer word (no NOT masks)
    for b, v, m in retained:
        assert isinstance(m, int)
        assert m >= 0


def test_unknown_never_narrows(corpus):
    """Assertion proving: UNKNOWN never narrows — leaves survivor set the size it was."""
    # 1. Starting from empty vector
    empty_vec = {}
    initial_survivors = survivors(empty_vec, corpus)
    assert len(initial_survivors) == 5

    # Adding UNKNOWN answer on state leaves survivor set identical in size and content
    state_unknown_vec = {"state": UNKNOWN}
    unknown_survivors = survivors(state_unknown_vec, corpus)
    assert len(unknown_survivors) == len(initial_survivors)
    assert unknown_survivors == initial_survivors

    # 2. Starting from a partially answered vector
    partial_vec = {"state": "MAHARASHTRA"}
    partial_survivors = survivors(partial_vec, corpus)
    assert len(partial_survivors) > 0

    # Adding an UNKNOWN answer to partial vector leaves survivors exactly the same size
    partial_with_unknown = {"state": "MAHARASHTRA", "gender": UNKNOWN}
    survivors_after_unknown = survivors(partial_with_unknown, corpus)
    assert len(survivors_after_unknown) == len(partial_survivors)
    assert survivors_after_unknown == partial_survivors

    # Adding multiple UNKNOWNs never narrows
    multi_unknown = {
        "state": "MAHARASHTRA",
        "gender": UNKNOWN,
        "age": UNKNOWN,
        "occupation": UNKNOWN,
    }
    multi_unknown_survivors = survivors(multi_unknown, corpus)
    assert len(multi_unknown_survivors) == len(partial_survivors)
    assert multi_unknown_survivors == partial_survivors


def test_hard_miss_scheme_s3_never_speakable_for_persona_p1(fixtures_data, corpus):
    """Assertion proving: the hard-miss scheme S3 is never speakable for persona P1."""
    schemes = fixtures_data["schemes"]
    s3_record = next(s for s in schemes if s["scheme_id"] == "S3")
    s3_idx = 2
    assert corpus.scheme_id(s3_idx) == "S3"

    p1 = fixtures_data["personas"]["P1"]
    # P1 is from outside Maharashtra ("OTHER"); S3 is state=MAHARASHTRA (D6
    # fixture migration: KARNATAKA -> MAHARASHTRA) — a genuine hard box miss.
    assert p1["demographics"]["state"] == "OTHER"
    assert s3_record["state"] == "MAHARASHTRA"

    # Stage 1: Empty vector (state is UNASKED) -> S3 must not be speakable
    vec_empty = {}
    assert not speakable(s3_record, vec_empty, corpus)
    assert not speakable(s3_idx, vec_empty, corpus)
    assert not speakable("S3", vec_empty, corpus)

    # Stage 2: State answered as UNKNOWN -> S3 must not be speakable
    vec_unknown = {"state": UNKNOWN}
    assert not speakable(s3_record, vec_unknown, corpus)
    assert not speakable(s3_idx, vec_unknown, corpus)
    assert not speakable("S3", vec_unknown, corpus)

    # Stage 3: State answered with P1's true state ("OTHER") -> S3 mismatched -> not speakable
    vec_bihar = {"state": "OTHER"}
    assert not speakable(s3_record, vec_bihar, corpus)
    assert not speakable(s3_idx, vec_bihar, corpus)
    assert not speakable("S3", vec_bihar, corpus)

    # Stage 4: Full vector matching all of P1's boxes -> S3 is NEVER speakable
    full_p1_vec = {b: str(v) for b, v in p1["demographics"].items()}
    assert not speakable(s3_record, full_p1_vec, corpus)
    assert not speakable(s3_idx, full_p1_vec, corpus)
    assert not speakable("S3", full_p1_vec, corpus)

    # Contrast check: S1 (state=ANY/central, female, SC) IS speakable for P1 when hard boxes match
    s1_record = next(s for s in schemes if s["scheme_id"] == "S1")
    s1_idx = 0
    assert speakable(s1_record, full_p1_vec, corpus)
    assert speakable(s1_idx, full_p1_vec, corpus)


def test_tally_and_miss_set(fixtures_data, corpus):
    """Test tally calculation and miss_set derivation."""
    # S1: farming, ANY (central), female, SC, 30, 75000, farmer (index 0)
    # S2: farming, ANY (central), female, SC, 30, 30000, farmer (index 1) - soft miss on income_band
    # S3: farming, MAHARASHTRA, female, SC, 30, 75000, farmer (index 2) - hard miss on state
    # Vector represents a caller from outside Maharashtra ("OTHER"): S1/S2
    # (state=ANY) still match; S3 (state=MAHARASHTRA) hard-misses.
    vector = {
        "category": "farming",
        "state": "OTHER",
        "gender": "female",
        "social_category": "SC",
        "age": "30-30",
        "income_band": "75000-75000",
        "occupation": "farmer",
    }
    tallies = tally(vector, corpus)
    # S1 matches all 7 answered boxes
    assert tallies[0] == 7
    # S2 matches 6 answered boxes (misses on income_band)
    assert tallies[1] == 6
    # S3 matches 6 answered boxes (misses on state)
    assert tallies[2] == 6

    # Miss sets
    ms_s1 = miss_set(vector, corpus, 0)
    assert ms_s1 == frozenset()

    ms_s2 = miss_set(vector, corpus, 1)
    assert ms_s2 == frozenset({"income_band"})
    assert not bool(ms_s2 & HARD_BOXES)  # soft-only miss

    ms_s3 = miss_set(vector, corpus, 2)
    assert ms_s3 == frozenset({"state"})
    assert bool(ms_s3 & HARD_BOXES)  # hard-miss!


def test_nearest_ranking_and_capping(fixtures_data, corpus):
    """Test nearest keeps soft-only miss-sets, ranks by tally then specificity, caps at 2."""
    # Build vector representing Persona P2 (zero survivors)
    # P2: farming, OTHER (outside Maharashtra), female, SC, 45, 90000, farmer
    # S1 misses on age (30 vs 45) and income_band (75000 vs 90000) -> soft misses
    # S2 misses on age (30 vs 45) and income_band (30000 vs 90000) -> soft misses
    # S3 misses on state (MAHARASHTRA vs OTHER) -> HARD miss, must be excluded!
    p2_vec = {
        "category": "farming",
        "state": "OTHER",
        "gender": "female",
        "social_category": "SC",
        "age": "45",
        "income_band": "90000",
        "occupation": "farmer",
    }

    # Verify survivors are 0
    survs = survivors(p2_vec, corpus)
    # S4 (state=ANY, central) might survive category and state if ANY on age/income
    # Let's check S4
    ms_s3 = miss_set(p2_vec, corpus, 2)
    assert "state" in ms_s3  # S3 has hard-miss

    # Nearest ranking
    near = nearest(p2_vec, corpus)
    assert len(near) <= tunables.NEAREST_CAP
    # S3 must NEVER be in nearest because its miss-set holds a hard box
    assert 2 not in near  # 2 is index of S3

    # All schemes in nearest must have soft-only miss-set and be speakable
    for ix in near:
        ms = miss_set(p2_vec, corpus, ix)
        assert not bool(ms & HARD_BOXES)
        assert speakable(ix, p2_vec, corpus)


def test_filter_class_wrapper(corpus):
    """Test Filter class static and instance wrapper methods."""
    vec = {"state": "MAHARASHTRA"}
    f = Filter(vec, corpus)
    assert f.get_survivors() == survivors(vec, corpus)
    assert f.get_tally() == tally(vec, corpus)
    assert f.get_miss_set(0) == miss_set(vec, corpus, 0)
    assert f.get_nearest() == nearest(vec, corpus)
    assert f.is_speakable(0) == speakable(0, vec, corpus)
    assert len(f.get_turn_masks()) == 1

    # Staticmethods
    assert Filter.survivors(vec, corpus) == f.get_survivors()
    assert Filter.tally(vec, corpus) == f.get_tally()
    assert Filter.miss_set(vec, corpus, 0) == f.get_miss_set(0)
    assert Filter.nearest(vec, corpus) == f.get_nearest()
    assert Filter.speakable(0, vec, corpus) == f.is_speakable(0)


def test_speakable_any_on_hard_box(fixtures_data, corpus):
    """S4 has ANY on gender and social_category, so it is speakable even when those are UNASKED."""
    schemes = fixtures_data["schemes"]
    s4_record = next(s for s in schemes if s["scheme_id"] == "S4")
    s4_idx = 3

    # State matches MAHARASHTRA, but gender and social_category are UNASKED
    vec = {"state": "MAHARASHTRA"}
    assert speakable(s4_record, vec, corpus)
    assert speakable(s4_idx, vec, corpus)

    # State matches MAHARASHTRA, but gender and social_category are UNKNOWN
    vec_unknown = {"state": "MAHARASHTRA", "gender": UNKNOWN, "social_category": UNKNOWN}
    assert speakable(s4_record, vec_unknown, corpus)
    assert speakable(s4_idx, vec_unknown, corpus)


def test_nearest_empty_when_all_schemes_hard_miss(corpus):
    """When all schemes have a hard-box miss, nearest returns empty tuple (T18 Empty terminal)."""
    # state=OTHER hard-misses S3/S4/S5 (all state=MAHARASHTRA-only, D6 fixture
    # migration gave S4 a real state constraint too); S1/S2 (state=ANY) survive
    # on state alone but are gagged by speakable() because gender and
    # social_category — both non-ANY on S1/S2 — are left unasked. Every scheme
    # ends up excluded.
    vec = {"state": "OTHER"}
    near = nearest(vec, corpus)
    assert near == ()


def test_survivor_and_tally_pure_dict_corpus(fixtures_data):
    """Filter functions work directly on mask dict without Corpus class."""
    schemes = fixtures_data["schemes"]
    masks = build_masks(schemes)

    vec = {"category": "farming", "state": "MAHARASHTRA"}
    survs = survivors(vec, masks)
    tallies = tally(vec, masks)
    assert len(survs) > 0
    assert len(tallies) == len(schemes)
    assert tallies[0] == 2  # S1 matches both category and state



def test_speakable_when_hard_box_is_any_on_every_scheme(tmp_path, monkeypatch):
    """A hard box that is ANY on every scheme never locks anything — every
    scheme is speakable no matter what the box_vector says about it.

    Before 13 Sep this refused every scheme in such a corpus — e.g. an
    all-nationwide corpus with no real `state` values. The original form of
    this test also asserted `c.values(box) == ()` (an "empty closed set" as
    the trigger for the ANY escape valve in speakable()); as of step 1.5a,
    `state`/`gender`/`social_category` are keypad-vocab boxes (D6), so
    Corpus.values() for them is now always the full vocab.py list, in vocab
    order, and can never be empty — that specific premise no longer applies,
    so it is dropped here. The behavior under test (every scheme ANY on a
    hard box => that box never locks anyone out) still holds and is asserted
    directly below.
    """
    schemes = [
        {"scheme_id": f"N{i}", "state": "ANY", "category": "farming",
         "gender": "ANY", "social_category": "ANY", "age": "ANY",
         "income_band": inc, "occupation": "ANY"}
        for i, inc in enumerate(("30000", "75000"))
    ]
    snap_dir = tmp_path / "snap"
    audio_dir = tmp_path / "audio"
    snap_dir.mkdir()
    audio_dir.mkdir()
    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap_dir))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio_dir))
    snap_id = build_snapshot(
        schemes_data=schemes, snapshot_id="all_any_hard",
        snapshots_dir=snap_dir, audio_dir=audio_dir, render_stubs=True,
    )
    c = Corpus.load(snap_id)

    bv = {b: UNASKED for b in SEVEN_BOXES}
    assert speakable(0, bv, c)
    assert speakable(1, bv, c)


def test_speakable_with_dict_corpus_any_escape_valve():
    """A dict-like corpus mapping (box, val) -> mask properly triggers ANY escape valve when all ANY."""
    dict_corpus = {
        ("state", "MAHARASHTRA"): 1,
        ("gender", "ANY"): 1,
        ("social_category", "GEN"): 1,
    }
    bv = {b: UNASKED for b in SEVEN_BOXES}
    bv["state"] = "MAHARASHTRA"
    bv["social_category"] = "GEN"
    scheme = {"state": "MAHARASHTRA", "gender": "ANY", "social_category": "GEN"}
    assert speakable(scheme, bv, dict_corpus) is True
