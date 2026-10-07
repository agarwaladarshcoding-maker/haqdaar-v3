"""PLAN 9b, step N6: more boxes for the talk (what a scheme gives, the kind inside the kind, the home state, 20 yes / no
facts) and schemes with no recorded clips (talk-only). No model, no network. The snapshot writer is proved by building
into a temp folder; the big kind is the made-up one of tests/test_ask_scale.py with the new boxes filled in."""
import json
import math
import random
import statistics
import time
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables, vocab
from haqdaar.contracts.types import FACT_BOXES, SEVEN_BOXES, TALK_BOXES, UNASKED, UNKNOWN, Ask, Stop
from haqdaar.data import chunk_index
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.engine import planner, talk_pick, terminals
from haqdaar.engine.filter import Filter
from haqdaar.engine.talk import _Talk, _take_facts
from haqdaar.prompts import talk as prompt
from tests.test_ask_first import Synth, _blank
from tests.test_ask_scale import ALL, ALL_IDS, KIND, KIND_IDS, Idx, Parts, make_corpus


# --- a temp snapshot of made-up rows ------------------------------------------------------------------------------

def _row(sid, **fields):
    chunks = {lang: {name: f"{sid} {name} {lang}" for name in
                     ("name", "summary", "benefit_text", "who_can_apply", "documents", "how_to_apply")}
              for lang in ("en", "hi", "mr")}
    return {"scheme_id": sid, "category": "farming", "aliases_en": [f"alias {sid}"], "chunks": chunks, **fields}


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    snap, audio = tmp_path / "snapshots", tmp_path / "audio"
    snap.mkdir()
    audio.mkdir()
    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio))
    return snap, audio


def _build(dirs, rows, snap_id="t", **kw):
    snap, audio = dirs
    kw.setdefault("render_stubs", True)
    build_snapshot(rows, snapshot_id=snap_id, snapshots_dir=snap, audio_dir=audio, **kw)
    return Corpus.load(snap_id)


def _holds(corpus, box, value):
    return {corpus.scheme_id(i) for i in range(len(corpus._scheme_ids)) if corpus.mask(box, value) >> i & 1}


def test_the_writer_makes_masks_for_the_new_boxes_from_rows(dirs):
    rows = [
        _row("a1", gives="loan", sub_kind="crops", home_state="KERALA", facts={"bpl_card": "needs", "widow": "bars"}),
        _row("b2", gives=["loan", "cash_aid"], facts={}),                      # a list for gives; no sub_kind, no facts
        _row("c3"),                                                           # no new field at all
        _row("d4", gives="insurance", facts={"bpl_card": "bars"}),
    ]
    corpus = _build(dirs, rows)
    assert corpus.values("gives") == vocab.GIVES and corpus.values("f_bpl_card") == ("yes", "no")
    assert corpus.values("sub_kind") == ("crops",) and corpus.values("home_state") == vocab.HOME_STATE
    assert len(vocab.HOME_STATE) == 37
    assert corpus.values("f_rural") == ()                    # no row names it: the box is not written
    assert _holds(corpus, "f_bpl_card", "yes") == {"a1", "b2", "c3"}        # needs: under yes only; d4 bars: not under yes
    assert _holds(corpus, "f_bpl_card", "no") == {"b2", "c3", "d4"}         # bars: under no only; a1 needs: not under no
    assert _holds(corpus, "f_widow", "yes") == {"b2", "c3", "d4"} and _holds(corpus, "f_widow", "no") == {"a1", "b2", "c3", "d4"}
    assert _holds(corpus, "gives", "loan") == {"a1", "b2", "c3"}            # a list holds both; a row with none = any value
    assert _holds(corpus, "gives", "cash_aid") == {"b2", "c3"} and _holds(corpus, "gives", "insurance") == {"c3", "d4"}
    assert _holds(corpus, "sub_kind", "crops") == {"a1", "b2", "c3", "d4"}  # the others name no sub_kind
    assert _holds(corpus, "home_state", "KERALA") == {"a1", "b2", "c3", "d4"} and _holds(corpus, "home_state", "GOA") == {"b2", "c3", "d4"}


