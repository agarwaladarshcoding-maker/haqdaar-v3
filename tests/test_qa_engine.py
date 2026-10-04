"""tests/test_qa_engine.py

Step 7.1, engine side: a caller's question is answered in text and the call goes back to
where it was. Fakes only. With QA_ENABLED off nothing in the trace or log may change.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Answer, Digit, Question, Speech, Unclear
from haqdaar.data.log import Log
from haqdaar.engine.call import Engine
from haqdaar.engine.filter import Filter
from haqdaar.sim import run_sim

from tests.test_call import MockAudio, corpus  # noqa: F401  (corpus is a fixture)

QUESTION = "what does the tractor subsidy give"
ANSWER_TEXT = "It gives fifty percent subsidy."


class QAAudio(MockAudio):
    def __init__(self, inputs, initial_lang="en", said=True):
        super().__init__(inputs, initial_lang)
        self.answers: list[str] = []
        self._said = said

    def say_text(self, text):
        self.answers.append(text)
        return self._said


class PlainAudio(MockAudio):
    """No say_text, like today's PhoneAudio."""


class QAModel:
    keypad_only = False

    def __init__(self, reply=ANSWER_TEXT, turn_result=None, kind="QUESTION"):
        self.reply, self.kind = reply, kind
        self.turn_result = turn_result if turn_result is not None else Question()
        self.asked: list[tuple] = []
        self.sorted: list[tuple] = []
        self.ask_counts: list[int] = []

    def turn(self, transcript, box=None, ask_count=0):
        self.ask_counts.append(ask_count)
        return self.turn_result

    def opener(self, transcript, lang="en"):
        return Unclear(reason="unclear")

    def confirm(self, text, lang=None):
        return None

    def sort(self, asked, transcript):
        self.sorted.append((asked, transcript))
        return self.kind

    def answer(self, question, lang, cards, profile=None, scheme_ids=None, english=False):
        self.asked.append((question, lang, list(cards), scheme_ids))
        return self.reply


class NoAnswerModel:
    """A model from before 7.1: no .answer, no .sort."""
    keypad_only = False

    def turn(self, transcript, box=None, ask_count=0):
        return Unclear(reason="unclear")

    def opener(self, transcript, lang="en"):
        return Unclear(reason="unclear")

    def confirm(self, text, lang=None):
        return None


def _run(corpus, tmp_path, audio, model, name="qa"):
    log = Log.open(name, corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, model, corpus, log)
    return [json.loads(l) for l in open(tmp_path / f"{name}.jsonl")]


def _question_inputs(extra=()):
    # English, category by key, then a spoken question at the next box, then keys.
    return [Digit("3"), Digit("1"), Speech(QUESTION), *extra, Digit("2"), Digit("2"), Digit("2"),
            Digit("2"), Digit("2"), Digit("2"), Digit("2"), Digit("2")]


@pytest.fixture
def qa_on(monkeypatch):
    monkeypatch.setattr(tunables, "QA_ENABLED", True)


def test_question_in_loop_is_answered_and_call_does_not_move(corpus, tmp_path, qa_on):
    audio = QAAudio(_question_inputs())
    model = QAModel()
    lines = _run(corpus, tmp_path, audio, model)

    assert audio.answers == [ANSWER_TEXT]
    q = [l for l in lines if l.get("class") == "QUESTION"]
    assert len(q) == 1 and q[0]["answer"] == ANSWER_TEXT and q[0]["transcript"] == QUESTION
    # turn_n unchanged by the question: it carries the turn count of the line before it.
    before = lines[lines.index(q[0]) - 1]
    assert q[0]["turn_n"] == before["turn_n"]
    # no turn spent, no strike: no UNCLEAR line, no rephrase prompt, and the same box is asked twice
    assert not any(l.get("class") == "UNCLEAR" for l in lines)
    assert not any(t.startswith("rephrase_") for t in audio.played)
    asked_box_prompts = [t for t in audio.played if t.startswith(("q_", "state_q_"))]
    assert asked_box_prompts[0] == asked_box_prompts[1]
    # the named scheme's card went to the model, in English
    assert model.asked[0][3] == ["S2"] and "Tractor" in model.asked[0][2][0]


def test_question_is_not_a_strike(corpus, tmp_path, qa_on):
    model = QAModel()
    _run(corpus, tmp_path, QAAudio(_question_inputs()), model)
    assert model.ask_counts and set(model.ask_counts) == {0}


