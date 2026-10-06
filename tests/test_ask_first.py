"""PLAN 9, step N1: ask before listing. The picker's best boxes are the model's options, the questions
one need may take follow the size of the list, and no scheme is listed while the list is long.
Fake model, fake audio, no network. Lists longer than today's data are built from a small synthetic corpus."""
import re
import time
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import SEVEN_BOXES, UNASKED
from haqdaar.data import chunk_index, log_text, scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.engine import planner, talk_pick
from haqdaar.engine.talk import _Talk
from haqdaar.prompts import talk as prompt
from tests.test_talk import Client


def _blank(**known):
    return {b: UNASKED for b in SEVEN_BOXES} | known


class Synth:
    """A corpus of schemes made from rows: {box: (the values the scheme takes)}. A box left out = any value."""

    snapshot_id = "synth"

    def __init__(self, rows):
        self._rows = rows
        self._scheme_ids = tuple(f"s{n}" for n in range(len(rows)))

    def values(self, box):
        return tuple(sorted({v for row in self._rows for v in row.get(box, ())}))

    def mask(self, box, value):
        return sum(1 << n for n, row in enumerate(self._rows) if box not in row or value in row[box])

    def specificity(self, n):
        return len(self._rows[n]) if 0 <= n < len(self._rows) else 0

    def scheme_id(self, n):
        return self._scheme_ids[n] if 0 <= n < len(self._scheme_ids) else ""


def _long_list():
    """16 schemes of one kind. What each box leaves after its worst answer:
    age 8, occupation 12, income_band 13, gender 14. State and category split nothing."""
    rows = []
    for n in range(16):
        row = {"category": ("farming",)}
        row["age"] = ("18-35",) if n < 8 else ("36-60",)
        row["occupation"] = ("farmer",) if n < 8 else ("labourer",) if n < 12 else ()
        if n < 3:
            row["income_band"] = ("low",)
        elif n < 8:
            row["income_band"] = ("mid",)
        if n < 2:
            row["gender"] = ("female",)
        elif n < 4:
            row["gender"] = ("male",)
        if n == 0:
            row["state"] = ("KA",)
        rows.append({k: v for k, v in row.items() if v})
    return Synth(rows)


# --- options -------------------------------------------------------------------

def test_options_are_the_best_three_boxes_best_first_with_the_most_left():
    corpus = _long_list()
    got = talk_pick.narrow(list(corpus._scheme_ids), _blank(), corpus)
    assert len(got.left) == 16
    assert [(o.box, o.left) for o in got.options] == [("age", 8), ("occupation", 12), ("income_band", 13)]
    assert got.ask == got.options[0].box == "age"          # `ask` stays the best one
    sub = talk_pick.SubCorpus(corpus, range(16))
    surv = tuple(range(16))
    assert [planner._worst_left(o.box, surv, _blank(), sub) for o in got.options] == [8, 12, 13]


def test_options_leave_out_a_box_that_splits_nothing_and_are_fewer_when_few_split():
    corpus = _long_list()
    got = talk_pick.narrow(list(corpus._scheme_ids), _blank(age="18-35"), corpus)
    boxes = [o.box for o in got.options]
    assert "age" not in boxes and "state" not in boxes and "category" not in boxes   # answered / splits nothing
    assert got.options[0].box == got.ask
    one = talk_pick.narrow(list(corpus._scheme_ids), _blank(age="18-35", occupation="farmer", income_band="low", gender="female"),
                           corpus)
    assert len(one.left) == 2 and one.options == () and one.ask is None             # 2 left: nothing to ask


def test_options_on_the_real_corpus_and_none_when_the_switch_is_off(monkeypatch):
    corpus = Corpus.load("CURRENT")
    ids = [corpus.scheme_id(i) for i in range(17)]
    got = talk_pick.narrow(ids, _blank(), corpus)
    assert 1 <= len(got.options) <= 3 and got.options[0].box == got.ask
    assert all(o.left <= len(got.left) for o in got.options)
    monkeypatch.setattr(tunables, "TALK_ASK_FIRST", False)
    off = talk_pick.narrow(ids, _blank(), corpus)
    assert off.options == () and off.ask == got.ask and off.order == got.order and off.left == got.left