def test_sub_kind_values_are_the_codes_the_rows_hold_in_sorted_order(dirs):
    corpus = _build(dirs, [_row("a1", sub_kind="fish"), _row("b2", sub_kind=["crops", "animals"]), _row("c3", sub_kind="ANY")])
    assert corpus.values("sub_kind") == ("animals", "crops", "fish")
    assert _holds(corpus, "sub_kind", "fish") == {"a1", "c3"}


@pytest.mark.parametrize("fields, text", [
    ({"gives": "gold"}, "gives value 'gold' not in vocab"),
    ({"gives": ["loan", "gold"]}, "gives value 'gold' not in vocab"),
    ({"home_state": "ATLANTIS"}, "home_state value 'ATLANTIS' not in vocab"),
    ({"sub_kind": "Big Crops"}, "sub_kind value 'Big Crops' is not a short code"),
    ({"facts": {"nope": "needs"}}, "fact 'nope' not in vocab"),
    ({"facts": {"widow": "maybe"}}, "fact widow value 'maybe' is not needs or bars"),
])
def test_an_unknown_code_fails_the_build_and_names_the_scheme(dirs, fields, text):
    with pytest.raises(ValueError) as err:
        _build(dirs, [_row("good1"), _row("bad7", **fields)])
    assert "bad7" in str(err.value) and text in str(err.value)


def test_no_chip_keys_for_the_new_boxes_and_the_seven_keep_theirs(dirs):
    rows = [_row("a1", gives="loan", sub_kind="crops", facts={"widow": "needs"}, gender="female")]
    corpus = _build(dirs, rows)
    manifest = json.loads((dirs[0] / "t" / "manifest.json").read_text())
    ids = " ".join(manifest["templates"])
    assert "chip_gender_female" in ids and "chip_state_MAHARASHTRA" in ids
    for box in ("gives", "sub_kind", "f_widow", "home_state"):
        assert f"chip_{box}_" not in ids
    assert all("f_widow" not in str(meta.get("line_id", "")) for meta in manifest["render_keys"].values())


def test_data_without_the_new_fields_builds_the_snapshot_as_before_and_the_talk_walks_the_seven(dirs):
    rows = [_row(f"s{i}", gender="female" if i < 4 else "ANY", occupation="farmer" if i < 2 else "ANY") for i in range(6)]
    corpus = _build(dirs, rows)
    vocab_json = json.loads((dirs[0] / "t" / "vocab.json").read_text())
    assert set(vocab_json["boxes"]) == set(SEVEN_BOXES)
    assert talk_pick.boxes_of(corpus) == SEVEN_BOXES
    bv = _blank(category="farming")
    got = talk_pick.narrow([f"s{i}" for i in range(6)], bv, corpus)
    assert got.ask in SEVEN_BOXES and got.ask == planner.next_action(bv, talk_pick.SubCorpus(corpus, range(6)),
                                                                     stop_survivors=2, tie_break="easy_first").box
    assert not any(b in vocab_json["boxes"] for b in TALK_BOXES[7:])
    # a fact the model sets for a box this snapshot does not hold is dropped, not taken
    t, _ = _talk(corpus, dirs[0].parent)
    assert _take_facts({"f_rural": "yes", "gives": "loan"}, t.bv, corpus, t.log, 1) == set()
    assert t.bv["f_rural"] == UNASKED


# --- the talk-only schemes ----------------------------------------------------------------------------------------

