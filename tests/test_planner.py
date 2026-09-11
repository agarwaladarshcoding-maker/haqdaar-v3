"""tests/test_planner.py

Unit tests for Step 4 pure questioning and widening planner (haqdaar/engine/planner.py).
Tests all four stops, the full widen ladder (including skipped rungs),
the speaking-rule exception, minimax scoring, tie-breaking, and out-of-set re-asking.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.log_schema import (
    STOP_LE_4_SURVIVORS,
    STOP_MAX_QUESTIONS,
    STOP_MAX_TURNS,
    STOP_NO_SPLIT,
    STOP_ZERO_SURVIVORS,
)
from haqdaar.contracts.types import (
    Ask,
    HARD_BOXES,
    SEVEN_BOXES,
    Stop,
    UNASKED,
    UNKNOWN,
    Widen,
    WIDENING_ORDER,
)
from haqdaar.data.corpus import Corpus
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.engine.filter import Filter
from haqdaar.engine.planner import Planner, next_action


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
        snapshot_id="test_planner_snap",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )
    return Corpus.load(snap_id)


def test_stop_survivors_le_4(corpus):
    """Stop 1: <= 4 survivors when speaking-rule exception is satisfied."""
    # When category, state, gender, social_category are answered, survivors are (0, 1, 3) -> 3 <= 4
    # All hard boxes are answered, so no unasked hard boxes are non-ANY.
    bv = {
        "category": "agriculture",
        "state": "BIHAR",
        "gender": "female",
        "social_category": "SC",
    }
    survs = Filter.survivors(bv, corpus)
    assert len(survs) <= tunables.STOP_SURVIVORS
    act = next_action(bv, corpus)
    assert isinstance(act, Stop)
    assert act.reason == STOP_LE_4_SURVIVORS


def test_speaking_rule_exception_prevents_le_4_stop(corpus):
    """Speaking-rule exception: do not stop on <= 4 while an unasked hard box is non-ANY.

    With category=agriculture, survivors are (0, 1, 2, 3) (4 survivors <= 4).
    However, state, gender, social_category are unasked, and schemes 0, 1, 2, 3
    require specific values (non-ANY) on them.
    Planner MUST ask the qualifying hard box first rather than stopping.
    """
    bv = {"category": "agriculture"}
    survs = Filter.survivors(bv, corpus)
    assert len(survs) == 4
    assert len(survs) <= tunables.STOP_SURVIVORS

    act = next_action(bv, corpus)
    assert isinstance(act, Ask)
    assert act.box in HARD_BOXES
    # In minimax score + snapshot order, state wins
    assert act.box == "state"


def test_stop_max_turns(corpus):
    """Stop 2a: 8 turns spent triggers STOP_MAX_TURNS."""
    bv = {"category": "agriculture"}
    act = next_action(bv, corpus, turn_count=tunables.MAX_TURNS)
    assert isinstance(act, Stop)
    assert act.reason == STOP_MAX_TURNS

    # Also over cap
    act_over = next_action(bv, corpus, turn_count=tunables.MAX_TURNS + 1)
    assert isinstance(act_over, Stop)
    assert act_over.reason == STOP_MAX_TURNS


def test_stop_max_questions(corpus):
    """Stop 2b: 6 questions spent triggers STOP_MAX_QUESTIONS."""
    bv = {"category": "agriculture"}
    act = next_action(bv, corpus, question_count=tunables.MAX_QUESTIONS)
    assert isinstance(act, Stop)
    assert act.reason == STOP_MAX_QUESTIONS

    # Also over cap
    act_over = next_action(bv, corpus, question_count=tunables.MAX_QUESTIONS + 1)
    assert isinstance(act_over, Stop)
    assert act_over.reason == STOP_MAX_QUESTIONS


def test_stop_no_split(tmp_path, monkeypatch):
    """Stop 3: No remaining box splits survivors."""
    # Build a corpus with 5 schemes where all remaining boxes are ANY
    snap_dir = tmp_path / "snapshots_nosplit"
    audio_dir = tmp_path / "audio_nosplit"
    snap_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap_dir))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio_dir))

    schemes = [
        {
            "scheme_id": f"NS{i}",
            "title": {"en": f"NS{i}", "hi": f"NS{i}", "mr": f"NS{i}"},
            "summary": {"en": f"NS{i}", "hi": f"NS{i}", "mr": f"NS{i}"},
            "details": {"en": f"NS{i}", "hi": f"NS{i}", "mr": f"NS{i}"},
            "documents": {"en": f"NS{i}", "hi": f"NS{i}", "mr": f"NS{i}"},
            "how_to_apply": {"en": f"NS{i}", "hi": f"NS{i}", "mr": f"NS{i}"},
            "category": "cat_common",
            "state": "BIHAR",
            "gender": "ALL",
            "social_category": "ALL",
            "age": "ANY",
            "income_band": "ANY",
            "occupation": "ANY",
            "aliases": [f"ns{i}"],
        }
        for i in range(5)
    ]
    snap_id = build_snapshot(
        schemes_data=schemes,
        snapshot_id="test_nosplit_snap",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )
    test_corpus = Corpus.load(snap_id)

    # 5 survivors > 4, but every remaining box is ANY across all survivors
    bv = {"category": "cat_common", "state": "BIHAR"}
    assert len(Filter.survivors(bv, test_corpus)) == 5
    act = next_action(bv, test_corpus)
    assert isinstance(act, Stop)
    assert act.reason == STOP_NO_SPLIT


def test_stop_zero_survivors_exhausted_ladder(tmp_path, monkeypatch):
    """Stop 4: Zero survivors and widening ladder exhausts."""
    # Build a corpus with hard-box conflict between two states
    snap_dir = tmp_path / "snapshots_zero"
    audio_dir = tmp_path / "audio_zero"
    snap_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap_dir))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio_dir))

    schemes = [
        {
            "scheme_id": "Z1",
            "title": {"en": "Z1", "hi": "Z1", "mr": "Z1"},
            "summary": {"en": "Z1", "hi": "Z1", "mr": "Z1"},
            "details": {"en": "Z1", "hi": "Z1", "mr": "Z1"},
            "documents": {"en": "Z1", "hi": "Z1", "mr": "Z1"},
            "how_to_apply": {"en": "Z1", "hi": "Z1", "mr": "Z1"},
            "category": "agriculture",
            "state": "BIHAR",
            "gender": "female",
            "social_category": "ALL",
            "age": "30",
            "income_band": "30000",
            "occupation": "farmer",
            "aliases": ["z1"],
        },
        {
            "scheme_id": "Z2",
            "title": {"en": "Z2", "hi": "Z2", "mr": "Z2"},
            "summary": {"en": "Z2", "hi": "Z2", "mr": "Z2"},
            "details": {"en": "Z2", "hi": "Z2", "mr": "Z2"},
            "documents": {"en": "Z2", "hi": "Z2", "mr": "Z2"},
            "how_to_apply": {"en": "Z2", "hi": "Z2", "mr": "Z2"},
            "category": "agriculture",
            "state": "KARNATAKA",
            "gender": "male",
            "social_category": "ALL",
            "age": "30",
            "income_band": "30000",
            "occupation": "farmer",
            "aliases": ["z2"],
        },
    ]
    snap_id = build_snapshot(
        schemes_data=schemes,
        snapshot_id="test_zero_snap",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )
    test_corpus = Corpus.load(snap_id)

    # State BIHAR + gender male conflicts on hard boxes with both schemes: 0 survivors
    # Widening drops all soft boxes (income_band, age, occupation, category), but survivors remain 0
    bv = {
        "state": "BIHAR",
        "gender": "male",
        "income_band": "30000",
        "age": "30",
        "occupation": "farmer",
        "category": "agriculture",
    }
    assert len(Filter.survivors(bv, test_corpus)) == 0
    act = next_action(bv, test_corpus)
    assert isinstance(act, Stop)
    assert act.reason == STOP_ZERO_SURVIVORS


def test_widen_ladder_rung_1_income_band(corpus):
    """Widening ladder: stops at first rung (income_band) producing >= 1 survivor."""
    # In fixture, S3 requires category=handloom, state=KARNATAKA, age=35, income_band=75000.
    # If caller answered income_band=30000 (mismatch), age=35 (match):
    # Dropping income_band at rung 1 immediately recovers S3!
    bv = {
        "category": "handloom",
        "state": "KARNATAKA",
        "age": "35",
        "income_band": "30000",
    }
    assert len(Filter.survivors(bv, corpus)) == 0
    act = next_action(bv, corpus)
    assert isinstance(act, Widen)
    assert act.box == "income_band"


def test_widen_ladder_rung_2_age(corpus):
    """Widening ladder: drops income_band then age cumulatively."""
    # S3 requires category=handloom, state=KARNATAKA, age=35, income_band=75000.
    # Caller answered income_band=30000 and age=30:
    # Rung 1: drop income_band -> vector still has age=30 -> 0 survivors.
    # Rung 2: drop age -> vector has both income_band and age dropped -> S3 survives!
    bv = {
        "category": "handloom",
        "state": "KARNATAKA",
        "age": "30",
        "income_band": "30000",
    }
    assert len(Filter.survivors(bv, corpus)) == 0
    act = next_action(bv, corpus)
    assert isinstance(act, Widen)
    assert act.box == "age"


def test_widen_ladder_skips_unasked_or_unknown_rungs(corpus):
    """Widening ladder skips rungs over UNASKED or UNKNOWN boxes rather than counting them.

    Order: income_band -> age -> occupation -> category.
    If income_band is answered (mismatched), age is UNASKED, occupation is UNKNOWN, and category is answered:
    Rung 1: drop income_band -> still 0 survivors.
    age is UNASKED -> skipped (not counted, no mask to drop).
    occupation is UNKNOWN -> skipped (not counted, no mask to drop).
    Next rung: category -> dropping category recovers survivors!
    Returns Widen("category").
    """
    # S1, S2, S4, S5 are state=BIHAR, category=agriculture.
    # S3 is state=KARNATAKA, category=handloom.
    # If state=BIHAR and category=handloom: 0 survivors.
    # Also answer income_band=75000 (which misses S1/S2 in BIHAR).
    # age is UNASKED, occupation is UNKNOWN.
    bv = {
        "state": "BIHAR",
        "category": "handloom",
        "income_band": "75000",
        "age": UNASKED,
        "occupation": UNKNOWN,
    }
    assert len(Filter.survivors(bv, corpus)) == 0

    act = next_action(bv, corpus)
    assert isinstance(act, Widen)
    # Rungs for age and occupation were skipped; category produced >= 1 survivor
    assert act.box == "category"


def test_widen_never_drops_hard_boxes(corpus):
    """Hard boxes (state, gender, social_category) are walls and never widened."""
    # When category is handloom and state is BIHAR: 0 survivors.
    # Widening drops category (soft box) and recovers BIHAR schemes.
    # State is never dropped to recover S3.
    bv = {"category": "handloom", "state": "BIHAR"}
    act = next_action(bv, corpus)
    assert isinstance(act, Widen)
    assert act.box == "category"
    assert act.box not in HARD_BOXES


def test_minimax_scoring_and_tie_breaking(corpus):
    """Minimax elimination divided by expected turns, ties broken on snapshot order."""
    # On empty vector:
    # category: elim=1, turns=1 -> 1.0
    # state: elim=2, turns=2 (spoken) -> 1.0
    # gender: elim=1, turns=1 -> 1.0
    # social_category: elim=1, turns=1 -> 1.0
    # age: elim=1, turns=1 -> 1.0
    # income_band: elim=2, turns=1 -> 2.0 (highest score!)
    # occupation: elim=1, turns=1 -> 1.0
    act = next_action({}, corpus)
    assert isinstance(act, Ask)
    assert act.box == "income_band"

    # When income_band is UNKNOWN, it appends no mask (5 survivors > 4 remain)
    # and income_band is permanently skipped.
    # The remaining boxes all have tie scores of 1.0 (category: 1/1, state: 2/2, gender: 1/1, etc.)
    # Ties must break on snapshot order: category (index 0) beats state (index 1) etc.
    act_tie = next_action({"income_band": UNKNOWN}, corpus)
    assert isinstance(act_tie, Ask)
    assert act_tie.box == "category"


def test_unknown_box_is_permanently_skipped(corpus):
    """Skip UNKNOWN boxes permanently — UNASKED stays askable, UNKNOWN does not."""
    # When income_band is UNKNOWN, it cannot be asked again
    bv = {"income_band": UNKNOWN}
    act = next_action(bv, corpus)
    assert isinstance(act, Ask)
    assert act.box != "income_band"
    assert act.box == "category"  # Ties break on snapshot order


def test_out_of_set_answer_reask(corpus):
    """Out-of-set answers must come back as a re-ask (from the Step 3 review / T09 §6).

    Coercion decision (as required by prompt):
    - The Caller / Turn Runner retains the raw user string in box_vector (e.g. state="MAHARASHTRA")
      without coercing it to UNKNOWN. If the caller side coerced out-of-set directly to UNKNOWN in the
      box_vector, T11 mandates that UNKNOWN is permanently skipped ("never re-asked, never pushed to keypad").
    - The Filter treats an out-of-set value as UNKNOWN (appends no mask, so survivors are not narrowed).
    - The Planner treats an out-of-set value as unasked / re-askable for question selection, so that
      it is asked again as required by T09 §6 ("handed to the ladder as a re-ask"). For widening,
      the Planner treats out-of-set values as UNKNOWN (skips the rung because no mask was appended).
    """
    # "MAHARASHTRA" is not in corpus.values("state") for the fixture (BIHAR, KARNATAKA)
    bv = {"category": "agriculture", "state": "MAHARASHTRA"}
    # Survivors are not narrowed by state=MAHARASHTRA (filter appends no mask -> 4 survivors)
    survs = Filter.survivors(bv, corpus)
    assert len(survs) == 4

    # A naive planner would see state in box_vector and skip it as answered.
    # Our planner detects that MAHARASHTRA is out-of-set, treats it as unasked, and
    # under the speaking-rule exception, re-asks state!
    act = next_action(bv, corpus)
    assert isinstance(act, Ask)
    assert act.box == "state"

    # Conversely, if state was answered with a valid in-set value "BIHAR", it is NOT re-asked:
    bv_valid = {"category": "agriculture", "state": "BIHAR"}
    act_valid = next_action(bv_valid, corpus)
    assert isinstance(act_valid, Ask)
    assert act_valid.box != "state"
    assert act_valid.box == "gender"


def test_planner_class_interface(corpus):
    """Planner namespace exposes next_action static method conforming to 04-INTERFACES."""
    res = Planner.next_action({}, corpus)
    assert isinstance(res, Ask)
    assert res.box == "income_band"