def test_the_keys_planner_is_untouched_by_the_score_split():
    corpus = _long_list()
    surv = tuple(range(16))
    # elimination / expected turns, as before the split of the worst answer out of the score
    assert planner._minimax_score("age", surv, _blank(), corpus) == (16 - 8) / planner._expected_turns("age", corpus)
    assert planner._minimax_score("state", surv, _blank(), corpus) == 0.0


# --- the worth-it rule (N5; the log2 budget of N1 is gone) -----------------------

@pytest.mark.parametrize("n,cut", [(1, 1), (2, 1), (3, 1), (10, 1), (11, 2), (14, 2), (30, 3), (94, 10), (1000, 100)])
def test_a_question_must_cut_a_tenth_of_the_list_and_one_scheme_at_least(n, cut):
    assert talk_pick.min_cut(n) == cut


def test_the_cut_follows_the_tunable(monkeypatch):
    monkeypatch.setattr(tunables, "TALK_MIN_CUT", 0.5)
    assert talk_pick.min_cut(94) == 47


def test_the_best_box_is_asked_while_it_cuts_enough_and_two_left_is_no_stop_reason():
    corpus = _long_list()
    got = talk_pick.narrow(list(corpus._scheme_ids), _blank(), corpus)
    assert got.ask == "age" and got.stop == ""                 # age leaves at most 8 of 16: a cut of 8, the bar is 2
    two = talk_pick.narrow(list(corpus._scheme_ids)[:2], _blank(), corpus)
    assert two.ask is None and two.stop == ""                  # 2 left: nothing to ask, no reason to give


# --- the talk ------------------------------------------------------------------

@pytest.fixture(scope="module")
def corpus():
    return Corpus.load("CURRENT")


@pytest.fixture(scope="module")
def idx():
    return scheme_index.SchemeIndex.load("CURRENT", embed=lambda texts: 1 / 0)


def _talk(corpus, tmp_path, idx, name="askfirst"):
    log = Log.open(name, corpus.snapshot_id, logs_dir=str(tmp_path))
    t = _Talk(SimpleNamespace(), None, corpus, log, "en", idx)
    t.stage = {}
    return t


def _peek(t, words):
    """The picker's state for these words, found the way a turn finds it (the search's top 10)."""
    t.heard.append(words)
    nar, _cards = t._state(t._found())
    t.heard.pop()
    return nar


def _turn(t, words, replies):
    """One _decide turn on a fake model; the model's prompts are in the returned client's calls."""
    client = Client(replies)
    t.model = SimpleNamespace(client=client)
    t.heard.append(words)
    return t._decide(words), client


ASK = {"action": "ask", "say": "What work do you do?", "ask_box": "occupation", "facts": {}, "scheme": ""}
LIST = {"action": "show_scheme", "say": "PM Kisan gives money.", "scheme": "pm-kisan", "facts": {}, "parts": []}
FARM = "I need help with farming"      # farming: 4 schemes fit, the picker asks work


def _schemes_block(content):
    return content.split("SCHEMES (", 1)[1].split("SCHEME IN TALK:", 1)[0]


def test_a_long_list_is_not_listed_in_the_prompt_only_how_many_fit(corpus, tmp_path, idx):
    t = _talk(corpus, tmp_path, idx)
    (action, _say), client = _turn(t, FARM, [ASK])
    prompt_text = client.calls[0]
    block = _schemes_block(prompt_text)
    assert action == "ask"
    assert "[pm-kisan]" not in block and "mark: " not in block and "how_to_apply" not in prompt_text
    assert "4 schemes fit" in block
    assert "NEXT QUESTION: occupation" in prompt_text and "OPTIONS" in prompt_text
    assert "- occupation: their work; at most 4 left" in prompt_text