def test_a_clipless_scheme_is_dropped_as_before_and_kept_as_talk_only_with_the_flag(dirs):
    keys = _row("k1", gender="female")
    plain = _row("t2", gender="male")
    snap, audio = dirs
    build_snapshot([keys], snapshot_id="stubs", snapshots_dir=snap, audio_dir=audio, render_stubs=True)   # the clips of k1
    build_snapshot([keys, plain], snapshot_id="old", snapshots_dir=snap, audio_dir=audio, only_with_audio=True)
    assert Corpus.load("old")._scheme_ids == ("k1",)                       # unchanged: no flag, the clipless one is dropped
    build_snapshot([keys, plain], snapshot_id="new", snapshots_dir=snap, audio_dir=audio, only_with_audio=True,
                   talk_only_rest=True)
    corpus = Corpus.load("new")                                           # would raise if t2's clips were looked for
    manifest = json.loads((snap / "new" / "manifest.json").read_text())
    assert corpus._scheme_ids == ("k1", "t2") and set(manifest["chunks"]) == {"k1"}
    rows = {json.loads(l)["scheme_id"]: json.loads(l) for l in (snap / "new" / "schemes.jsonl").read_text().splitlines()}
    assert rows["t2"]["talk_only"] is True and "talk_only" not in rows["k1"] and "chunk_keys" not in rows["t2"]
    assert corpus.chunks("t2", "en") == () and len(corpus.chunks("k1", "en")) == 6
    assert corpus.alias_lookup("alias t2", "en") == () and corpus.alias_lookup("alias k1", "en") == ("k1",)


def test_the_talk_shows_a_talk_only_scheme_and_the_keys_path_never_offers_it(dirs):
    snap, audio = dirs
    keys = _row("k1")
    build_snapshot([keys], snapshot_id="stubs", snapshots_dir=snap, audio_dir=audio, render_stubs=True)
    flagged = _row("t2", talk_only=True, chunks={"en": _row("t2")["chunks"]["en"]})        # English text only
    build_snapshot([keys, flagged], snapshot_id="m", snapshots_dir=snap, audio_dir=audio, only_with_audio=True,
                   enforce_readback_gate=False)
    corpus = Corpus.load("m")
    t, _ = _talk(corpus, snap.parent)
    assert "t2 name en" in t.texts.card("t2", "en")                        # the talk's card comes from the text
    assert talk_pick.narrow(["k1", "t2"], _blank(category="farming"), corpus).left == ("k1", "t2")
    bv = _blank(category="farming")
    assert Filter.speakable(0, bv, corpus) is True and Filter.speakable(1, bv, corpus) is False
    assert Filter.speakable("t2", bv, corpus) is False and Filter.speakable({"talk_only": True}, bv, corpus) is False
    shape, schemes, _drops = terminals.classify_shape(box_vector=bv, corpus=corpus)
    assert schemes == [0]                                                  # k1 only
    only = _row("t3", talk_only=True)
    build_snapshot([only], snapshot_id="alone", snapshots_dir=snap, audio_dir=audio, only_with_audio=True)
    corpus = Corpus.load("alone")
    shape, schemes, _drops = terminals.classify_shape(box_vector=bv, corpus=corpus)     # the only survivor is talk-only
    assert shape == terminals.DELIVERY_EMPTY and schemes == []             # "nothing to read", no crash
    assert terminals.terminal_sequence(box_vector=bv, corpus=corpus) == (terminals.TERMINAL_EMPTY,)
    assert Filter.nearest(bv, corpus) == ()


def test_a_talk_only_row_needs_english_text_only_and_a_normal_row_still_needs_three_languages(dirs):
    snap, audio = dirs
    english = {"talk_only": True, "chunks": {"en": _row("x")["chunks"]["en"]}}
    build_snapshot([_row("t1", **english)], snapshot_id="ok", snapshots_dir=snap, audio_dir=audio, enforce_readback_gate=True)
    from haqdaar.data.pipeline.p6_snapshot import BuildGateError
    with pytest.raises(BuildGateError):
        build_snapshot([_row("t2", chunks={"en": _row("x")["chunks"]["en"]})], snapshot_id="no", snapshots_dir=snap,
                       audio_dir=audio, enforce_readback_gate=True)


# --- the talk with the new boxes -------------------------------------------------------------------------------------

def _talk(corpus, tmp_path):
    idx = Idx()
    log = Log.open("boxes", "big", logs_dir=str(tmp_path))
    t = _Talk(SimpleNamespace(), None, corpus, log, "en", idx)
    t.stage = {}
    t.heard.append("pension")
    return t, idx


