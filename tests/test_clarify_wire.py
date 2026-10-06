"""Step 1.3b, part 2: what is written but never called, now wired.

_decide-level cases pin each wire; the live loop (Engine + fake model +
real name-only index) proves the routing end to end, including every "by
code" case of fixtures/talk_human.json on its first turn.
"""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import SEVEN_BOXES, UNASKED, Speech
from haqdaar.data import scheme_index
from haqdaar.data.corpus import Corpus
from haqdaar.engine.filter import Filter
from haqdaar.data.log import Log
from haqdaar.engine import talk_kind
from haqdaar.engine.call import Engine
from haqdaar.engine.talk import _Talk
from tests.test_talk import Audio, Client
from tests.test_talk_human_code import CODE_IDS


@pytest.fixture(scope="module")
def corpus():
    return Corpus.load("CURRENT")


@pytest.fixture(scope="module")
def idx():
    return scheme_index.SchemeIndex.load("CURRENT", embed=lambda texts: 1 / 0)


def _talk(corpus, tmp_path, name, index, lang="en"):
    log = Log.open(name, corpus.snapshot_id, logs_dir=str(tmp_path))
    t = _Talk(SimpleNamespace(), None, corpus, log, lang, index)
    t.stage = {}
    return t


def _prime(t, corpus, words):
    """The word-spot half of a turn, so a peeked question matches _decide's."""
    from haqdaar.engine import talk_words
    from haqdaar.engine.talk import _take_facts
    _take_facts(talk_words.spot(words, corpus), t.bv, corpus, t.log, t.turn_n)


def _ask(t, corpus, words, say, **facts):
    """One _decide turn asking the picker's box."""
    _prime(t, corpus, words)
    nar, _cards = t._state(t._found())
    assert nar.ask is not None
    t.model = SimpleNamespace(client=Client([{"action": "ask", "say": say, "ask_box": nar.ask,
                       "facts": dict(facts), "scheme": ""}]))
    return t._decide(words), nar.ask


def test_situation_asks_first(corpus, tmp_path, idx):
    """P2.1: a situation clarifies first; the question counts."""
    t = _talk(corpus, tmp_path, "wire-situation", idx)
    t.heard = ["मेरी फसल खराब हो गई"]
    t.model = SimpleNamespace(client=Client([{"action": "ask", "say": "What work do you do?",
                       "ask_box": "occupation", "facts": {}, "scheme": ""}]))
    action, _say = t._decide("मेरी फसल खराब हो गई")
    assert (action, t.last_asked, t.asked) == ("ask", "occupation", {"occupation": 1})


def test_held_scheme_answers_first(corpus, tmp_path, idx):
    """P2.1: a scheme we hold is answered first; nothing is asked."""
    t = _talk(corpus, tmp_path, "wire-held", idx)
    t.heard = ["पीएम किसान"]
    t.model = SimpleNamespace(client=Client([{"action": "answer", "say": "It gives money.",
                       "scheme": "pm-kisan", "facts": {}}]))
    action, _say = t._decide("पीएम किसान")
    assert action == "answer" and t.focus == "pm-kisan" and t.asked == {}


def test_not_held_scheme_gets_the_fixed_reply(corpus, tmp_path, idx):
    """P2.2: "I do not have that one yet" + the kinds held. No model call."""
    t = _talk(corpus, tmp_path, "wire-notheld", idx)
    client = Client([])
    t.model = client
    t.heard = ["आयुष्मान कार्ड मिलेगा क्या"]
    action, say = t._decide("आयुष्मान कार्ड मिलेगा क्या")
    assert action == "answer" and client.calls == []
    assert "do not have that one yet" in say and "Farming" in say
    assert "?" not in say
    t = _talk(corpus, tmp_path, "wire-notheld-hi", idx, lang="hi")
    t.model = SimpleNamespace(client=Client([]))
    t.heard = ["आयुष्मान कार्ड मिलेगा क्या"]
    _action, say = t._decide("आयुष्मान कार्ड मिलेगा क्या")
    assert "यह योजना मेरे पास अभी नहीं है।" in say


def test_two_needs_first_taken_other_kept(corpus, tmp_path, idx):
    """P2.3: the first named need is taken; "you also asked about a house"."""
    t = _talk(corpus, tmp_path, "wire-two", idx)
    t.heard = ["खेती और घर दोनों के लिए कुछ है क्या"]
    t.model = SimpleNamespace(client=Client([{"action": "show_scheme", "say": "Two schemes for you.", "scheme": ""}]))
    action, say = t._decide("खेती और घर दोनों के लिए कुछ है क्या")
    assert action == "show_scheme"
    assert t.bv["category"] == "farming"
    assert "also asked about" in say and "A house" in say
    assert t.more_needs == []  # come back to it once: said, then dropped