def test_show_scheme_while_the_list_is_long_is_sent_back_once_then_the_question_is_said(corpus, tmp_path, idx):
    t = _talk(corpus, tmp_path, idx)
    (action, say), client = _turn(t, FARM, [LIST, LIST])
    assert (action, say) == ("ask", prompt.QUESTION["occupation"]["en"])
    assert len(client.calls) == 2 and "too many to list" in client.calls[1]
    assert t.asked == {"occupation": 1} and t.last_asked == "occupation"
    # sent back once: the second try may be the question the model words itself
    t2 = _talk(corpus, tmp_path, idx, "askfirst2")
    (action, say), client = _turn(t2, FARM, [LIST, ASK])
    assert (action, say) == ("ask", ASK["say"]) and len(client.calls) == 2


def test_a_side_question_is_still_answered_while_the_list_is_long(corpus, tmp_path, idx):
    t = _talk(corpus, tmp_path, idx)
    _turn(t, FARM, [ASK])
    why = {"action": "answer", "say": "Work tells me which schemes are for you.", "scheme": "", "facts": {}}
    (action, say), client = _turn(t, "why do you ask?", [why])
    assert (action, say) == ("answer", why["say"]) and len(client.calls) == 1
    assert "[pm-kisan]" not in _schemes_block(client.calls[0])        # and still no listing
    # a side question on the scheme in talk: the scheme's text is in the prompt
    t.focus = "pm-kisan"
    (action, _say), client = _turn(t, "which papers?", [{"action": "answer", "say": "Bring your Aadhaar card.",
                                                          "scheme": "pm-kisan", "facts": {}}])
    assert action == "answer" and "[pm-kisan]" in _schemes_block(client.calls[0])
    assert "NEXT QUESTION: none" in client.calls[0]


def test_just_tell_me_opens_the_gate(corpus, tmp_path, idx):
    t = _talk(corpus, tmp_path, idx)
    _turn(t, FARM, [ASK])
    (action, _say), client = _turn(t, "just tell me", [LIST])
    assert action == "show_scheme" and len(client.calls) == 1
    assert "NEXT QUESTION: none" in client.calls[0] and client.calls[0].count("mark: ") == 2


def test_a_named_scheme_opens_the_gate(corpus, tmp_path, idx):
    t = _talk(corpus, tmp_path, idx)
    (action, _say), client = _turn(t, "tell me about pm kisan", [
        {"action": "answer", "say": "It helps farmers.", "scheme": "pm-kisan", "facts": {}}])
    assert action == "answer" and "NEXT QUESTION: none" in client.calls[0]
    assert "[pm-kisan]" in _schemes_block(client.calls[0])