class _Facts(Synth):
    """Synth, with the closed list a snapshot holds for a yes / no box: both answers once any row names the box."""

    def values(self, box):
        if vocab.fact_of(box):
            return vocab.YES_NO if any(box in row for row in self._rows) else ()
        return super().values(box)


def _fact_rows():
    """12 schemes of one kind. s0-s3 need a BPL card, s4-s5 bar one (they are for the better off), s6-s7 are for a widow,
    the rest name nothing. Nothing in the seven boxes splits them."""
    rows = []
    for n in range(12):
        row = {"category": ("pension",)}
        if n < 4:
            row["f_bpl_card"] = ("yes",)
        elif n < 6:
            row["f_bpl_card"] = ("no",)
        if n in (6, 7):
            row["f_widow"] = ("yes",)
        rows.append(row)
    return _Facts(rows)


def test_the_planner_with_default_arguments_ignores_the_new_boxes_and_the_talk_list_asks_them():
    corpus = _fact_rows()
    bv = _blank(category="pension")
    sub = talk_pick.SubCorpus(corpus, range(12))
    assert isinstance(planner.Planner.next_action(bv, sub), Stop)                       # the keys path: nothing in the seven splits
    assert isinstance(planner.next_action(bv, sub, boxes=talk_pick.boxes_of(corpus)), Ask)
    assert talk_pick.boxes_of(corpus) == SEVEN_BOXES + ("f_bpl_card", "f_widow")
    got = talk_pick.narrow([f"s{n}" for n in range(12)], bv, corpus)
    assert got.ask == "f_bpl_card" and got.values == ("yes", "no")


def test_a_fact_answered_by_key_1_or_2_and_the_hint_says_yes_and_no(tmp_path):
    corpus = _fact_rows()
    t, _ = _talk(corpus, tmp_path)
    t.left = tuple(corpus._scheme_ids)
    t.last_asked = "f_bpl_card"
    say = t._add_keys("ask", "Do you have a BPL card?", 0)
    assert say.endswith("Press 1 for yes, 2 for no, 0 if you do not know.") and t._kbox == "f_bpl_card"
    assert t._key_words("2") == "no" and t.bv["f_bpl_card"] == "no"
    assert t._just[-1] == ("f_bpl_card", "no", "key")
    t.bv["f_bpl_card"] = UNASKED
    assert t._key_words("1") == "yes" and t.bv["f_bpl_card"] == "yes"
    assert talk_pick.live_values("f_bpl_card", t.left, corpus) == ["yes", "no"]        # yes first, always


def test_just_heard_and_the_read_back_use_plain_words_never_a_code_or_a_bare_yes(tmp_path):
    corpus = _fact_rows()
    t, _ = _talk(corpus, tmp_path)
    t.bv.update(f_bpl_card="yes", f_widow="no")
    heard = prompt.just_heard([("f_bpl_card", "yes", "key"), ("f_widow", "no", "voice"), ("f_widow", "UNKNOWN", "key")])
    assert "has a BPL card (by key)" in heard and "is not a widow (by voice)" in heard
    assert "= yes" not in heard and "f_bpl_card" not in heard
    facts = " | ".join(t._recap_facts())
    assert facts == "has a BPL card | is not a widow"
    assert prompt.say_value("f_bpl_card", "yes", "hi") == "has a BPL card"             # the fixed read-back
    t.bv.update(gives="loan", home_state="KERALA")
    assert t._recap_facts() == ["wants a loan", "lives in Kerala", "has a BPL card", "is not a widow"]


