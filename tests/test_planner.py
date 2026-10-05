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
    # When category, state, gender, social_category are answered, survivors are
    # (0, 1, 2, 3) -> 4 <= 4 (S3's state is now ANY/central, so it also survives).
    # All hard boxes are answered, so no unasked hard boxes are non-ANY.
    bv = {
        "category": "farming",
        "state": "MAHARASHTRA",
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

    With category=farming, survivors are (0, 1, 2, 3) (4 survivors <= 4).
    However, state, gender, social_category are unasked, and S1, S2, S4
    require specific values (non-ANY) on them (S3 is state=ANY/central).
    Planner MUST ask the qualifying hard box first rather than stopping.
    """
    bv = {"category": "farming"}
    survs = Filter.survivors(bv, corpus)
    assert len(survs) == 4
    assert len(survs) <= tunables.STOP_SURVIVORS

    act = next_action(bv, corpus)
    assert isinstance(act, Ask)
    assert act.box in HARD_BOXES
    # 1.3a tie rule: worst scores tie at 0, averages are state 3.0, gender 2.0,
    # social_category 1.75, so social_category asks first (was "state" on snapshot order).
    assert act.box == "social_category"


def test_stop_max_turns(corpus):
    """Stop 2a: 8 turns spent triggers STOP_MAX_TURNS."""
    bv = {"category": "farming"}
    act = next_action(bv, corpus, turn_count=tunables.MAX_TURNS)
    assert isinstance(act, Stop)
    assert act.reason == STOP_MAX_TURNS

    # Also over cap
    act_over = next_action(bv, corpus, turn_count=tunables.MAX_TURNS + 1)
    assert isinstance(act_over, Stop)
    assert act_over.reason == STOP_MAX_TURNS


def test_stop_max_questions(corpus):
    """Stop 2b: 6 questions spent triggers STOP_MAX_QUESTIONS."""
    bv = {"category": "farming"}
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
            "category": "farming",
            "state": "MAHARASHTRA",
            "gender": "ANY",
            "social_category": "ANY",
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
    bv = {"category": "farming", "state": "MAHARASHTRA"}
    assert len(Filter.survivors(bv, test_corpus)) == 5
    act = next_action(bv, test_corpus)
    assert isinstance(act, Stop)
    assert act.reason == STOP_NO_SPLIT


def test_stop_zero_survivors_exhausted_ladder(tmp_path, monkeypatch):
    """Stop 4: Zero survivors and widening ladder exhausts."""
    # Build a corpus with a hard-box conflict. The closed `state` set is now
    # binary (MAHARASHTRA or ANY/central, D6), so there is no second real state
    # left to build a two-state conflict from; social_category still has 4 real
    # codes, so the conflict is built there instead. The point under test is
    # unchanged: a hard-box mismatch is permanent and the widening ladder
    # (income_band -> age -> occupation) can never rescue it.
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
            "category": "farming",
            "state": "ANY",
            "gender": "female",
            "social_category": "GEN",
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
            "category": "farming",
            "state": "ANY",
            "gender": "male",
            "social_category": "OBC",
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

    # social_category ST matches neither Z1 (GEN) nor Z2 (OBC), and gender male
    # also conflicts with Z1 (female): both hard-miss. 0 survivors.
    # Widening drops all soft boxes (income_band, age, occupation, category), but survivors remain 0
    bv = {
        "gender": "male",
        "social_category": "ST",
        "income_band": "30000",
        "age": "30",
        "occupation": "farmer",
        "category": "farming",
    }
    assert len(Filter.survivors(bv, test_corpus)) == 0
    act = next_action(bv, test_corpus)
    assert isinstance(act, Stop)
    assert act.reason == STOP_ZERO_SURVIVORS


def test_widen_ladder_rung_1_income_band(corpus):
    """Widening ladder: stops at first rung (income_band) producing >= 1 survivor."""
    # S5 (the sole business_loans scheme) is state=MAHARASHTRA, age=35, income_band=50000.
    # If caller answered income_band=30000 (mismatch), age=35 (match):
    # Dropping income_band at rung 1 immediately recovers S5!
    # gender and social_category are answered ANY (a no-op mask, same role the
    # old broken "ALL" placeholder played), so the widened candidate is already
    # speakable without an extra hard-box ask.
    bv = {
        "category": "business_loans",
        "state": "MAHARASHTRA",
        "gender": "ANY",
        "social_category": "ANY",
        "age": "35-35",
        "income_band": "30000-30000",
    }
    assert len(Filter.survivors(bv, corpus)) == 0
    act = next_action(bv, corpus)
    assert isinstance(act, Widen)
    assert act.box == "income_band"


def test_widen_ladder_rung_2_age(corpus):
    """Widening ladder: drops income_band then age cumulatively."""
    # S5 (the sole business_loans scheme) is age=35, income_band=50000.
    # Caller answered income_band=30000 and age=30:
    # Rung 1: drop income_band -> vector still has age=30 -> 0 survivors.
    # Rung 2: drop age -> vector has both income_band and age dropped -> S5 survives!
    bv = {
        "category": "business_loans",
        "state": "MAHARASHTRA",
        "gender": "ANY",
        "social_category": "ANY",
        "age": "30-30",
        "income_band": "30000-30000",
    }
    assert len(Filter.survivors(bv, corpus)) == 0
    act = next_action(bv, corpus)
    assert isinstance(act, Widen)
    assert act.box == "age"


def test_widen_ladder_skips_unasked_or_unknown_rungs(corpus):
    """Widening ladder skips rungs over UNASKED or UNKNOWN boxes rather than counting them.

    Order: income_band -> age -> occupation.
    income_band is answered and mismatched, age is UNASKED, occupation is
    answered and mismatched:
    Rung 1: drop income_band -> still 0 survivors.
    age is UNASKED -> skipped (not counted, no mask to drop).
    Next rung: occupation -> dropping it recovers survivors.
    """
    # S1 and S2 are the two state=ANY (central) farming schemes (income_band
    # 75000/30000, occupation farmer). state=OTHER excludes S3, S4, S5 (all
    # state=MAHARASHTRA-only, D6 fixture migration: S4's only real constraint
    # is its state, KARNATAKA -> MAHARASHTRA), leaving only S1/S2 in play;
    # income_band=50000 and occupation=weaver miss both of them.
    bv = {
        "category": "farming",
        "state": "OTHER",
        "gender": "female",
        "social_category": "SC",
        "income_band": "50000",
        "age": UNASKED,
        "occupation": "weaver",
    }
    assert len(Filter.survivors(bv, corpus)) == 0

    act = next_action(bv, corpus)
    assert isinstance(act, Widen)
    # Rung 1 (income_band) did not recover anything on its own, age was skipped
    assert act.box == "occupation"


def test_widen_never_drops_hard_boxes_or_category(corpus):
    """Hard boxes are walls. `category` is soft but is never widened either.

    T10 D6 as amended 13 Sep: the ladder is income_band -> age -> occupation.
    `category` is the subject the caller phoned about (Door A), so relaxing it
    would answer a question they did not ask — and with it in the ladder,
    "ladder exhausted" and "no scheme with a soft-only miss-set" collapse into
    the same condition, which made delivery shape 4 (Nearest) unreachable.
    """
    assert "category" not in WIDENING_ORDER
    assert not set(WIDENING_ORDER) & HARD_BOXES

    # category=business_loans (handloom) outside Maharashtra: S5 (the sole
    # business_loans scheme) is state=MAHARASHTRA-only (D6 fixture migration:
    # KARNATAKA -> MAHARASHTRA), so it hard-misses; 0 survivors, and no soft
    # box is answered, so there is no rung to walk. The call stops on zero
    # survivors and the terminal becomes Nearest or Empty — it never drops the
    # subject.
    bv = {
        "category": "business_loans",
        "state": "OTHER",
        "gender": "female",
        "social_category": "SC",
    }
    assert len(Filter.survivors(bv, corpus)) == 0
    act = next_action(bv, corpus)
    assert isinstance(act, Stop)
    assert act.reason == STOP_ZERO_SURVIVORS


def test_zero_survivors_asks_hard_box_the_nearest_would_need(corpus):
    """The speaking-rule exception also guards the Nearest terminal.

    With gender and social_category unasked, the nearest candidates are gagged
    by Filter.speakable() and the caller would hear an empty terminal over a
    corpus that held two near misses. The planner asks the hard box first.
    """
    bv = {"category": "business_loans", "state": "OTHER"}
    assert len(Filter.survivors(bv, corpus)) == 0
    act = next_action(bv, corpus)
    assert isinstance(act, Ask)
    assert act.box in HARD_BOXES


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
    # "KARNATAKA" is not in corpus.values("state") for the fixture (MAHARASHTRA, OTHER):
    # the closed state set is binary now (D6), and any other state name is out-of-set.
    # gender + social_category are answered so state is the only qualifying hard box.
    bv = {"category": "farming", "state": "KARNATAKA", "gender": "female", "social_category": "SC"}
    # Survivors are not narrowed by state=KARNATAKA (filter appends no mask -> 4 survivors)
    survs = Filter.survivors(bv, corpus)
    assert len(survs) == 4

    # A naive planner would see state in box_vector and skip it as answered.
    # Our planner detects that KARNATAKA is out-of-set, treats it as unasked, and
    # under the speaking-rule exception, re-asks state!
    act = next_action(bv, corpus)
    assert isinstance(act, Ask)
    assert act.box == "state"

    # Conversely, if state was answered with a valid in-set value "MAHARASHTRA", it is NOT re-asked:
    bv_valid = {"category": "farming", "state": "MAHARASHTRA"}
    act_valid = next_action(bv_valid, corpus)
    assert isinstance(act_valid, Ask)
    assert act_valid.box != "state"
    # 1.3a tie rule: gender and social_category tie at worst 0, social_category
    # leaves fewer on average, so it asks first (was "gender" on snapshot order).
    assert act_valid.box == "social_category"


def test_planner_class_interface(corpus):
    """Planner namespace exposes next_action static method conforming to 04-INTERFACES."""
    res = Planner.next_action({}, corpus)
    assert isinstance(res, Ask)
    assert res.box == "income_band"


def test_widen_asks_unasked_hard_box_before_widening(corpus):
    """A widened candidate is only worth buying if it can be spoken.

    S1/S2 (category=farming, state=ANY/central) are recovered by dropping
    income_band, and they are non-ANY on gender and social_category, which
    should force the planner to ask a hard box before naming either. state
    must be OTHER: S3 and S4 are both state=MAHARASHTRA-only now (D6 fixture
    migration gave S4 back a real state constraint too), so state=OTHER
    excludes them, leaving only S1/S2 to widen back in.
    """
    bv = {
        "category": "farming",
        "state": "OTHER",
        "income_band": "50000-50000",
    }
    assert len(Filter.survivors(bv, corpus)) == 0
    act = next_action(bv, corpus)
    assert isinstance(act, Ask)
    assert act.box in HARD_BOXES


def test_widen_ladder_agreement_with_terminals_on_unspeakable_raw_survivors(corpus):
    """#9: Planner and Terminals agree on widening ladder rungs.
    When a soft box drop recovers raw survivors that cannot be spoken (e.g. hard box
    is UNKNOWN and scheme is non-ANY on it), Planner skips that rung rather than
    emitting Widen, agreeing with Terminals.classify_shape.
    """
    from haqdaar.engine.terminals import Terminals, DELIVERY_EMPTY

    bv = {
        "category": "business_loans",
        "state": UNKNOWN,
        "gender": "female",
        "social_category": "SC",
        "age": "35-35",
        "income_band": "30000-30000",
    }
    # Raw survivors: 0
    assert len(Filter.survivors(bv, corpus)) == 0
    # Dropping income_band yields S5 as raw survivor:
    dropped_vec = {
        "category": "business_loans",
        "state": UNKNOWN,
        "gender": "female",
        "social_category": "SC",
        "age": "35-35",
    }
    assert len(Filter.survivors(dropped_vec, corpus)) == 1
    # But S5 is non-ANY on state (requires MAHARASHTRA), so with state=UNKNOWN it is unspeakable:
    assert Filter.speakable(4, dropped_vec, corpus) is False

    # Planner must NOT emit Widen for income_band since it cannot be spoken
    act = next_action(bv, corpus)
    assert isinstance(act, Stop)
    assert act.reason == STOP_ZERO_SURVIVORS

    from haqdaar.engine.terminals import Terminals, DELIVERY_NEAREST

    # Terminals.classify_shape agrees: ladder produced no speakable matches, goes to nearest
    shape, resolved, drops = Terminals.classify_shape(
        box_vector=bv,
        corpus=corpus,
    )
    assert shape == DELIVERY_NEAREST
    assert drops == []