def test_sixth_question_is_not_answered(corpus, tmp_path, qa_on):
    n = tunables.QA_MAX_PER_CALL
    inputs = [Digit("3"), Digit("1")] + [Speech(QUESTION)] * (n + 1) + [Digit("2")] * 20
    audio = QAAudio(inputs)
    lines = _run(corpus, tmp_path, audio, QAModel())
    assert len(audio.answers) == n
    assert len([l for l in lines if l.get("class") == "QUESTION"]) == n
    # the one past the limit took today's path: an UNCLEAR line
    assert any(l.get("class") == "UNCLEAR" and l.get("transcript") == QUESTION for l in lines)


def test_keypad_only_never_answers(corpus, tmp_path, qa_on):
    model = QAModel()
    model.keypad_only = True
    audio = QAAudio([Digit("3"), Digit("1"), Speech(QUESTION)] + [Digit("2")] * 20)
    lines = _run(corpus, tmp_path, audio, model)
    assert audio.answers == [] and model.asked == []
    assert not any(l.get("class") == "QUESTION" for l in lines)


def test_model_without_answer_behaves_as_today(corpus, tmp_path, qa_on):
    audio = QAAudio([Digit("3"), Digit("1"), Speech(QUESTION)] + [Digit("2")] * 20)
    lines = _run(corpus, tmp_path, audio, NoAnswerModel())
    assert audio.answers == []
    assert not any(l.get("class") == "QUESTION" for l in lines)
    assert any(l.get("class") == "UNCLEAR" for l in lines)


def test_audio_without_say_text_behaves_as_today(corpus, tmp_path, qa_on):
    model = QAModel()
    audio = PlainAudio([Digit("3"), Digit("1"), Speech(QUESTION)] + [Digit("2")] * 20, "en")
    lines = _run(corpus, tmp_path, audio, model)
    assert model.asked == []
    assert not any(l.get("class") == "QUESTION" for l in lines)


def test_say_text_false_or_no_answer_falls_back_to_unclear(corpus, tmp_path, qa_on):
    for audio, model in ((QAAudio([Digit("3"), Digit("1"), Speech(QUESTION)] + [Digit("2")] * 20, said=False), QAModel()),
                         (QAAudio([Digit("3"), Digit("1"), Speech(QUESTION)] + [Digit("2")] * 20), QAModel(reply=None))):
        lines = _run(corpus, tmp_path, audio, model, name="fallback")
        assert not any(l.get("class") == "QUESTION" for l in lines)
        assert any(l.get("class") == "UNCLEAR" for l in lines)
        (tmp_path / "fallback.jsonl").unlink()


def test_qa_off_a_question_result_is_todays_unclear_path(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "QA_ENABLED", False)
    inputs = [Digit("3"), Digit("1"), Speech(QUESTION)] + [Digit("2")] * 20
    a_audio, b_audio = QAAudio(list(inputs)), MockAudio(list(inputs), "en")
    a = _run(corpus, tmp_path, a_audio, QAModel(), name="a")
    b = _run(corpus, tmp_path, b_audio, NoAnswerModel(), name="b")
    assert a[1:] == b[1:]  # all but the open line, which carries the call id
    assert a_audio.played == b_audio.played and a_audio.answers == []


def test_anything_else_question_is_answered_and_asked_again(corpus, tmp_path, qa_on):
    model = QAModel()
    audio = QAAudio([Digit("3"), Digit("1"), Digit("2"), Digit("1"), Digit("3"), Digit("0"),
                     Speech(QUESTION), Digit("2")], "en")
    lines = _run(corpus, tmp_path, audio, model)
    assert model.sorted == [("anything_else", QUESTION)]
    assert audio.answers == [ANSWER_TEXT]
    assert audio.played.count("anything_else") == 2
    assert any(l.get("class") == "QUESTION" for l in lines)


def test_anything_else_other_kind_is_not_answered(corpus, tmp_path, qa_on):
    model = QAModel(kind="OTHER")
    audio = QAAudio([Digit("3"), Digit("1"), Digit("2"), Digit("1"), Digit("3"), Digit("0"),
                     Speech(QUESTION), Digit("2")], "en")
    _run(corpus, tmp_path, audio, model)
    assert audio.answers == [] and audio.played.count("anything_else") == 1


def test_section_menu_question_is_answered_about_the_open_scheme(corpus, tmp_path, qa_on):
    model = QAModel()
    audio = QAAudio([Digit("3"), Digit("1"), Digit("2"), Digit("1"), Digit("3"),
                     Speech("how do I apply"), Digit("0"), Digit("2")], "en")
    _run(corpus, tmp_path, audio, model)
    assert model.sorted == [("section_menu", "how do I apply")]
    # The scheme whose menu is open comes first, then the other results just read.
    assert model.asked[0][3][0] == "S1" and len(model.asked[0][3]) <= tunables.QA_MAX_SCHEMES
    assert audio.answers == [ANSWER_TEXT]
    assert audio.played.count("section_menu") == 3  # S1, then S1's menu again, then S2


