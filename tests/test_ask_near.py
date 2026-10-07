"""PLAN 9, step N3: none fits -> the nearest schemes and what stands in the way; a scheme that fits so far
with conditions we did not ask about. Fake model, no network. The blocker tests use a small synthetic corpus
(as test_ask_first does); the talk tests use the live snapshot."""
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables
from haqdaar.data import chunk_index, log_text, scheme_index
from haqdaar.contracts.types import Hangup
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.engine.talk import _Talk
from haqdaar.engine import talk_pick
from haqdaar.prompts import talk as prompt
from tests.test_qa_engine import QAAudio
from tests.test_talk import Client
from tests.test_ask_first import Parts, Synth, _blank, _hit, _schemes_block, _talk, _turn

OK = {"action": "answer", "say": "Okay.", "facts": {}, "scheme": ""}


@pytest.fixture(scope="module")
def corpus():
    return Corpus.load("CURRENT")


@pytest.fixture(scope="module")
def idx():
    return scheme_index.SchemeIndex.load("CURRENT", embed=lambda texts: 1 / 0)


def _pension(bv_extra):
    return _blank(category="pension", **bv_extra)


def _synth(rows):
    return Synth([{"category": ("pension",), **r} for r in rows] + [{"age": ("41-79",), "gender": ("male", "female"),
                                                                      "occupation": ("farmer", "worker")}])


# --- the blockers --------------------------------------------------------------

def test_a_miss_on_age_is_said_as_a_range_and_can_not_change():
    corpus = _synth([{"age": ("18-35", "36-39", "40-40")}])
    got = talk_pick.blockers(["s0"], _pension({"age": "41-79"}), corpus)
    assert got["s0"] == (talk_pick.Blocker("age", "18 to 40", "41 to 79", False),)


def test_a_miss_on_gender_is_listed_though_it_is_a_hard_box():
    corpus = _synth([{"gender": ("female",)}])
    (b,) = talk_pick.blockers(["s0"], _pension({"gender": "male"}), corpus)["s0"]
    assert (b.box, b.needs, b.said, b.can_change) == ("gender", "Woman", "Man", False)


def test_a_miss_on_work_can_change():
    corpus = _synth([{"occupation": ("farmer",)}])
    (b,) = talk_pick.blockers(["s0"], _pension({"occupation": "worker"}), corpus)["s0"]
    assert (b.box, b.needs, b.said, b.can_change) == ("occupation", "Farmer", "Worker", True)
    assert b.line("their work") == ("their work: the scheme needs Farmer, the caller said Worker (can change: yes)")


def test_a_box_not_known_or_not_asked_is_never_a_blocker():
    corpus = _synth([{"gender": ("female",), "age": ("18-35",)}])
    assert talk_pick.blockers(["s0"], _pension({}), corpus)["s0"] == ()
    assert talk_pick.blockers(["s0"], _pension({"gender": "UNKNOWN", "age": "UNKNOWN"}), corpus)["s0"] == ()
    assert talk_pick.near(["s0"], _pension({"gender": "UNKNOWN"}), corpus) == []      # fits: nothing in the way


def test_the_kind_of_help_is_never_a_blocker_and_another_kind_is_never_near():
    corpus = Synth([{"category": ("farming",), "gender": ("female",)}, {"category": ("pension",), "gender": ("female",)},
                    {"category": ("pension",), "gender": ("male",)}])
    bv = _blank(category="pension", gender="male")
    assert talk_pick.blockers(["s0", "s1"], bv, corpus)["s0"][0].box == "gender"   # category is left out
    assert [sid for sid, _b in talk_pick.near(["s0", "s1"], bv, corpus)] == ["s1"]


def test_one_miss_before_two_search_order_inside_and_two_at_most():
    rows = [{"gender": ("female",), "age": ("18-35",)},                 # s0: two misses
            {"gender": ("female",)},                                    # s1: one
            {"gender": ("female",), "age": ("18-35",), "occupation": ("farmer",)},   # s2: three: never near
            {"age": ("18-35",)},                                        # s3: one
            {"occupation": ("farmer",)}]                                # s4: one
    corpus = Synth([{"category": ("pension",), **r} for r in rows] + [{"age": ("41-79",), "gender": ("male", "female"),
                                                                       "occupation": ("farmer", "worker")}])
    bv = _pension({"age": "41-79", "gender": "male", "occupation": "worker"})
    ids = ["s0", "s1", "s2", "s3", "s4"]
    assert [s for s, _b in talk_pick.near(ids, bv, corpus)] == ["s1", "s3"]
    assert [s for s, _b in talk_pick.near(["s4", "s0", "s3"], bv, corpus)] == ["s4", "s3"]   # one-miss ones first, search order
    assert [s for s, _b in talk_pick.near(["s0", "s2"], bv, corpus)] == ["s0"]
    assert talk_pick.near(["s2"], bv, corpus) == []


