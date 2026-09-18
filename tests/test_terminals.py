"""tests/test_terminals.py

Unit tests for Step 5 pure terminals (haqdaar/engine/terminals.py).
Tests all five delivery shapes in architecture §8, the bad-news-first ordering lock,
the widened match sequence structure, nearest restraints, state_unknown_disclaimer,
marks placement, and the Filter.speakable() truth lock.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import (
    FIXED_LINE_IDS,
    HARD_BOXES,
    UNASKED,
    UNKNOWN,
    WIDENING_ORDER,
)
from haqdaar.data.corpus import Corpus
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.engine.filter import Filter
from haqdaar.engine.terminals import (
    DELIVERY_DIRECT_MATCH,
    DELIVERY_EMPTY,
    DELIVERY_NEAREST,
    DELIVERY_OVERFLOW,
    DELIVERY_WIDENED_MATCH,
    RESULTS_EXACT_PREAMBLE,
    RESULTS_OVERFLOW,
    RESULTS_WIDENED_LEAD,
    SECTION_MENU,
    SECTION_SOURCE_FRAME,
    STATE_UNKNOWN_DISCLAIMER,
    TERMINAL_EMPTY,
    TERMINAL_NEAREST_PREAMBLE,
    TERMINAL_WIDENED_PREAMBLE,
    Terminals,
    classify_shape,
    direct_match,
    empty,
    nearest,
    overflow,
    render_terminal,
    terminal_sequence,
    widened_match,
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
        snapshot_id="test_terminals_snap",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )
    return Corpus.load(snap_id)


# ---------------------------------------------------------------------------
# Ordering & Bad-News-First Tests (Prompt & Architecture §8 & Ticket T18)
# ---------------------------------------------------------------------------

def _is_scheme_name_token(token: str) -> bool:
    """Helper to detect if a token is a scheme name or scheme name mark."""
    return token.startswith("name:") or token.endswith(":name") or token.endswith("_name")


def test_ordering_bad_news_before_names_in_all_non_exact_endings(corpus):
    """In EVERY non-exact ending, no scheme name appears before the preamble.

    Asserted at build time over say() sequences:
    1. Overflow: results_overflow before names
    2. Widened match: terminal_widened_preamble before names
    3. Nearest: terminal_nearest_preamble before names
    4. Empty: terminal_empty and no names at all
    """
    # 1. Overflow
    survs_overflow = [0, 1, 2, 3, 4]
    seq_over = overflow(survs_overflow, state="BIHAR", corpus=corpus, pre_vetted=True)
    assert RESULTS_OVERFLOW in seq_over
    idx_preamble = seq_over.index(RESULTS_OVERFLOW)
    # Check every element before the preamble
    for token in seq_over[:idx_preamble]:
        assert not _is_scheme_name_token(token), (
            f"Scheme name token '{token}' appeared before preamble in overflow"
        )
    # Preamble must be followed eventually by a scheme name
    assert any(_is_scheme_name_token(t) for t in seq_over[idx_preamble:])

    # 2. Widened Match
    survs_widened = [0, 1]
    seq_widened = widened_match(
        survs_widened,
        state="BIHAR",
        dropped_boxes=["income_band", "age"],
        corpus=corpus,
        pre_vetted=True,
    )
    assert TERMINAL_WIDENED_PREAMBLE in seq_widened
    idx_preamble = seq_widened.index(TERMINAL_WIDENED_PREAMBLE)
    for token in seq_widened[:idx_preamble]:
        assert not _is_scheme_name_token(token), (
            f"Scheme name token '{token}' appeared before preamble in widened match"
        )
    assert any(_is_scheme_name_token(t) for t in seq_widened[idx_preamble:])

    # 3. Nearest
    survs_nearest = [0, 1]
    seq_near = nearest(survs_nearest, state="BIHAR", corpus=corpus, pre_vetted=True)
    assert TERMINAL_NEAREST_PREAMBLE in seq_near
    idx_preamble = seq_near.index(TERMINAL_NEAREST_PREAMBLE)
    for token in seq_near[:idx_preamble]:
        assert not _is_scheme_name_token(token), (
            f"Scheme name token '{token}' appeared before preamble in nearest"
        )
    assert any(_is_scheme_name_token(t) for t in seq_near[idx_preamble:])

    # 4. Empty
    seq_emp = empty(state="BIHAR")
    assert TERMINAL_EMPTY in seq_emp
    for token in seq_emp:
        assert not _is_scheme_name_token(token), (
            f"Scheme name token '{token}' appeared in empty terminal"
        )


def test_widened_match_strict_order_sequence(corpus):
    """In the widened ending the order is strictly:
    preamble -> drop_* -> results_widened_lead -> names.
    """
    dropped = ["income_band", "age"]
    seq = widened_match(
        [0, 1],
        state="BIHAR",
        dropped_boxes=dropped,
        corpus=corpus,
        pre_vetted=True,
    )

    idx_preamble = seq.index(TERMINAL_WIDENED_PREAMBLE)
    idx_drop1 = seq.index("drop_income_band")
    idx_drop2 = seq.index("drop_age")
    idx_lead = seq.index(RESULTS_WIDENED_LEAD)
    first_name_idx = next(i for i, t in enumerate(seq) if _is_scheme_name_token(t))

    # Strict monotonicity
    assert idx_preamble < idx_drop1 < idx_drop2 < idx_lead < first_name_idx

    # Adjacent sequence confirmation
    assert seq[idx_preamble + 1] == "drop_income_band"
    assert seq[idx_preamble + 2] == "drop_age"
    assert seq[idx_preamble + 3] == RESULTS_WIDENED_LEAD
    assert seq[idx_preamble + 4] == "name:S1"  # First name mark immediately follows lead
    assert seq[idx_preamble + 5] == "scheme:S1:name"


# ---------------------------------------------------------------------------
# Delivery Shapes Specifications (Architecture §8)
# ---------------------------------------------------------------------------

def test_direct_match_shape(corpus):
    """Shape 1: Direct match with <= 4 survivors.
    Contains results_exact_preamble, reads all survivors by specificity,
    name mark immediately before each name, end mark after summary, and section_menu.
    """
    survs = [0, 1]  # S1, S2
    seq = direct_match(survs, state="BIHAR", corpus=corpus, pre_vetted=True)

    assert seq[0] == RESULTS_EXACT_PREAMBLE
    assert seq[1] == "name:S1"
    assert seq[2] == "scheme:S1:name"
    assert seq[3] == "scheme:S1:summary"
    assert seq[4] == "end:S1"
    assert seq[5] == SECTION_MENU

    assert seq[6] == "name:S2"
    assert seq[7] == "scheme:S2:name"
    assert seq[8] == "scheme:S2:summary"
    assert seq[9] == "end:S2"
    assert seq[10] == SECTION_MENU


def test_overflow_shape(corpus):
    """Shape 2: Overflow (>4 survivors).
    Speaks top 3 by specificity, preceded by results_overflow.
    """
    survs = [0, 1, 2, 3, 4]  # 5 survivors
    seq = overflow(survs, state="BIHAR", corpus=corpus, pre_vetted=True)

    assert seq[0] == RESULTS_OVERFLOW
    # Should deliver exactly 3 schemes
    name_marks = [t for t in seq if t.startswith("name:")]
    assert len(name_marks) == 3

    # All 3 have section_menu
    section_menus = [t for t in seq if t == SECTION_MENU]
    assert len(section_menus) == 3


def test_nearest_restraints(corpus):
    """Shape 4: Nearest restraints.
    - terminal_nearest_preamble FIRST.
    - Capped at tunables.NEAREST_CAP (2).
    - Summary ONLY: NO section_menu anywhere in sequence.
    - Auto-advance.
    """
    candidates = [0, 1, 2, 3]  # 4 candidates
    seq = nearest(candidates, state="BIHAR", corpus=corpus, pre_vetted=True)

    assert seq[0] == TERMINAL_NEAREST_PREAMBLE
    name_marks = [t for t in seq if t.startswith("name:")]
    assert len(name_marks) == tunables.NEAREST_CAP  # 2

    # Restraint: NO section_menu in entire sequence!
    assert SECTION_MENU not in seq


def test_empty_shape():
    """Shape 5: Empty terminal emits terminal_empty and nothing else."""
    seq = empty(state="BIHAR")
    assert seq == (TERMINAL_EMPTY,)
    assert not any(_is_scheme_name_token(t) for t in seq)


# ---------------------------------------------------------------------------
# Disclaimer, Marks & section_source_frame Rules
# ---------------------------------------------------------------------------

def test_state_unknown_disclaimer_comes_first_across_all_shapes(corpus):
    """state_unknown_disclaimer comes first when state is UNKNOWN across all 5 shapes."""
    # 1. Direct Match
    s1 = direct_match([0], state=UNKNOWN, corpus=corpus, pre_vetted=True)
    assert s1[0] == STATE_UNKNOWN_DISCLAIMER
    assert s1[1] == RESULTS_EXACT_PREAMBLE

    # 2. Overflow
    s2 = overflow([0, 1, 2, 3, 4], state=UNKNOWN, corpus=corpus, pre_vetted=True)
    assert s2[0] == STATE_UNKNOWN_DISCLAIMER
    assert s2[1] == RESULTS_OVERFLOW

    # 3. Widened Match
    s3 = widened_match([0], state=UNKNOWN, dropped_boxes=["income_band"], corpus=corpus, pre_vetted=True)
    assert s3[0] == STATE_UNKNOWN_DISCLAIMER
    assert s3[1] == TERMINAL_WIDENED_PREAMBLE

    # 4. Nearest
    s4 = nearest([0], state=UNKNOWN, corpus=corpus, pre_vetted=True)
    assert s4[0] == STATE_UNKNOWN_DISCLAIMER
    assert s4[1] == TERMINAL_NEAREST_PREAMBLE

    # 5. Empty
    s5 = empty(state=UNKNOWN)
    assert s5[0] == STATE_UNKNOWN_DISCLAIMER
    assert s5[1] == TERMINAL_EMPTY


def test_state_known_omits_disclaimer(corpus):
    """When state is known, state_unknown_disclaimer is NEVER emitted."""
    for seq in (
        direct_match([0], state="BIHAR", corpus=corpus, pre_vetted=True),
        overflow([0, 1, 2, 3, 4], state="BIHAR", corpus=corpus, pre_vetted=True),
        widened_match([0], state="BIHAR", dropped_boxes=["income_band"], corpus=corpus, pre_vetted=True),
        nearest([0], state="BIHAR", corpus=corpus, pre_vetted=True),
        empty(state="BIHAR"),
    ):
        assert STATE_UNKNOWN_DISCLAIMER not in seq


def test_marks_flank_name_and_summary_strictly(corpus):
    """A name:<scheme_id> mark sits immediately before each name; end:<scheme_id> after its summary."""
    seq = direct_match([0], state="BIHAR", corpus=corpus, pre_vetted=True)
    name_mark_idx = seq.index("name:S1")
    name_chunk_idx = seq.index("scheme:S1:name")
    summary_chunk_idx = seq.index("scheme:S1:summary")
    end_mark_idx = seq.index("end:S1")

    # Name mark is immediately before name chunk
    assert name_mark_idx + 1 == name_chunk_idx
    # End mark is immediately after summary chunk
    assert summary_chunk_idx + 1 == end_mark_idx


def test_section_source_frame_never_comes_before_summary(corpus):
    """section_source_frame never comes before a summary in any terminal sequence."""
    for seq in (
        direct_match([0, 1], state="BIHAR", corpus=corpus, pre_vetted=True),
        overflow([0, 1, 2, 3, 4], state="BIHAR", corpus=corpus, pre_vetted=True),
        widened_match([0, 1], state="BIHAR", dropped_boxes=["income_band"], corpus=corpus, pre_vetted=True),
        nearest([0, 1], state="BIHAR", corpus=corpus, pre_vetted=True),
        empty(state="BIHAR"),
    ):
        assert SECTION_SOURCE_FRAME not in seq
        for i, token in enumerate(seq):
            if token.endswith(":summary"):
                # Ensure section_source_frame is not before it
                assert (i == 0) or (seq[i - 1] != SECTION_SOURCE_FRAME)


# ---------------------------------------------------------------------------
# Filter.speakable() Truth Lock Enforcement (Step 3 Review Probe)
# ---------------------------------------------------------------------------

def test_truth_lock_speakable_filtering_uncarried_state(corpus):
    """Probed on Step 3 branch: answering only one box leaves survivors in
    bitmasks of which speakable() allows NONE, because the others are still
    unasked and non-ANY. Terminals must enforce speakable() before naming any
    scheme.

    The closed `state` set is now the binary MAHARASHTRA/OTHER pair (D6), and
    MAHARASHTRA is carried by several fixture schemes, so it can no longer be
    used as an "uncarried" probe. OTHER, answered alone, still makes the
    point: it correctly survives S1/S2 (state=ANY/central) while hard-missing
    S3/S4/S5 (state=MAHARASHTRA-only) — but S1/S2 are non-ANY on gender and
    social_category, both unasked, so speakable() still allows neither.
    """
    # State OTHER is carried by S1/S2 (state=ANY) but hard-misses S3/S4/S5
    # (state=MAHARASHTRA-only); gender/social_category are left unasked.
    bv = {"state": "OTHER"}

    # Verify that raw survivors() does NOT protect the speaking rule:
    # S1 and S2 (state=ANY) both survive on state alone.
    raw_survs = Filter.survivors(bv, corpus)
    assert len(raw_survs) == 2

    # Verify that speakable() allows none of them (gender/social_category unasked)
    assert all(not Filter.speakable(s, bv, corpus) for s in raw_survs)

    # When rendered via Terminals, speakable() must be enforced:
    # 0 schemes may be spoken, so it falls down ladder to Empty
    seq = render_terminal(box_vector=bv, corpus=corpus)
    assert TERMINAL_EMPTY in seq
    assert not any(_is_scheme_name_token(t) for t in seq)

    # Even if raw survivors are directly passed to direct_match with box_vector,
    # speakable() filters them out!
    seq_direct = direct_match(raw_survs, box_vector=bv, corpus=corpus)
    # If all schemes fail speakable, direct_match emits only preamble and no schemes
    assert seq_direct == (RESULTS_EXACT_PREAMBLE,)


# ---------------------------------------------------------------------------
# Shape Classification & Top-Level Dispatcher Integration
# ---------------------------------------------------------------------------

def test_classify_shape_and_end_to_end_dispatch(fixtures_data, corpus):
    """Test classify_shape and render_terminal on real personas."""
    personas = fixtures_data["personas"]

    # Persona P1: Direct match
    p1_vec = personas["P1"]["demographics"]
    shape, survs, drops = classify_shape(box_vector=p1_vec, corpus=corpus)
    assert shape == DELIVERY_DIRECT_MATCH
    assert 1 <= len(survs) <= tunables.STOP_SURVIVORS
    assert drops == []

    seq_p1 = render_terminal(box_vector=p1_vec, corpus=corpus)
    assert seq_p1[0] == RESULTS_EXACT_PREAMBLE
    assert "name:S1" in seq_p1

    # Widened match: farming outside Maharashtra for female SC on the wrong
    # income. Initial survivors: 0 (S1/S2 both need income_band 75000/30000,
    # not 50000). Rung 1 drops income_band -> S1 (and S2) come back. `state`
    # must be OTHER, not MAHARASHTRA: S3 and S4 are both state=MAHARASHTRA +
    # category=farming now (S4's state D6 fixture migration: KARNATAKA ->
    # MAHARASHTRA, so its only real constraint is state), so any
    # state=MAHARASHTRA + category=farming vector is an immediate direct match
    # on S4, never a 0-survivors-then-widen path — and S3 is unreachable from
    # OTHER since it too is state=MAHARASHTRA-only.
    widened_vec = {
        "state": "OTHER",
        "gender": "female",
        "social_category": "SC",
        "category": "farming",
        "income_band": "50000",
    }
    shape_w, survs_w, drops_w = classify_shape(box_vector=widened_vec, corpus=corpus)
    assert shape_w == DELIVERY_WIDENED_MATCH
    assert drops_w == ["income_band"]
    assert len(survs_w) >= 1

    seq_w = render_terminal(box_vector=widened_vec, corpus=corpus)
    assert seq_w[0] == TERMINAL_WIDENED_PREAMBLE
    assert "drop_income_band" in seq_w
    assert RESULTS_WIDENED_LEAD in seq_w
    assert "name:S1" in seq_w

    # `category` is never widened (T10 D6 as amended 13 Sep). handloom
    # (business_loans) outside Maharashtra has no match and no soft box to
    # relax (S5, the sole business_loans scheme, is state=MAHARASHTRA-only, D6
    # fixture migration: KARNATAKA -> MAHARASHTRA), so the terminal is Nearest,
    # not a widened match that quietly answered a different question.
    subject_vec = {
        "state": "OTHER",
        "gender": "female",
        "social_category": "SC",
        "category": "business_loans",
    }
    shape_s, survs_s, drops_s = classify_shape(box_vector=subject_vec, corpus=corpus)
    assert shape_s == DELIVERY_NEAREST
    assert drops_s == []
    assert len(survs_s) == tunables.NEAREST_CAP

    seq_s = render_terminal(box_vector=subject_vec, corpus=corpus)
    assert seq_s[0] == TERMINAL_NEAREST_PREAMBLE
    assert "drop_category" not in seq_s
    assert SECTION_MENU not in seq_s

    # Nearest delivery: rendered directly or via shape override.
    # Persona P2 (male, GEN) can no longer be used for this: it hard-misses
    # every scheme on gender alone once state=OTHER also excludes S3/S4/S5
    # (all state=MAHARASHTRA-only, D6 fixture migration gave S4 a real state
    # constraint too), so `Filter.nearest(p2_vec, corpus)` is now empty for
    # P2's literal demographics (this was already true of gender=male vs
    # S1/S2's female regardless of state — P2's own "expected_nearest":
    # [S1, S2] never held at the engine level; S4 satisfied this assertion by
    # coincidence in every earlier round, being ANY on every hard box it
    # didn't just literally match). A hand-built vector demonstrates the same
    # soft-only-miss nearest() mechanic instead: business_loans in
    # Maharashtra (matches S5's hard boxes) on the wrong age/income.
    p2_vec = {
        "category": "business_loans",
        "state": "MAHARASHTRA",
        "gender": "male",
        "social_category": "GEN",
        "age": "99",
        "income_band": "999999",
        "occupation": "farmer",
    }
    near_candidates = Filter.nearest(p2_vec, corpus)
    assert len(near_candidates) <= tunables.NEAREST_CAP
    assert len(near_candidates) >= 1

    seq_near = render_terminal(survivors=near_candidates, state="BIHAR", shape=DELIVERY_NEAREST, corpus=corpus, pre_vetted=True)
    assert seq_near[0] == TERMINAL_NEAREST_PREAMBLE
    assert SECTION_MENU not in seq_near
    assert any(_is_scheme_name_token(t) for t in seq_near)

    # Unmatchable hard-box persona: Empty. state=OTHER hard-misses S3/S4/S5
    # (all state=MAHARASHTRA-only, D6 fixture migration); category=education
    # matches no scheme at all, so S1/S2 (state=ANY) never survive either.
    unmatchable_vec = {
        "state": "OTHER",
        "gender": "female",
        "social_category": "ST",
        "category": "education",
    }
    shape_emp, survs_emp, _ = classify_shape(box_vector=unmatchable_vec, corpus=corpus)
    assert shape_emp == DELIVERY_EMPTY
    assert survs_emp == []

    seq_emp = render_terminal(box_vector=unmatchable_vec, corpus=corpus)
    assert seq_emp == (TERMINAL_EMPTY,)


def test_terminals_class_namespace():
    """Verify Terminals class exposes static methods."""
    assert Terminals.direct_match is direct_match
    assert Terminals.overflow is overflow
    assert Terminals.widened_match is widened_match
    assert Terminals.nearest is nearest
    assert Terminals.empty is empty
    assert Terminals.render is render_terminal
    assert Terminals.sequence is terminal_sequence
    assert Terminals.classify_shape is classify_shape


# ---------------------------------------------------------------------------
# Truth-lock fail-closed (Step 5 review, 2026-09-12)
# ---------------------------------------------------------------------------

def test_naming_without_box_vector_raises_rather_than_waving_schemes_through(corpus):
    """An omitted box_vector must never silently disable Filter.speakable().

    Before this was closed, direct_match(raw, corpus=corpus) named the
    fixture schemes under state=OTHER, for which speakable() is False on
    every one of them (see test_truth_lock_speakable_filtering_uncarried_state
    above: S1/S2 survive state=OTHER on state alone, but are gagged because
    gender/social_category are unasked). The lock has to fail closed, not
    open.
    """
    bv = {"state": "OTHER"}
    raw_survs = list(Filter.survivors(bv, corpus))
    assert raw_survs, "probe needs a non-empty survivor set to be meaningful"
    assert all(not Filter.speakable(s, bv, corpus) for s in raw_survs)

    for render in (direct_match, overflow, nearest):
        with pytest.raises(ValueError, match="truth lock"):
            render(raw_survs, state="BIHAR", corpus=corpus)

    with pytest.raises(ValueError, match="truth lock"):
        widened_match(raw_survs, state="BIHAR", dropped_boxes=["age"], corpus=corpus)

    # And with the vector supplied, the same call names nobody.
    seq = direct_match(raw_survs, box_vector=bv, corpus=corpus)
    assert [t for t in seq if t.startswith("name:")] == []


def test_read_caps_come_from_tunables_not_inline(corpus, monkeypatch):
    """The overflow/widened read cap is a tunable, not a 3 typed into the code."""
    monkeypatch.setattr(tunables, "OVERFLOW_READ_CAP", 2)
    seq = overflow([0, 1, 2, 3, 4], state="BIHAR", corpus=corpus, pre_vetted=True)
    assert len([t for t in seq if t.startswith("name:")]) == 2


def test_scheme_id_is_never_guessed_from_an_index():
    """A bitmask index with no corpus must raise, not invent a scheme id."""
    with pytest.raises(ValueError, match="cannot resolve scheme id"):
        direct_match([0, 1], state="BIHAR", corpus=None, pre_vetted=True)