def test_both_question_is_tried_after_the_confirm_accepts(corpus, tmp_path, qa_on):
    class BothModel(QAModel):
        def turn(self, transcript, box=None, ask_count=0):
            vals = corpus.values(box)
            return Answer(box=box, value=vals[0], span=transcript, also_question=True)

        def confirm(self, text, lang=None):
            return True

    audio = QAAudio([Digit("3"), Digit("1"), Speech("yes " + QUESTION), Speech("yes"), Digit("2")] + [Digit("2")] * 20)
    model = BothModel()
    lines = _run(corpus, tmp_path, audio, model)
    q = [i for i, l in enumerate(lines) if l.get("class") == "QUESTION"]
    a = [i for i, l in enumerate(lines)
         if l.get("class") == "ANSWER" and l.get("transcript") == "yes"]
    assert len(q) == 1 and a and a[0] < q[0]
    assert audio.answers == [ANSWER_TEXT]


def test_aadhaar_sized_number_is_masked_in_the_log(corpus, tmp_path, qa_on):
    audio = QAAudio([Digit("3"), Digit("1"), Speech(QUESTION + " 123456789012")] + [Digit("2")] * 20)
    lines = _run(corpus, tmp_path, audio, QAModel())
    q = [l for l in lines if l.get("class") == "QUESTION"]
    assert q and "123456789012" not in q[0]["transcript"] and "…" in q[0]["transcript"]


def test_summary_counts_as_heard_only_if_the_clip_played(corpus, tmp_path):
    class HeardAudio(MockAudio):
        def heard(self, token):
            return token.endswith(":S1:summary") or token.endswith("S1:summary")

    inputs = [Digit("1"), Digit("1"), Digit("2"), Digit("1"), Digit("3"), Digit("9"), Digit("9"), Digit("2")]
    audio = HeardAudio(list(inputs))
    log = Log.open("heard", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)
    deliveries = [json.loads(l) for l in open(tmp_path / "heard.jsonl") if '"slug"' in l]
    assert deliveries
    for rec in deliveries:
        assert ("summary" in rec["sections"]) == (rec["slug"] == "S1"), rec

    # an audio without `heard` keeps today's behaviour: summary for every named scheme
    audio = MockAudio(list(inputs))
    log = Log.open("noheard", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, None, corpus, log)
    deliveries = [json.loads(l) for l in open(tmp_path / "noheard.jsonl") if '"slug"' in l]
    assert deliveries and all("summary" in r["sections"] for r in deliveries)


def _clean(path: Path):
    out = []
    for l in open(path):
        d = json.loads(l)
        d.pop("t", None); d.pop("at", None); d.pop("start", None); d.pop("call_id", None)
        d.pop("t0", None)
        s = json.dumps(d, sort_keys=True)
        s = re.sub(r'"t_(name|end)": [0-9.e-]+', '"t_x": 0', s)
        s = re.sub(r"sim_off|sim_on", "ID", s)
        s = re.sub(r"\(\d+(\.\d+)? s\)", "(N s)", s)
        out.append(s)
    return out


def test_sim_call_with_qa_off_and_on_but_no_question_is_identical(tmp_path, monkeypatch, capsys):
    paths = {}
    for name, flag in (("sim_off", False), ("sim_on", True)):
        monkeypatch.setattr(tunables, "QA_ENABLED", flag)
        paths[name] = run_sim(call_id=name, logs_dir=str(tmp_path))
    capsys.readouterr()
    assert _clean(paths["sim_off"]) == _clean(paths["sim_on"])
    assert _clean(tmp_path / "trace" / "sim_off.jsonl") == _clean(tmp_path / "trace" / "sim_on.jsonl")
    assert "QUESTION" not in Path(paths["sim_on"]).read_text()


# --- 7.3: search, the opener, the read-back ---------------------------------------------------

WEAVER_Q = "I want a working capital loan at low interest for my weavers"