def test_new_need_drops_the_scheme_in_talk(corpus, tmp_path, idx):
    """P2.4: new words, new need; the scheme in talk is dropped."""
    t = _talk(corpus, tmp_path, "wire-newneed", idx)
    t.heard = ["विधवा पेंशन"]
    t.model = SimpleNamespace(client=Client([{"action": "answer", "say": "It gives money.", "scheme": "ignwps"}]))
    t._decide("विधवा पेंशन")
    assert t.focus == "ignwps" and t.bv["category"] == "pension"
    t.heard.append("मुझे लोन चाहिए")
    t.model = SimpleNamespace(client=Client([{"action": "show_scheme", "say": "Two schemes for you.", "scheme": ""}]))
    t._decide("मुझे लोन चाहिए")
    assert t.focus == "" and t.bv["category"] == "business_loans"


def test_corrected_fact_rebuilds_from_the_need(corpus, tmp_path, idx):
    """P2.5: "not 26, 62" builds the list again from all schemes of the need."""
    bands = corpus.values("age")
    t = _talk(corpus, tmp_path, "wire-fix", idx)
    t.bv.update({"category": "pension", "age": bands[2]})
    t.heard = ["hmm"]
    t.model = SimpleNamespace(client=Client([{"action": "answer", "say": "It gives money.",
                       "facts": {"age": bands[4]}, "scheme": ""}]))
    t._decide("hmm")
    assert t.bv["age"] == bands[4] and t.left
    pensions = {corpus.scheme_id(i) for i in Filter.survivors({"category": "pension"}, corpus)}
    in_left = [s for s in t.left if s in pensions]
    assert in_left and in_left == [s for s in idx.ids if s in pensions and s in set(t.left)]


def test_new_person_clears_age_gender_work(corpus, tmp_path, idx):
    """P2.6: "for my mother" clears age, gender and work; the rest stays."""
    t = _talk(corpus, tmp_path, "wire-person", idx)
    bands = corpus.values("age")
    t.bv.update({"category": "pension", "age": bands[2], "gender": "female",
                 "occupation": "worker", "state": "MAHARASHTRA", "social_category": "GEN"})
    t.heard = ["for my mother"]
    t.model = SimpleNamespace(client=Client([{"action": "not_for_me"}]))
    t._decide("for my mother")
    assert t.bv["age"] == UNASKED and t.bv["occupation"] == UNASKED
    assert t.bv["gender"] == "female" and t.bv["category"] == "pension"
    assert t.bv["state"] == "MAHARASHTRA" and t.bv["social_category"] == "GEN"


def test_will_result_brings_one_question_back(corpus, tmp_path, idx):
    """P3.4: after "just tell me", "will I get it?" lets one question back."""
    t = _talk(corpus, tmp_path, "wire-will", idx)
    t.just_tell = True
    t.heard = ["मुझे पेंशन मिलेगी क्या?"]
    t._will_now = True  # _decide recomputes the same from just_tell + will-words
    (action, _say), ask = _ask(t, corpus, "मुझे पेंशन मिलेगी क्या?", "How old are you?")
    assert ask == "age" and action == "ask" and t.asked == {"age": 1} and t._will_used
    t.heard.append("और बताओ")
    t.model = SimpleNamespace(client=Client(
        [{"action": "show_scheme", "say": "Two schemes for you.", "scheme": ""}]))
    action2, _say2 = t._decide("और बताओ")
    assert action2 == "show_scheme"
    nar, _cards = t._state(t._found())
    assert nar.ask is None


# --- the live loop ------------------------------------------------------------


