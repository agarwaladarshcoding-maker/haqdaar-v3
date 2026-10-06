"""PLAN 9b, step N5: the picker decides how many questions are asked; what is left is ranked; a turn is fast
at 1,000 schemes of one kind in a set of 5,000. No model, no network. The big corpus is made here with the real
Corpus class (masks built the way the snapshot writer does it: a scheme with no condition on a box holds every value)."""
import random
import statistics
import time
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.log_schema import STOP_MAX_QUESTIONS
from haqdaar.contracts.types import SEVEN_BOXES, UNASKED, UNKNOWN, Ask, Stop
from haqdaar.data import chunk_index
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.engine import planner, talk_pick
from haqdaar.engine.filter import Filter
from haqdaar.engine.talk import _Talk
from haqdaar.prompts import talk as prompt
from tests.test_ask_first import Synth, _blank

VALUES = {
    "category": ("farming", "business_loans", "jobs_skills", "health", "housing", "pension", "education",
                 "women_children", "welfare_disability"),
    "state": ("MAHARASHTRA", "OTHER"),
    "gender": ("female", "male", "other"),
    "social_category": ("GEN", "OBC", "SC", "ST"),
    "age": ("0-13", "14-17", "18-35", "36-39", "40-40", "41-79", "80+"),
    "income_band": (),
    "occupation": ("farmer", "street_vendor", "apprentice", "entrepreneur", "artisan", "weaver", "worker"),
}
KIND = 1000
ALL = 5000