def test_nothing_near_when_every_scheme_misses_by_three(monkeypatch):
    corpus = Synth([{"category": ("pension",), "gender": ("female",), "age": ("18-35",), "occupation": ("farmer",)},
                    {"age": ("41-79",), "gender": ("male",), "occupation": ("worker",)}])
    assert talk_pick.near(["s0"], _pension({"age": "41-79", "gender": "male", "occupation": "worker"}), corpus) == []


# --- what the model is given ---------------------------------------------------

PENSION = {"category": "pension", "age": "41-79", "gender": "male"}      # on the live snapshot: apy (age), ignwps (gender)


def _pension_turn(corpus, tmp_path, idx, name="near"):
    t = _talk(corpus, tmp_path, idx, name)
    t.bv.update(PENSION)
    return t, *_turn(t, "I need a pension", [OK])


def test_the_prompt_has_the_near_lines_and_the_schemes_text_not_a_bare_does_not_fit(corpus, tmp_path, idx):
    t, (_a, _s), client = _pension_turn(corpus, tmp_path, idx)
    block = _schemes_block(client.calls[0])
    assert t.left == ()
    assert "NEAR, DOES NOT FIT:" in block
    assert "In the way: their age: the scheme needs 18 to 40, the caller said 41 to 79 (can change: no)" in block
    assert "In the way: man or woman: the scheme needs Woman, the caller said Man (can change: no)" in block
    assert block.count("NEAR, DOES NOT FIT") == 2 and "mark: near" in block
    assert "mark: does not fit" not in block
    assert "[apy]" in block and "[ignwps]" in block               # the schemes' own text came with them


def test_the_near_schemes_come_through_the_parts_and_are_not_pushed_down(corpus, tmp_path, idx, monkeypatch):
    parts = Parts(idx.ids, lambda q: [_hit("kcc", "KCC-TEXT"), _hit("apy", "APY-TEXT"), _hit("ignwps", "IGN-TEXT")])
    monkeypatch.setitem(chunk_index._loaded_chunks, corpus.snapshot_id, parts)
    monkeypatch.setattr(tunables, "TALK_CHUNKS", True)
    t, (_a, _s), client = _pension_turn(corpus, tmp_path, idx)
    block = _schemes_block(client.calls[0])
    assert "APY-TEXT" in block and "IGN-TEXT" in block and "KCC-TEXT" not in block
    assert block.count("NEAR, DOES NOT FIT") == 2 and "mark: does not fit" not in block
    assert parts.fits[0]["apy"] != talk_pick.DOES_NOT_FIT                     # the search is not told to bury it


def test_the_rules_are_added_only_on_a_turn_that_has_the_lines(corpus):
    def system(cards):
        return prompt.build("en", "", {}, {}, None, (), cards, "hi", ask_first=True)[0]["content"]
    assert "NEAR, DOES NOT FIT lines" in system([("a", "near", "x\nNEAR, DOES NOT FIT: A.")])
    assert "NEAR, DOES NOT FIT lines" not in system([("a", "fits", "x")])
    assert '"it may fit, if ..."' in system([("a", "fits", "x\nFITS SO FAR. Conditions we did not ask about: y")])
    assert '"it may fit, if ..."' not in system([("a", "fits", "x")])
    off = prompt.build("en", "", {}, {}, None, (), [("a", "near", "NEAR, DOES NOT FIT")], "hi", ask_first=False)[0]["content"]
    assert "NEAR, DOES NOT FIT lines" not in off