def test_a_blocker_for_a_missed_fact_reads_the_scheme_needs_and_can_change(tmp_path):
    corpus = _fact_rows()
    bv = _blank(category="pension", f_bpl_card="no", f_widow="no")
    got = talk_pick.blockers(["s0", "s6", "s5"], bv, corpus)
    (bpl,), (widow,) = got["s0"], got["s6"]
    assert (bpl.box, bpl.needs, bpl.said, bpl.can_change) == ("f_bpl_card", "has a BPL card", "no", True)
    line = bpl.line(prompt.BOX_MEANING["f_bpl_card"])
    assert "the scheme needs: has a BPL card; the caller said: no" in line and "can change: yes" in line
    assert widow.can_change is False and widow.line("x").endswith("(can change: no)")
    assert "is a widow" in widow.line("x")
    assert got["s5"] == ()                                                              # s5 bars a card: "no" fits
    bv2 = _blank(category="pension", f_bpl_card="yes")
    assert talk_pick.blockers(["s5"], bv2, corpus)["s5"][0].needs == "has no BPL card"  # bars: the words of "no"
    assert talk_pick.mark("s0", _blank(category="pension"), corpus) == talk_pick.NOT_KNOWN     # needs a card: not asked yet
    assert talk_pick.mark("s0", bv, corpus) == talk_pick.DOES_NOT_FIT


def test_a_fact_from_free_talk_is_taken_when_its_value_is_in_the_corpus(tmp_path):
    corpus = _fact_rows()
    t, _ = _talk(corpus, tmp_path)
    assert _take_facts({"f_bpl_card": "Yes"}, t.bv, corpus, t.log, 1) == {"f_bpl_card"} and t.bv["f_bpl_card"] == "yes"
    assert _take_facts({"f_widow": False}, t.bv, corpus, t.log, 1) == {"f_widow"} and t.bv["f_widow"] == "no"
    assert _take_facts({"f_rural": "yes", "f_widow": "maybe"}, t.bv, corpus, t.log, 1) == set()   # not held / not a value


def test_keys_out_holds_only_the_seven(tmp_path):
    corpus = _fact_rows()
    t, _ = _talk(corpus, tmp_path)
    t.bv.update(category="pension", f_bpl_card="yes", gives="loan")
    out = t._keys_out()
    assert set(out) == set(SEVEN_BOXES) and out["category"] == "pension"
    back, _ = _talk(corpus, tmp_path)                                  # and a talk that comes back from the keys holds the new ones
    again = _Talk(SimpleNamespace(), None, corpus, back.log, "en", back.index, bv=out)
    assert set(again.bv) == set(TALK_BOXES) and again.bv["f_bpl_card"] == UNASKED


def test_the_prompt_shows_only_the_new_boxes_that_still_cut_the_list(tmp_path):
    corpus = _fact_rows()
    ids = [f"s{n}" for n in range(12)]
    bv = _blank(category="pension")
    shown = talk_pick.model_boxes(ids, bv, corpus, 6)
    assert shown == {"f_bpl_card": ("yes", "no"), "f_widow": ("yes", "no")}
    assert talk_pick.model_boxes(ids, {**bv, "f_bpl_card": "yes"}, corpus, 6).keys() == {"f_widow"}     # answered: not shown
    assert talk_pick.model_boxes(ids[8:], bv, corpus, 6) == {}                                           # nothing in these splits
    assert list(talk_pick.model_boxes(ids, bv, corpus, 1)) == ["f_bpl_card"]                             # the cap; the best cut first
    assert list(talk_pick.model_boxes(ids, bv, corpus, 0, must={"f_widow"})) == ["f_widow"]              # the box asked is always in
    msgs = prompt.build("en", "", {}, {**{b: corpus.values(b) for b in SEVEN_BOXES}, **shown}, "f_bpl_card", ["f_bpl_card"], [], "x")
    assert "- f_bpl_card (has a BPL card): yes, no" in msgs[1]["content"]
    assert '(ask it like: "Do you have a BPL card?")' in msgs[1]["content"]


# --- a big kind with the new boxes ------------------------------------------------------------------------------------