def make_corpus(n_all=ALL, n_kind=KIND, seed=7, extra=None, extra_values=None):
    """n_all schemes; the first n_kind are `pension`. About 40% of those hold no condition at all; the rest hold one
    or two across gender, age, work, social group and state.
    N6: `extra(rnd, i, row)` may add rows for more boxes (a box left out = any value) and `extra_values` names their
    closed lists; the seven boxes' rows are the same with or without them (the extra work has its own random stream)."""
    rnd = random.Random(seed)
    others = [c for c in VALUES["category"] if c != "pension"]
    rows = []
    for i in range(n_all):
        row = {"category": ("pension" if i < n_kind else others[i % len(others)],)}
        if not (i < n_kind and rnd.random() < 0.4):
            for box in rnd.sample(["gender", "age", "occupation", "social_category", "state"], rnd.choice([1, 2])):
                row[box] = tuple(rnd.sample(VALUES[box], rnd.randint(1, max(1, len(VALUES[box]) // 2))))
        rows.append(row)
    values = {b: VALUES[b] for b in SEVEN_BOXES}
    if extra is not None:
        extra_rnd = random.Random(seed + 1)
        for i, row in enumerate(rows):
            extra(extra_rnd, i, row)
        values.update(extra_values)
    masks = {(b, v): sum(1 << i for i, r in enumerate(rows) if b not in r or v in r[b])
             for b in values for v in values[b]}
    return Corpus("big", masks, values, tuple(f"s{i}" for i in range(n_all)),
                  tuple(len(r) - 1 for r in rows), {}, {}, {}, {}), rows


@pytest.fixture(scope="module")
def big():
    return make_corpus()


KIND_IDS = [f"s{i}" for i in range(KIND)]
ALL_IDS = tuple(f"s{i}" for i in range(ALL))


def _kind_bv(**known):
    return _blank(category="pension", **known)


# --- the question count is the picker's -----------------------------------------

def _pool(n, rows):
    """n schemes of one kind; `rows` are the first schemes' conditions, the rest hold none."""
    return Synth([{"category": ("pension",), **(rows[i] if i < len(rows) else {})} for i in range(n)])


def _ids(corpus):
    return list(corpus._scheme_ids)


def test_a_box_whose_worst_cut_is_small_but_whose_mean_cut_is_big_is_offered():
    # 100 schemes: 35 need a woman, 5 need a man, 60 hold no condition. Female leaves 95, male leaves 65:
    # the worst case cuts 5 (the bar is 10); the mean leaves 80, a cut of 20.
    corpus = _pool(100, [{"gender": ("female",)}] * 35 + [{"gender": ("male",)}] * 5)
    assert planner._worst_left("gender", tuple(range(100)), _blank(category="pension"), corpus) == 95
    got = talk_pick.narrow(_ids(corpus), _blank(category="pension"), corpus)
    assert got.ask == "gender" and got.stop == "" and talk_pick.min_cut(100) == 10
    assert [(o.box, o.left) for o in got.options] == [("gender", 95)]       # the option keeps its worst case


def test_a_box_under_both_bars_is_not_offered_and_the_asking_stops_with_a_reason():
    # one woman's scheme, one man's scheme, 98 with no condition: both answers leave 99
    corpus = _pool(100, [{"gender": ("female",)}, {"gender": ("male",)}])
    got = talk_pick.narrow(_ids(corpus), _blank(category="pension"), corpus)
    assert got.ask is None and got.options == () and got.stop == "small_cut" and len(got.left) == 100


def test_minimax_order_stands_when_a_box_passes_the_worst_case_bar():
    # age leaves at most 50 (cut 50); gender is the better MEAN box (its mean cut is bigger) but fails the worst bar
    rows = [{"age": ("18-35",)}] * 50 + [{"age": ("41-79",)}] * 50
    rows = [dict(r, **({"gender": ("female",)} if i < 45 else {"gender": ("male",)} if i < 47 else {}))
            for i, r in enumerate(rows)]
    corpus = _pool(100, rows)
    surv = tuple(range(100))
    bv = _blank(category="pension")
    assert 100 - planner._worst_left("age", surv, bv, corpus) >= talk_pick.min_cut(100)
    assert 100 - planner._worst_left("gender", surv, bv, corpus) < talk_pick.min_cut(100)
    got = talk_pick.narrow(_ids(corpus), bv, corpus)
    assert got.ask == "age" and [o.box for o in got.options] == ["age"]    # a box under the worst bar is not an option


def test_expected_left_is_the_mean_over_live_answers_and_never_counts_do_not_know():
    corpus = _pool(100, [{"gender": ("female",)}] * 35 + [{"gender": ("male",)}] * 5)
    assert planner._expected_left("gender", tuple(range(100)), _blank(category="pension"), corpus) == 80
    # "ANY" and "do not know" are not answers (they are never in a box's values here; the mean is over female and male only)
    assert planner._expected_left("gender", tuple(range(100)), _blank(category="pension"), corpus) != 100


def test_the_planner_cap_of_six_does_not_stop_the_talk_and_the_keys_path_keeps_it(big):
    corpus, _rows = big
    six = _kind_bv()
    six.update({"category": UNASKED, "state": UNKNOWN, "gender": UNKNOWN, "social_category": UNKNOWN,
                "age": UNKNOWN, "income_band": UNKNOWN, "occupation": UNKNOWN})   # six boxes answered, the kind still open
    assert planner._inferred_questions(six, corpus) == 6
    act = planner.Planner.next_action(six, corpus)                    # the keys path: default arguments
    assert isinstance(act, Stop) and act.reason == STOP_MAX_QUESTIONS
    assert isinstance(planner.next_action(six, corpus, max_questions=7), Ask)   # the talk's call lifts it
    got = talk_pick.narrow(list(ALL_IDS), six, corpus)
    assert got.ask == "category"


def test_the_guard_stops_the_talk_at_ask_max(big, tmp_path):
    corpus, _rows = big
    t, _idx = _talk(corpus, tmp_path)
    t.bv["category"] = "pension"
    assert tunables.TALK_ASK_MAX == 12
    assert t._state(KIND_IDS)[0].ask is not None and t.need_base == 0      # the need is named: the count starts
    t.asked = {"gender": 6, "age": 5}
    assert t._state(KIND_IDS)[0].ask is not None
    t.asked = {"gender": 6, "age": 6}
    nar = t._state(KIND_IDS)[0]
    assert nar.ask is None and nar.stop == "ask_max" and t._stop == "ask_max"


def test_switch_off_is_the_old_stop_rules(big, monkeypatch):
    corpus, _rows = big
    monkeypatch.setattr(tunables, "TALK_ASK_FIRST", False)
    got = talk_pick.narrow(KIND_IDS, _kind_bv(), corpus)
    best = planner.next_action(_kind_bv(), talk_pick.SubCorpus(corpus, range(KIND)), stop_survivors=2, tie_break="easy_first")
    assert got.ask == best.box and got.options == () and got.stop == ""
    six = _kind_bv(state=UNKNOWN, gender=UNKNOWN, social_category=UNKNOWN, age=UNKNOWN, income_band=UNKNOWN)
    six["occupation"] = "worker"
    assert talk_pick.narrow(KIND_IDS, six, corpus).ask is None      # the planner's own cap of 6 again


# --- rank ------------------------------------------------------------------------

def _rank_corpus():
    return Synth([{"category": ("pension",)},                                                       # s0 no condition
                  {"category": ("pension",)},                                                       # s1 no condition
                  {"category": ("pension",), "gender": ("female",)},                                # s2 a woman's
                  {"category": ("pension",), "gender": ("female",), "age": ("41-79",)},             # s3 a woman's, 41-79
                  {"category": ("pension",), "gender": ("male",), "age": ("18-35",)}])              # s4 not her


def test_a_scheme_that_asks_for_the_callers_facts_is_above_one_that_asks_for_nothing():
    corpus = _rank_corpus()
    bv = _blank(category="pension", gender="female", age="41-79")
    ids = ["s1", "s0", "s2", "s3", "s4"]
    left = talk_pick.narrow(ids, bv, corpus).left
    assert left == ("s1", "s0", "s2", "s3")                          # s4 does not fit; search order
    assert talk_pick.rank(left, bv, corpus) == ("s3", "s2", "s1", "s0")   # 2 facts, 1 fact, then search order for the equal pair
    assert talk_pick.rank(left, _blank(category="pension"), corpus) == left   # no facts known: nothing changes


def test_the_talk_ranks_when_the_asking_is_over_and_any_other_walks_the_same_order(big, tmp_path):
    corpus, _rows = big
    t, _idx = _talk(corpus, tmp_path)
    t.bv.update(category="pension", gender="female", age="41-79", occupation="worker", social_category="SC",
                state="MAHARASHTRA")
    t.just_tell = True
    t._others = [sid for sid, m in talk_pick.marks(KIND_IDS, t.bv, corpus).items() if m != talk_pick.DOES_NOT_FIT]   # as _found leaves it
    nar, _cards = t._state(KIND_IDS)
    left = nar.left
    assert len(left) > 2 and t._ranked is True and list(t._rank_pos) == list(left)
    assert list(left) == list(talk_pick.rank(talk_pick.narrow(KIND_IDS, t.bv, corpus).left, t.bv, corpus))
    assert t._others == list(left)                                     # "any other?" gives the schemes in this order
    facts = [b for b in SEVEN_BOXES if b != "category" and t.bv[b] not in (UNASKED, UNKNOWN)]
    cnt = [sum(talk_pick._ix_map(corpus)[s] >= 0 and bool(_specific(corpus, talk_pick._ix_map(corpus)[s], b)) for b in facts)
           for s in left]
    assert cnt == sorted(cnt, reverse=True)                            # the most facts first
    t.focus = left[-1]                                                 # a scheme in talk: a side question, no ranking line
    t._state(KIND_IDS)
    assert t._ranked is False


def _specific(corpus, ix, box):
    return any(not corpus.mask(box, v) >> ix & 1 for v in corpus.values(box))


def test_the_prompt_holds_the_count_once_and_the_new_line_only_when_ranked():
    msgs = prompt.build("en", "", {}, {}, None, [], [("s3", "fits", "[s3]\nname")], "x", fit=14, ask_first=True, ranked=True)
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert prompt.RANK_RULE.strip() in system
    assert user.count("14 schemes fit") == 1 and "12 more fit" in user and "13 if you tell only one" in user
    plain = prompt.build("en", "", {}, {}, None, [], [("s3", "fits", "[s3]\nname")], "x", ask_first=True)
    assert prompt.RANK_RULE.strip() not in plain[0]["content"] and "schemes fit" not in plain[1]["content"]
    gated = prompt.build("en", "", {}, {}, "age", [], [], "x", fit=14, ask_first=True)
    assert "Name none of them" in gated[1]["content"] and prompt.RANK_RULE.strip() not in gated[0]["content"]
    off = prompt.build("en", "", {}, {}, None, [], [], "x", ranked=True)          # switch off: the system text is the old one
    assert prompt.RANK_RULE.strip() not in off[0]["content"]


# --- speed -----------------------------------------------------------------------

class Idx:
    ids = ALL_IDS
    snapshot_id = "big"

    def __init__(self):
        self.searches = 0

    def search(self, text, k=10):
        self.searches += 1
        return [SimpleNamespace(scheme_id=s, by="vec") for s in self.ids[:k]]


class Parts:
    scheme_ids = ALL_IDS
    chunks = [None] * 5

    def search(self, query, *, k=5, fits=None, max_chunks_per_scheme=2):
        return [chunk_index.ChunkHit(s, "summary", "text " + s, 1.0) for s in self.scheme_ids[:k]]


def _talk(corpus, tmp_path):
    idx = Idx()
    log = Log.open("scale", "big", logs_dir=str(tmp_path))
    t = _Talk(SimpleNamespace(), None, corpus, log, "en", idx)
    t.stage = {}
    t.heard.append("pension")
    return t, idx


def _one_pass(t):
    t._nar_memo = t._found_memo = t._piece_memo = None
    ids = t._found()
    return t._state(ids)


def test_a_turn_with_1000_schemes_of_one_kind_in_5000_is_fast(big, tmp_path, monkeypatch, capsys):
    corpus, _rows = big
    monkeypatch.setitem(chunk_index._loaded_chunks, "big", Parts())
    monkeypatch.setattr(tunables, "TALK_CHUNKS", True)
    t, _idx = _talk(corpus, tmp_path)
    t.bv.update(category="pension", gender="female", age="41-79")
    t.just_tell = True                      # the gate is open: the parts are searched, 5,000 marks are made
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        nar, cards = _one_pass(t)
        times.append((time.perf_counter() - t0) * 1000)
    assert len(t._found()) >= KIND and len(nar.left) > 100 and cards and t._ranked
    median = statistics.median(times)
    with capsys.disabled():
        print(f"\nN5 speed: one turn pass (found + narrow + parts, 5,000 marks) on 1,000 of 5,000: median {median:.0f} ms "
              f"(runs: {', '.join(f'{x:.0f}' for x in times)})")
    assert median < 400


def test_nothing_changed_means_no_second_search_and_no_second_narrow(big, tmp_path, monkeypatch):
    corpus, _rows = big
    t, idx = _talk(corpus, tmp_path)
    t.bv["category"] = "pension"
    calls = []
    real = talk_pick.narrow
    monkeypatch.setattr(talk_pick, "narrow", lambda *a: calls.append(1) or real(*a))
    ids = t._found()
    searches = idx.searches
    nar = t._state(ids)[0]
    assert t._found() == ids and t._state(ids)[0] is nar
    assert idx.searches == searches and len(calls) == 1
    t.bv["gender"] = "female"                                          # a fact changed: both work again
    t._state(t._found())
    assert idx.searches > searches and len(calls) == 2


def test_the_speed_work_gives_the_same_answers(big):
    corpus, _rows = big
    bv = _kind_bv(gender="female", age="41-79")
    assert talk_pick._ix(corpus, "s4321") == 4321 and talk_pick._ix(corpus, "nope") == -1
    sample = [f"s{i}" for i in range(0, ALL, 7)] + ["nope"]
    assert talk_pick.marks(sample, bv, corpus) == {s: talk_pick.mark(s, bv, corpus) for s in sample}
    assert talk_pick.marks(sample, _blank(), corpus) == {s: talk_pick.mark(s, _blank(), corpus) for s in sample}
    sub = talk_pick.SubCorpus(corpus, range(0, 3000, 3))
    assert sub.mask("gender", "female") == sub.mask("gender", "female")            # kept: the same number again
    # Filter.survivors against the scheme-by-scheme test it replaced
    for vec in (_blank(), bv, _kind_bv(occupation="worker", social_category="SC")):
        mask = None
        for _b, _v, m in Filter.turn_masks(vec, corpus):
            mask = m if mask is None else mask & m
        old = tuple(i for i in range(ALL) if mask is None or mask & 2 ** i)
        assert Filter.survivors(vec, corpus) == old