def test_nothing_near_the_card_is_as_before(corpus, tmp_path, idx, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_NEAR_K", 0)
    t, (_a, _s), client = _pension_turn(corpus, tmp_path, idx)
    block = _schemes_block(client.calls[0])
    assert "NEAR" not in block and "mark: does not fit" in block and "In the way" not in block


def test_switch_off_no_near_lines(corpus, tmp_path, idx, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ASK_FIRST", False)
    t, (_a, _s), client = _pension_turn(corpus, tmp_path, idx)
    assert "NEAR" not in client.calls[0] and "In the way" not in client.calls[0]


def test_the_act_row_names_the_near_schemes_and_their_boxes(corpus, tmp_path, idx):
    audio, client = QAAudio([Hangup()], "en"), Client([OK])
    log = Log.open("near-row", corpus.snapshot_id, logs_dir=str(tmp_path))
    t = _Talk(audio, SimpleNamespace(client=client), corpus, log, "en", idx)
    t.bv.update(PENSION)
    t.run("I need a pension")
    acts = [r for r in log_text.read_rows(t.log.path) if r.get("ev") == "act" and r.get("near")]
    assert acts and acts[0]["near"] == {"ignwps": ["gender"], "apy": ["age"]}


def test_a_corrected_fact_brings_the_scheme_back_on_the_next_turn(corpus, tmp_path, idx):
    t, (_a, _s), client = _pension_turn(corpus, tmp_path, idx)
    assert "NEAR, DOES NOT FIT: " in client.calls[0]
    fix = {"action": "answer", "say": "Thank you.", "facts": {"age": "18-35"}, "scheme": ""}
    (_a, _s), client = _turn(t, "no, I am 35", [fix])
    assert t.bv["age"] == "18-35" and "apy" in t.left
    (_a, _s), client = _turn(t, "tell me more", [OK])
    block = _schemes_block(client.calls[0])
    assert "NEAR" not in block and "[apy]" in block


# --- the scheme in talk that does not fit --------------------------------------

def test_the_scheme_in_talk_that_does_not_fit_carries_its_blocker(corpus, tmp_path, idx):
    t = _talk(corpus, tmp_path, idx)
    t.bv.update({"category": "farming", "occupation": "street_vendor"})      # smam fits; pm-kisan needs a farmer
    t.focus = "pm-kisan"
    (_a, _s), client = _turn(t, "which papers are needed", [OK])
    block = _schemes_block(client.calls[0])
    assert ("mark: does not fit. In the way: their work: the scheme needs Farmer, the caller said Street vendor "
            "(can change: yes)") in block
    assert "NEAR" not in block                                              # something fits: no near list


# --- may fit, if ---------------------------------------------------------------

def _farmer(corpus, tmp_path, idx, monkeypatch, parts):
    t = _talk(corpus, tmp_path, idx)
    t.bv.update({"category": "farming", "occupation": "farmer"})
    t.just_tell = True                                                     # the gate is open
    if parts:
        monkeypatch.setattr(tunables, "TALK_CHUNKS", True)
        monkeypatch.setitem(chunk_index._loaded_chunks, corpus.snapshot_id, parts)
    return _turn(t, "farming schemes", [OK])


def test_conditions_not_asked_about_are_one_line_for_a_scheme_with_notes_and_none_without(corpus, tmp_path, idx, monkeypatch):
    parts = Parts(idx.ids, lambda q: [_hit("pm-kisan", "KISAN-TEXT"), _hit("pmfby", "FBY-TEXT")])
    (_a, _s), client = _farmer(corpus, tmp_path, idx, monkeypatch, parts)
    block = _schemes_block(client.calls[0])
    kisan, fby = block.split("[pm-kisan]")[1].split("[pmfby]")[0], block.split("[pmfby]")[1]
    assert "FITS SO FAR. Conditions we did not ask about: Requires cultivable land holding" in kisan
    assert "FITS SO FAR" not in fby
    assert block.count("FITS SO FAR") == 1


def test_the_notes_are_cut_to_about_two_hundred_characters(corpus, tmp_path, idx, monkeypatch):
    parts = Parts(idx.ids, lambda q: [_hit("pmay-g", "PMAY-TEXT")])
    t = _talk(corpus, tmp_path, idx)
    t.bv.update({"category": "housing"})
    t.just_tell = True
    monkeypatch.setattr(tunables, "TALK_CHUNKS", True)
    monkeypatch.setitem(chunk_index._loaded_chunks, corpus.snapshot_id, parts)
    (_a, _s), client = _turn(t, "a house", [OK])
    line = [l for l in _schemes_block(client.calls[0]).split("\n") if l.startswith("FITS SO FAR")][0]
    assert line.endswith(" ...") and len(line.split(": ", 1)[1]) <= 205


def test_a_whole_card_holds_the_notes_already_so_the_line_only_points_to_them(corpus, tmp_path, idx, monkeypatch):
    (_a, _s), client = _farmer(corpus, tmp_path, idx, monkeypatch, None)
    block = _schemes_block(client.calls[0])
    assert block.count("Requires cultivable land holding") == 1             # not said twice
    assert "FITS SO FAR. Conditions we did not ask about: see its exclusions line." in block