NEW_VALUES = {
    "gives": vocab.GIVES,
    "sub_kind": ("pension_old", "pension_widow", "pension_disabled", "pension_farmer", "pension_worker", "pension_other"),
    "home_state": vocab.HOME_STATE,
    **{b: vocab.YES_NO for b in FACT_BOXES[:12]},
}
COMMON_GIVES = ("cash_aid", "monthly_pension", "insurance", "loan", "subsidy", "training", "house", "health_cover",
                "scholarship", "food")
STATES = ("MAHARASHTRA", "KERALA", "UTTAR_PRADESH", "BIHAR", "TAMIL_NADU", "GUJARAT", "RAJASTHAN", "WEST_BENGAL",
          "ODISHA", "KARNATAKA")


def _fill(rnd, i, row):
    """A plausible mix for a kind (not fitted to the test): every scheme gives something (one thing, a second one in
    1 of 6); every scheme of the kind names its sub_kind; half are the centre's (no state), half are one state's (a few
    hold two); a scheme names 2 to 5 of the 12 facts, mostly as a need (7 in 10), the rest as a bar."""
    gives = rnd.sample(COMMON_GIVES, 2 if rnd.random() < 1 / 6 else 1)
    row["gives"] = tuple(gives)
    row["sub_kind"] = (rnd.choice(NEW_VALUES["sub_kind"]),)
    if rnd.random() < 0.5:
        row["home_state"] = tuple(rnd.sample(STATES, 2 if rnd.random() < 0.15 else 1))
    for box in rnd.sample(FACT_BOXES[:12], rnd.randint(2, 5)):
        row[box] = ("yes",) if rnd.random() < 0.7 else ("no",)


@pytest.fixture(scope="module")
def bigfacts():
    return make_corpus(extra=_fill, extra_values=NEW_VALUES)


def _walk(corpus, known=None):
    """The worst answer to each question until the picker stops: the answer that leaves the most schemes."""
    bv = _blank(category="pension") | (known or {})
    steps = []
    nar = talk_pick.narrow(KIND_IDS, bv, corpus)
    while nar.ask and len(steps) < 30:
        before = len(nar.left)
        worst = max(nar.values, key=lambda v: len(talk_pick.narrow(KIND_IDS, bv | {nar.ask: v}, corpus).left))
        bv = bv | {nar.ask: worst}
        nxt = talk_pick.narrow(KIND_IDS, bv, corpus)
        steps.append((nar.ask, worst, before, len(nxt.left)))
        nar = nxt
    return steps, nar


def test_on_a_big_kind_the_new_boxes_cut_what_the_seven_alone_could_not(bigfacts, capsys):
    corpus, _rows = bigfacts
    steps, end = _walk(corpus)
    with capsys.disabled():
        print("\nN6 worst-answer walk on 1,000 (seven boxes alone ended at 682 left):")
        for box, value, before, after in steps:
            print(f"   {box} = {value}: {before} -> {after}")
        print(f"   end: {len(end.left)} left, stop = {end.stop or 'none'}, {len(steps)} questions")
    assert len(end.left) <= 60 or end.stop == "small_cut"
    assert len(end.left) < 682


def test_a_caller_with_clear_answers_ends_at_ten_or_fewer(bigfacts, capsys):
    corpus, _rows = bigfacts
    # wants a loan, lives in a village, has a BPL card, is a woman, 41-79; the rest is answered by the picker's worst case
    clear = {"gives": "loan", "f_rural": "yes", "f_bpl_card": "yes", "gender": "female", "age": "41-79"}
    bv = _blank(category="pension") | clear
    first = talk_pick.narrow(KIND_IDS, bv, corpus)
    steps, end = _walk(corpus, clear)
    with capsys.disabled():
        print(f"\nN6 clear caller: {len(first.left)} fit on the five answers; after the picker's worst-answer questions "
              f"{len(end.left)} left ({len(steps)} more)")
    assert len(end.left) <= 10


