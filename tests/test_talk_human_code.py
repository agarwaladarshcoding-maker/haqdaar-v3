"""Step 1.3a (f): the "by code" cases of fixtures/talk_human.json as pytest cases.

Each pure-code step-1.3 case (by == "code") is read from the fixture and
checked through fixed code only: no model. The model-worded half of each
want (the sentence the line finally says) is NOT this step.
"""
import json
from pathlib import Path

import pytest

from haqdaar.contracts.types import SEVEN_BOXES, UNASKED
from haqdaar.data import scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.engine import talk_kind, talk_pick, talk_words
from haqdaar.engine import words_tell_me


#: Step-1.3 cases with a fixed-code half in 1.3a. Pure "code" cases plus the
#: code half of hybrids (the model sentence is never asserted here).
CODE_IDS = [
    "fix-2", "for-4", "jump-2", "name-1", "name-2", "name-3",
    "name-4", "name-5", "name-6", "name-7", "not-1", "not-2", "not-3",
    "otherbox-1", "skip-4", "two-1",
    "skip-1", "skip-2", "dontknow-1", "dontknow-2",
    "nothere-1", "nothere-2", "nothere-3", "jump-1",
    "for-1", "for-2", "for-3", "two-2", "many-1", "vague-1", "fix-1",
]
#: Left out: skip-3 and why-1 are model-only (a sorry / a reason sentence).


def _cases():
    path = Path(__file__).resolve().parent.parent / "fixtures" / "talk_human.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [c for c in data["cases"] if c.get("id") in CODE_IDS]


@pytest.fixture(scope="module")
def corpus():
    return Corpus.load("CURRENT")


@pytest.fixture(scope="module")
def index():
    return scheme_index.SchemeIndex.load("CURRENT", embed=lambda texts: 1 / 0)


def _said(cid):
    return next(c["said"] for c in _cases() if c["id"] == cid)


def test_fixture_code_cases_are_all_mapped():
    """Every CODE_ID is in the fixture; every other step-1.3 case is model-only."""
    path = Path(__file__).resolve().parent.parent / "fixtures" / "talk_human.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    step13 = [c["id"] for c in data["cases"] if c.get("step") == "1.3"]
    assert sorted(c["id"] for c in _cases()) == sorted(CODE_IDS)
    assert sorted(set(step13) - set(CODE_IDS)) == ["skip-3", "why-1"]


@pytest.mark.parametrize("cid,want", [
    ("name-1", "pm-kisan"), ("name-2", "mgnrega"), ("name-3", "pm-kisan"),
    ("name-4", "kcc"), ("name-5", "pmay-g"), ("name-6", "pmmy"), ("name-7", "pm-svanidhi"),
])
def test_named_scheme_is_answered_first(index, cid, want):
    """name-1..7: said short, found by name -> a scheme we hold -> answer first, ask nothing."""
    top = index.search(_said(cid), 1)[0]
    assert (top.scheme_id, top.by) == (want, "name")
    assert talk_kind.kind(_said(cid), index) == "held_scheme"


def test_not_1_worker_not_farmer(corpus):
    assert talk_words.spot(_said("not-1"), corpus) == {"occupation": "worker"}


def test_not_2_no_need_set(corpus):
    assert talk_words.spot(_said("not-2"), corpus) == {}


def test_not_3_not_a_farmer(corpus):
    assert talk_words.spot(_said("not-3"), corpus).get("occupation") != "farmer"


def test_fix_2_corrected_need_is_pension(corpus):
    """"not farming, ..." unsets the old need; pension is the need now."""
    assert talk_words.spot(_said("fix-2"), corpus) == {"category": "pension"}


def test_for_4_empty_need_gets_no_question(corpus):
    """Education holds no scheme: nothing to ask, nothing to show."""
    assert talk_words.spot(_said("for-4"), corpus) == {"category": "education", "gender": "female"}
    bv = {b: UNASKED for b in SEVEN_BOXES} | {"category": "education"}
    got = talk_pick.narrow([corpus.scheme_id(i) for i in range(17)], bv, corpus)
    assert got.left == () and got.ask is None