def test_the_guard_runs_out_and_the_gate_opens_then_a_new_need_starts_a_new_count(corpus, tmp_path, idx, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ASK_MAX", 3)        # the guard only; the picker's own stop is the worth-it rule
    t = _talk(corpus, tmp_path, idx)
    t.bv["category"] = "farming"
    assert t._state(list(idx.ids))[0].ask == "occupation" and t.need_base == 0      # the need is named: the count starts
    t.asked = {"occupation": 1, "age": 1}
    assert t._state(list(idx.ids))[0].ask is not None
    t.asked = {"occupation": 1, "age": 1, "gender": 1}
    nar, cards = t._state(list(idx.ids))
    assert nar.ask is None and nar.options == () and nar.stop == "ask_max" and t._gate is False and cards   # asked out: it lists
    (action, _say), client = _turn(t, "I want a pension", [{"action": "ask", "say": "How old are you?",
                                                           "ask_box": "age", "facts": {}, "scheme": ""}])
    assert "NEXT QUESTION: age" in client.calls[0] and t.need_base == 3        # a new need: the count starts again


def test_no_question_for_two_or_fewer(corpus, tmp_path, idx):
    t = _talk(corpus, tmp_path, idx)
    t.bv["category"] = "housing"                     # one scheme fits
    nar, _cards = t._state(list(idx.ids))
    assert nar.ask is None and nar.stop == "" and t.need_base == 0


class Parts:
    """A stand-in for the loaded parts index."""

    def __init__(self, ids, answer):
        self.scheme_ids, self.chunks, self._answer = tuple(ids), [None] * 5, answer
        self.fits = []

    def search(self, query, *, k=5, fits=None, max_chunks_per_scheme=2):
        self.fits.append(fits)
        return self._answer(query)


def _hit(sid, text):
    return chunk_index.ChunkHit(sid, "summary", text, 1.0)


def test_parts_come_only_from_the_narrowed_list_and_the_scheme_in_talk(corpus, tmp_path, idx, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_CHUNKS", True)
    ranked = [h.scheme_id for h in idx.search("something", len(idx.ids))]
    inside, outside = ranked[0], ranked[-1]          # the search's first is in the top 10, its last is not
    parts = Parts(idx.ids, lambda q: [_hit(outside, "OUTSIDE-TEXT"), _hit(inside, "INSIDE-TEXT")])
    monkeypatch.setitem(chunk_index._loaded_chunks, corpus.snapshot_id, parts)
    t = _talk(corpus, tmp_path, idx)
    t.just_tell = True                               # the gate is open: parts are given
    (_a, _s), client = _turn(t, "I need something", [LIST])
    block = _schemes_block(client.calls[0])
    assert "INSIDE-TEXT" in block and "OUTSIDE-TEXT" not in block
    assert parts.fits[0][outside] == talk_pick.DOES_NOT_FIT      # the search is told to push it down
    # the scheme in talk is kept even when it is not in the list
    t.focus = outside
    (_a, _s), client = _turn(t, "I need something", [LIST])
    assert "OUTSIDE-TEXT" in _schemes_block(client.calls[0])
    # switch off: the old way, whatever the search found
    monkeypatch.setattr(tunables, "TALK_ASK_FIRST", False)
    t2 = _talk(corpus, tmp_path, idx, "askfirst-off")
    t2.just_tell = True
    (_a, _s), client = _turn(t2, "I need something", [LIST])
    assert "OUTSIDE-TEXT" in _schemes_block(client.calls[0])


def test_parts_while_the_gate_holds_are_the_scheme_in_talk_only(corpus, tmp_path, idx, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_CHUNKS", True)
    parts = Parts(idx.ids, lambda q: [_hit("kcc", "KCC-TEXT"), _hit("pm-kisan", "KISAN-TEXT")])
    monkeypatch.setitem(chunk_index._loaded_chunks, corpus.snapshot_id, parts)
    t = _talk(corpus, tmp_path, idx)
    t.focus = "pm-kisan"
    (_a, _s), client = _turn(t, FARM, [ASK])
    block = _schemes_block(client.calls[0])
    assert "KISAN-TEXT" in block and "KCC-TEXT" not in block and "4 schemes fit" in block


def _three_named(rule_say):
    return {"action": "answer", "say": rule_say, "scheme": "", "facts": {}}


THREE = "PM Kisan, Kisan Credit Card and crop insurance are all there."
TWO = "PM Kisan and Kisan Credit Card are both there."


def test_a_reply_naming_three_schemes_is_sent_back_once(corpus, tmp_path, idx):
    t = _talk(corpus, tmp_path, idx)
    t.just_tell = True
    (action, say), client = _turn(t, FARM, [_three_named(THREE), _three_named(TWO)])
    assert (action, say) == ("answer", TWO) and len(client.calls) == 2
    assert "many_schemes" in client.calls[1] and "at most 2 schemes" in client.calls[1]
    assert [r["rule"] for r in log_text.read_rows(t.log.path) if r.get("ev") == "blocked"] == ["many_schemes"]


def test_a_second_reply_naming_three_schemes_gets_the_not_sure_line_like_the_other_checks(corpus, tmp_path, idx):
    t = _talk(corpus, tmp_path, idx)
    t.just_tell = True
    (action, say), client = _turn(t, FARM, [_three_named(THREE), _three_named(THREE)])
    assert (action, say) == ("answer", prompt.NOT_SURE["en"]) and len(client.calls) == 2


def test_two_names_in_a_reply_pass_and_the_check_is_off_with_the_switch(corpus, tmp_path, idx, monkeypatch):
    t = _talk(corpus, tmp_path, idx)
    t.just_tell = True
    (action, say), client = _turn(t, FARM, [_three_named(TWO)])
    assert (action, say) == ("answer", TWO) and len(client.calls) == 1
    monkeypatch.setattr(tunables, "TALK_ASK_FIRST", False)
    t2 = _talk(corpus, tmp_path, idx, "askfirst-off")
    t2.just_tell = True
    (action, say), client = _turn(t2, FARM, [_three_named(THREE)])
    assert (action, say) == ("answer", THREE) and len(client.calls) == 1


def test_a_box_from_the_options_that_is_not_the_best_one_is_a_right_box(corpus, tmp_path, idx, monkeypatch):
    monkeypatch.setattr("haqdaar.engine.talk.SEARCH_K", 17)     # the picker works on all 17: more than one box splits
    t = _talk(corpus, tmp_path, idx)
    nar = _peek(t, "hello")                           # no need named: the options hold more than one box
    assert len(nar.options) >= 2
    other = nar.options[1].box
    reply = {"action": "ask", "say": "Tell me.", "ask_box": other, "facts": {}, "scheme": ""}
    (action, say), client = _turn(t, "hello", [reply])
    assert (action, say) == ("ask", "Tell me.") and len(client.calls) == 1 and t.last_asked == other
    reply["ask_box"] = "state"                        # not an option: sent back
    t2 = _talk(corpus, tmp_path, idx, "askfirst2")
    assert "state" not in {o.box for o in _peek(t2, "hello").options}
    (action, say), client = _turn(t2, "hello", [reply, reply])
    assert len(client.calls) == 2 and "Ask about one of:" in client.calls[1]


def test_a_dont_know_to_an_option_that_was_not_the_best_sets_that_box_unknown(corpus, tmp_path, idx, monkeypatch):
    monkeypatch.setattr("haqdaar.engine.talk.SEARCH_K", 17)
    t = _talk(corpus, tmp_path, idx)
    other = _peek(t, "I do not know").options[1].box
    t.last_asked = other
    t.asked[other] = 1
    (_a, _s), _client = _turn(t, "I do not know", [{"action": "answer", "say": "That is fine.", "scheme": "",
                                                   "facts": {}}])
    assert t.bv[other] == "UNKNOWN"


def test_switch_off_is_the_talk_as_it_was(corpus, tmp_path, idx, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ASK_FIRST", False)
    t = _talk(corpus, tmp_path, idx)
    (action, say), client = _turn(t, FARM, [LIST])
    assert (action, say) == ("show_scheme", LIST["say"]) and len(client.calls) == 1   # listed at once
    assert "[pm-kisan]" in _schemes_block(client.calls[0]) and "OPTIONS" not in client.calls[0]
    assert "fit what we know" not in client.calls[0]
    # the old fixed 3 questions
    t.asked = {"occupation": 1, "age": 1, "gender": 1}
    assert t._state(list(idx.ids))[0].ask is None
    system = prompt.build("en", "", {}, {}, None, [], [], "x")[0]["content"]
    assert "ONLY the box named in NEXT QUESTION" in system and "or when the caller asks which schemes there are" in system


def test_the_prompt_lines_that_clashed_are_brought_in_line_with_the_switch_on():
    system_on = prompt.build("en", "", {}, {}, None, [], [], "x", ask_first=True)[0]["content"]
    for was, _now in prompt.ASK_FIRST_EDITS:
        assert was in prompt.SYSTEM                   # the edit still finds its line
    assert "or when the caller asks which schemes there are" not in system_on
    assert 'The need is clear and NEXT QUESTION is "none" -> "show_scheme"' in system_on
    assert "say how many there are, then ask" in system_on
    # the same, with the switch off, is the old text
    assert prompt.build("en", "", {}, {}, None, [], [], "x")[0]["content"] == prompt.build(
        "en", "", {}, {}, None, [], [], "x", ask_first=False)[0]["content"]