def test_the_big_kind_works_with_the_marks_the_rank_and_the_blockers(bigfacts):
    corpus, _rows = bigfacts
    bv = _blank(category="pension", gives="loan", f_rural="yes", f_bpl_card="no")
    left = talk_pick.narrow(KIND_IDS, bv, corpus).left
    marks = talk_pick.marks(KIND_IDS, bv, corpus)
    assert set(left) == {s for s, m in marks.items() if m != talk_pick.DOES_NOT_FIT}
    assert all(marks[s] == talk_pick.mark(s, bv, corpus) for s in KIND_IDS[::7])
    ranked = talk_pick.rank(left, bv, corpus)
    assert set(ranked) == set(left)
    miss = next(s for s in KIND_IDS if marks[s] == talk_pick.DOES_NOT_FIT)
    assert talk_pick.blockers([miss], bv, corpus)[miss]


def test_the_speed_with_thirty_boxes_is_still_under_the_bar(bigfacts, tmp_path, monkeypatch, capsys):
    corpus, _rows = bigfacts
    monkeypatch.setitem(chunk_index._loaded_chunks, "big", Parts())
    monkeypatch.setattr(tunables, "TALK_CHUNKS", True)
    assert len(talk_pick.boxes_of(corpus)) == 22
    t, _idx = _talk(corpus, tmp_path)
    t.bv.update(category="pension", gender="female", age="41-79")
    t.just_tell = True
    times = []
    for _ in range(5):
        t._nar_memo = t._found_memo = t._piece_memo = None
        t0 = time.perf_counter()
        nar, cards = t._state(t._found())
        times.append((time.perf_counter() - t0) * 1000)
    asking = _talk(corpus, tmp_path)[0]
    asking.bv.update(category="pension")
    t0 = time.perf_counter()
    asking._narrow(KIND_IDS)
    ask_ms = (time.perf_counter() - t0) * 1000
    with capsys.disabled():
        print(f"\nN6 speed (22 boxes): turn pass on 1,000 of 5,000: median {statistics.median(times):.0f} ms; "
              f"first asking narrow {ask_ms:.0f} ms")
    assert statistics.median(times) < 400 and ask_ms < 1500


def test_the_prompt_grows_by_a_few_lines_for_five_new_boxes(bigfacts, capsys):
    corpus, _rows = bigfacts
    bv = _blank(category="pension")
    nar = talk_pick.narrow(KIND_IDS, bv, corpus)
    five = talk_pick.model_boxes(nar.left, bv, corpus, 5)
    base = {b: corpus.values(b) for b in SEVEN_BOXES}
    plain = prompt.build("en", "", {}, base, nar.ask, nar.order, [], "x", ask_first=True)[1]["content"]
    wide = prompt.build("en", "", {}, base | five, nar.ask, nar.order, [], "x", ask_first=True)[1]["content"]
    grew = (len(wide) - len(plain)) / 4
    with capsys.disabled():
        print(f"\nN6 prompt growth: {len(five)} boxes ({', '.join(five)}): +{len(wide) - len(plain)} chars, about {grew:.0f} tokens")
    assert len(five) == 5 and grew < 250


def test_a_turn_shows_the_model_the_new_boxes_and_takes_the_facts_it_sets(bigfacts, tmp_path):
    from tests.test_ask_first import Client
    corpus, _rows = bigfacts
    t, _ = _talk(corpus, tmp_path)
    t.heard.clear()
    t.model = SimpleNamespace(client=Client([{"action": "answer", "say": "Let me look at that.", "scheme": "",
                                              "facts": {"gives": "loan", "f_rural": "yes", "f_bpl_card": "maybe"}}]))
    words = "I need a pension, I want a loan and I live in a village"
    t.heard.append(words)
    t._decide(words)
    shown = t.model.client.calls[0].split("BOXES (allowed values):")[1].split("KNOWN ABOUT THE CALLER")[0]
    assert "- gives (what they want the scheme to give): cash_aid (say: Cash help)" in shown
    assert shown.count("\n- ") <= 6 + tunables.TALK_MODEL_BOXES                      # six of the seven (income_band holds nothing) and at most 5 new
    assert t.bv["gives"] == "loan" and t.bv["f_rural"] == "yes" and t.bv["f_bpl_card"] == UNASKED   # "maybe" is not a value