def test_opener_question_is_answered_by_search_and_the_opener_is_asked_again(corpus, tmp_path, qa_on, monkeypatch):
    monkeypatch.setattr(tunables, "QA_SEARCH", True)
    # At the opener no gate fact is known, so no scheme is speakable yet; make them so for this test.
    monkeypatch.setattr(Filter, "speakable", staticmethod(lambda *a, **k: True))
    model = QAModel()
    audio = QAAudio([Digit("3"), Speech(WEAVER_Q)] + [Digit("2")] * 20)
    lines = _run(corpus, tmp_path, audio, model)
    assert model.sorted[0] == ("opener", WEAVER_Q)
    assert audio.answers == [ANSWER_TEXT] and model.asked[0][3][0] == "S5"
    assert audio.played.count("opener_prompt") >= 2  # asked again, no strike, no turn
    q = [l for l in lines if l.get("class") == "QUESTION"]
    assert len(q) == 1 and not any(l.get("class") == "UNCLEAR" for l in lines)


def test_opener_question_with_nothing_speakable_is_not_answered(corpus, tmp_path, qa_on, monkeypatch):
    monkeypatch.setattr(tunables, "QA_SEARCH", True)
    model = QAModel()
    audio = QAAudio([Digit("3"), Speech(WEAVER_Q)] + [Digit("2")] * 20)
    _run(corpus, tmp_path, audio, model)
    assert audio.answers == [] and model.asked == []


def test_opener_question_without_search_is_not_answered(corpus, tmp_path, qa_on, monkeypatch):
    monkeypatch.setattr(tunables, "QA_SEARCH", False)
    model = QAModel()
    audio = QAAudio([Digit("3"), Speech(WEAVER_Q)] + [Digit("2")] * 20)
    lines = _run(corpus, tmp_path, audio, model)
    assert audio.answers == [] and model.asked == []
    assert any(l.get("class") == "UNCLEAR" for l in lines)


def test_opener_other_kind_is_not_answered(corpus, tmp_path, qa_on, monkeypatch):
    monkeypatch.setattr(tunables, "QA_SEARCH", True)
    audio = QAAudio([Digit("3"), Speech(WEAVER_Q)] + [Digit("2")] * 20)
    _run(corpus, tmp_path, audio, QAModel(kind="OTHER"))
    assert audio.answers == []


def test_opener_that_names_a_scheme_stays_door_a(corpus, tmp_path, qa_on, monkeypatch):
    monkeypatch.setattr(tunables, "QA_SEARCH", True)
    model = QAModel()
    audio = QAAudio([Digit("3"), Speech("tractor subsidy")] + [Digit("2")] * 20)
    _run(corpus, tmp_path, audio, model)
    assert model.sorted == [] and audio.answers == []


def test_named_scheme_wins_over_search(corpus, tmp_path, qa_on, monkeypatch):
    monkeypatch.setattr(tunables, "QA_SEARCH", True)
    monkeypatch.setattr(tunables, "QA_MAX_SCHEMES", 1)
    model = QAModel()
    _run(corpus, tmp_path, QAAudio(_question_inputs()), model)
    assert model.asked[0][3] == ["S2"]


def test_question_at_the_read_back_is_answered_and_read_back_again(corpus, tmp_path, qa_on):
    class ConfirmModel(QAModel):
        def turn(self, transcript, box=None, ask_count=0):
            return Answer(box=box, value=corpus.values(box)[0], span=transcript)

        def confirm(self, text, lang=None):
            return True if text == "yes" else None

    model = ConfirmModel()
    audio = QAAudio([Digit("3"), Digit("1"), Speech("hello"), Speech(QUESTION), Speech("yes")] + [Digit("2")] * 20)
    lines = _run(corpus, tmp_path, audio, model)
    assert audio.answers == [ANSWER_TEXT]
    assert audio.played.count("bundle_confirm_intro") >= 2
    assert not any(l.get("class") == "UNCLEAR" for l in lines)
    assert any(l.get("class") == "ANSWER" and l.get("transcript") == "yes" for l in lines)


def test_a_question_naming_a_scheme_at_the_opener_is_answered_not_read_out(corpus, tmp_path, qa_on):
    """Added at Claude's review: a question about a named scheme at the first prompt is answered
    from that one scheme, the scheme is not read out, and the opener is asked again."""
    model = QAModel()
    q = "how much money does tractor subsidy give"
    audio = QAAudio([Digit("3"), Speech(q)] + [Digit("2")] * 20)
    lines = _run(corpus, tmp_path, audio, model)
    assert model.sorted[0] == ("opener", q)
    assert audio.answers == [ANSWER_TEXT] and len(model.asked[0][3]) == 1
    assert audio.played.count("opener_prompt") >= 2
    assert len([l for l in lines if l.get("class") == "QUESTION"]) == 1