def test_two_1_keeps_both_needs(corpus):
    all_named = talk_words.spot_all(_said("two-1"), corpus)
    assert set(all_named.get("category", ())) == {"farming", "housing"}
    assert "category" not in talk_words.spot(_said("two-1"), corpus)


def test_jump_1_scheme_question_answers_first(index):
    assert talk_kind.kind(_said("jump-1"), index) == "held_scheme"


def test_jump_2_new_need_is_a_question(corpus, index):
    """The new need is spotted; the code part ends here (search on the new
    words only + dropping the scheme in talk is later work, see NOTES-1.3)."""
    assert talk_words.spot(_said("jump-2"), corpus) == {"category": "pension"}
    assert talk_kind.kind(_said("jump-2"), index) == "question"


def test_otherbox_1_state_words_name_no_box(corpus, index):
    """"I am from Maharashtra" names no box by fixed code (the state comes
    from the model's facts); the no-count rule is pinned in test_clarify_picker."""
    assert talk_words.spot(_said("otherbox-1"), corpus) == {}
    assert talk_kind.kind(_said("otherbox-1"), index) == "situation"


def test_skip_4_is_just_tell_me():
    assert words_tell_me.is_just_tell_me(_said("skip-4"))


@pytest.mark.parametrize("cid", ["skip-1", "skip-2"])
def test_skip_lists_stop_the_questions(cid):
    """skip-1/2: the word list fires; the rest (show 2 best) is pinned in test_talk_phrases."""
    assert words_tell_me.is_just_tell_me(_said(cid))


def test_dontknow_1_sets_unknown():
    from haqdaar.engine import words_no_answer
    assert words_no_answer.no_answer(_said("dontknow-1")) == "dont_know"


def test_dontknow_2_sets_unknown():
    from haqdaar.engine import words_no_answer
    assert words_no_answer.no_answer(_said("dontknow-2")) == "wont_say"


@pytest.mark.parametrize("cid,want", [
    ("nothere-1", "ayushman"), ("nothere-2", "ration_card"), ("nothere-3", "ladli_behna"),
])
def test_not_held_is_its_own_kind(index, cid, want):
    """nothere-1..3: named by the not-held list, never a situation for questions."""
    from haqdaar.data import scheme_names
    assert scheme_names.find_not_held(_said(cid)) == want
    assert talk_kind.kind(_said(cid), index) == "not_held_scheme"


def test_for_1_names_pension_for_the_mother(corpus):
    """The need is pension; the mother words name a female beneficiary by code.
    (Questions about HER need person-switching: later work, see NOTES-1.3.)"""
    assert talk_words.spot(_said("for-1"), corpus) == {"category": "pension", "gender": "female"}


def test_for_2_no_farmer_from_the_husband(corpus):
    """Work is NOT farmer. (Need = pension needs widow logic: later work.)"""
    got = talk_words.spot(_said("for-2"), corpus)
    assert got.get("occupation") != "farmer"
    assert got.get("gender") == "female"


def test_two_2_sick_is_health_and_work_is_not_his(corpus):
    all_named = talk_words.spot_all(_said("two-2"), corpus)
    assert "farmer" not in all_named.get("occupation", [])
    assert "health" in all_named.get("category", [])


def test_many_1_takes_need_and_gender(corpus):
    """The years and the state come from the model's facts; need + gender are code."""
    got = talk_words.spot(_said("many-1"), corpus)
    assert got == {"category": "pension", "gender": "female"}


def test_vague_fix_for3_do_not_guess(corpus, index):
    """vague-1 / fix-1 / for-3: fixed code guesses nothing (no number, no box);
    the yes-or-no question, the rebuild and the person switch are later work."""
    for cid in ("vague-1", "fix-1", "for-3"):
        assert talk_words.spot(_said(cid), corpus) == {}, cid
    assert talk_kind.kind(_said("vague-1"), index) == "situation"