@pytest.fixture()
def livecall(corpus, tmp_path, monkeypatch, idx):
    from haqdaar.engine.call import Engine
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": idx)
    from haqdaar.data import log_text
    n = [0]

    def go(inputs, replies):
        n[0] += 1
        audio, client = Audio(inputs), Client(list(replies))
        log = Log.open(f"wire_live_{n[0]}", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
        rows = log_text.read_rows(log.path)
        assert not [r for r in rows if r.get("invalid")]
        return audio, client, rows

    return go


def _peek_ask(corpus, tmp_path, idx, said):
    t = _talk(corpus, tmp_path, "wire-peek", idx)
    t.heard = [said]
    _prime(t, corpus, said)
    return t._state(t._found())[0].ask


def test_live_held_scheme_asks_nothing(livecall):
    audio, client, _rows = livecall(
        [Speech("पीएम किसान")],
        [{"action": "answer", "say": "It gives money.", "scheme": "pm-kisan", "facts": {}}])
    assert "NEXT QUESTION: none" in client.calls[0]
    assert audio.answers == ["It gives money."]


def test_live_not_held_needs_no_model(livecall):
    audio, client, _rows = livecall([Speech("आयुष्मान कार्ड मिलेगा क्या")], [])
    assert client.calls == []
    assert "do not have that one yet" in audio.answers[0]


def test_live_situation_asks_first(corpus, tmp_path, idx, livecall):
    said = "मेरी फसल खराब हो गई"
    ask = _peek_ask(corpus, tmp_path, idx, said)
    assert ask == "occupation"
    audio, client, _rows = livecall(
        [Speech(said)],
        [{"action": "ask", "say": "What work do you do?", "ask_box": ask, "facts": {}}])
    assert f"NEXT QUESTION: {ask}" in client.calls[0]
    assert audio.answers == ["What work do you do?"]


def test_live_just_tell_on_turn_two(livecall):
    audio, client, _rows = livecall(
        [Speech("I need some scheme"), Speech("just tell me")],
        [{"action": "show_scheme", "say": "Two schemes for you.", "scheme": ""},
         {"action": "show_scheme", "say": "Two schemes for you.", "scheme": ""}])
    assert "NEXT QUESTION: none" in client.calls[1]
    assert client.calls[1].count("mark: ") == 2


class _Echo:
    """A fake model that always asks the picker's box, or shows when none."""

    def __init__(self):
        self.calls = []

    def call(self, messages, task="", timeout=None, model=None):
        content = messages[1]["content"]
        self.calls.append(content)
        box = (re.search(r"NEXT QUESTION: (\S+)", content) or [None, "none"])[1]
        if box == "none":
            data = {"action": "show_scheme", "say": "These may help.",
                    "scheme": "", "facts": {}, "parts": []}
        else:
            data = {"action": "ask", "say": "Please tell me.",
                    "ask_box": box, "facts": {}, "scheme": ""}
        return SimpleNamespace(success=True, data=data)


def _said(cid):
    path = Path(__file__).resolve().parent.parent / "fixtures" / "talk_human.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return next(c["said"] for c in data["cases"] if c["id"] == cid)


def test_prompt_carries_the_situation_block_and_new_fields():
    """Part 3: the SITUATION block, the free-question line, and the reply's
    "not" list + "just_tell" flag the code reads."""
    from haqdaar.prompts import talk as prompt
    assert "WHILE A NEXT QUESTION STANDS" in prompt.SYSTEM
    assert "AFTER \"JUST TELL ME\"" in prompt.SYSTEM
    assert '"not": []' in prompt.SYSTEM and '"just_tell": false' in prompt.SYSTEM
    assert "at most once a call" in prompt.SYSTEM
    added = len(prompt.SYSTEM.split()) - 1390
    assert added * 1.3 <= 450, added      # 6 Oct: 350 -> 450 for three rules (no sex-marked words, spoken names, first sentence)
    msgs = prompt.build("en", "", {}, {"category": ("farming",)}, "category",
                        ["category"], [], "my crops died")
    assert "NEXT QUESTION: category" in msgs[1]["content"]


@pytest.mark.parametrize("cid", CODE_IDS)
def test_live_code_cases_first_turn(corpus, tmp_path, monkeypatch, idx, cid):
    """Every "by code" fixture case runs through the live talk loop: the
    first turn takes the kind's path (held: no question; not-held: the fixed
    reply with no model call; just-tell/don't-know: the code's rule holds)."""
    from haqdaar.contracts.types import Hangup, Speech
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    said = _said(cid)
    audio = Audio([Speech(said)])
    echo = _Echo()
    log = Log.open(f"wire_case_{cid}", corpus.snapshot_id, logs_dir=str(tmp_path))
    Engine.run_call(audio, SimpleNamespace(client=echo, keypad_only=False), corpus, log)
    kind = talk_kind.kind(said, idx)
    first = echo.calls[0] if echo.calls else ""
    if kind == talk_kind.HELD_SCHEME:
        assert "NEXT QUESTION: none" in first, cid
    elif kind == talk_kind.NOT_HELD_SCHEME:
        assert echo.calls == [], cid
        assert "do not have that one yet" in audio.answers[0], cid
    elif cid in ("skip-1", "skip-2", "skip-4"):
        assert "NEXT QUESTION: none" in first, cid
    elif cid == "dontknow-1":
        assert "NEXT QUESTION: none" not in first, cid
        assert "UNKNOWN" not in first, cid
    else:
        assert first, cid
