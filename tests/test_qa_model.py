"""tests/test_qa_model.py

Step 7.1, model side. Fakes only: no network, no real model.
"""
from __future__ import annotations

import json

import pytest

from haqdaar.contracts import tunables, vocab
from haqdaar.contracts.types import Answer, Question, Repeat, Unclear
from haqdaar.model.answer import digits_of, mask_digits
from haqdaar.model.client import GroqModelClient, ModelClientResponse
from haqdaar.model.confirm import match_confirm
from haqdaar.model.prompts.opener import build_opener_prompt
from haqdaar.model.prompts.turn import build_turn_prompt
from haqdaar.model.router import Model

CARDS = "[pm-kisan]\nbenefit_text: Rs. 6,000 per year in three instalments.\nexclusions: Income tax payers are excluded."


class ScriptedClient(GroqModelClient):
    """Returns scripted replies in order and records every call, including per-call timeout and model."""

    def __init__(self, replies=()):
        super().__init__(api_key="fake_key")
        self.replies = list(replies)
        self.calls: list[dict] = []

    def call(self, messages, task="model_router", timeout=None, model=None):
        self.calls.append({"messages": messages, "task": task, "timeout": timeout, "model": model})
        if self.replies:
            r = self.replies.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        return ModelClientResponse(success=True, data={})


def ok(data):
    return ModelClientResponse(success=True, data=data)


def fail(timeout=False):
    return ModelClientResponse(success=False, data=None, error="timeout" if timeout else "http_500", is_timeout=timeout)


class FakeTranslator:
    def __init__(self, out):
        self.out = out
        self.seen = []

    def translate(self, text, lang):
        self.seen.append((text, lang))
        return self.out


@pytest.fixture
def qa_on(monkeypatch):
    monkeypatch.setattr(tunables, "QA_ENABLED", True)


def lines(tmp_path):
    path = tmp_path / "reports" / "questions.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


# --- Model.turn ----------------------------------------------------------------------------

def test_turn_prompt_off_is_the_old_prompt_byte_for_byte():
    old = build_turn_prompt("I am a farmer", "occupation", ("farmer", "worker"), None, 1)
    new = build_turn_prompt("I am a farmer", "occupation", ("farmer", "worker"), None, 1,
                            qa=False, english=False, lang="hi")
    assert old == new
    assert "kind" not in old and "translation" not in old
    # pinned: the first and last lines of today's text
    assert old.startswith('The caller was asked about box: "occupation".\nValid closed-set choices')
    assert old.endswith("- For UNCLEAR: {\"class\": \"UNCLEAR\", \"reason\": \"<reason>\"}\n\nJSON Output:")


def test_opener_prompt_off_is_unchanged():
    base = build_opener_prompt("I am a farmer", lang="en")
    assert build_opener_prompt("I am a farmer", lang="en", english=False) == base
    assert "English translation" in build_opener_prompt("I am a farmer", lang="hi", english=True)


def test_turn_sends_the_old_prompt_when_qa_is_off(monkeypatch):
    monkeypatch.setattr(tunables, "QA_ENABLED", False)
    client = ScriptedClient([ok({"class": "REPEAT"})])
    r = Model(client=client).turn("I am a farmer", box="occupation")
    assert isinstance(r, Repeat)
    sent = client.calls[0]["messages"][1]["content"]
    assert sent == build_turn_prompt("I am a farmer", "occupation", ("farmer", "street_vendor", "apprentice",
                                     "entrepreneur", "artisan", "weaver", "worker"), None, 0)


def test_turn_english_note_added_only_when_english(monkeypatch):
    monkeypatch.setattr(tunables, "QA_ENABLED", False)
    client = ScriptedClient([ok({}), ok({})])
    m = Model(client=client)
    m.turn("I am a farmer", box="occupation", english=True, lang="hi")
    m.turn("I am a farmer", box="occupation")
    assert "English translation of speech in Hindi" in client.calls[0]["messages"][1]["content"]
    assert "translation" not in client.calls[1]["messages"][1]["content"]


def test_turn_kinds_map_to_result_classes(qa_on):
    ans = {"kind": "ANSWER", "box": "occupation", "value": "farmer", "span": "farmer"}
    client = ScriptedClient([ok(ans), ok({**ans, "kind": "BOTH"}), ok({"kind": "QUESTION"}),
                             ok({"kind": "REPEAT"}), ok({"kind": "OTHER"}), ok({}), ok({"kind": "banana"})])
    m = Model(client=client)
    a = m.turn("I am a farmer", box="occupation")
    assert a == Answer(box="occupation", value="farmer", span="farmer") and a.also_question is False
    b = m.turn("I am a farmer, will I get a loan?", box="occupation")
    assert isinstance(b, Answer) and b.also_question is True
    assert isinstance(m.turn("how much money", box="occupation"), Question)
    assert isinstance(m.turn("say again", box="occupation"), Repeat)
    assert isinstance(m.turn("hello", box="occupation"), Unclear)
    assert isinstance(m.turn("hello", box="occupation"), Unclear)   # missing kind
    assert isinstance(m.turn("hello", box="occupation"), Unclear)   # unknown kind


def test_turn_kind_prompt_carries_the_rules(qa_on):
    client = ScriptedClient([ok({"kind": "OTHER"})])
    Model(client=client).turn("hello", box="occupation")
    sent = client.calls[0]["messages"][1]["content"]
    assert "Go through the rules in order" in sent and '"kind"' in sent


def test_turn_answer_still_goes_through_the_span_guard(qa_on):
    client = ScriptedClient([ok({"kind": "ANSWER", "box": "occupation", "value": "farmer", "span": "farmer"})])
    r = Model(client=client).turn("I drive an auto", box="occupation")
    assert isinstance(r, Unclear)


def test_turn_bad_json_is_unclear_and_counts_as_a_failure(qa_on):
    m = Model(client=ScriptedClient([ModelClientResponse(success=False, data=None, error="json_parse_error")]))
    assert isinstance(m.turn("hello", box="occupation"), Unclear)
    assert m.failures == 1


# --- Model.sort ----------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["ANSWER", "BOTH", "QUESTION", "REPEAT", "OTHER"])
def test_sort_returns_each_kind(kind):
    client = ScriptedClient([ok({"kind": kind})])
    assert Model(client=client).sort("Anything else?", "something") == kind
    assert "Anything else?" in client.calls[0]["messages"][0]["content"]


@pytest.mark.parametrize("reply", [fail(), fail(True), ok({}), ok({"kind": "MAYBE"}), RuntimeError("boom")])
def test_sort_failure_gives_other_and_is_not_counted(reply):
    m = Model(client=ScriptedClient([reply]))
    assert m.sort("Anything else?", "something") == "OTHER"
    assert m.failures == 0


# --- find_verdict --------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang", [
    ("You can apply at the office.", "en"), ("You cannot apply for this.", "en"),
    ("You are not eligible.", "en"), ("आप आवेदन कर सकते हैं।", "hi"), ("आप आवेदन नहीं कर सकते।", "hi"),
    ("आपको मिलेगा।", "hi"), ("तुम्ही अर्ज करू शकता.", "mr"), ("तुम्हाला मिळेल.", "mr"),
])
def test_find_verdict_hits(text, lang):
    assert vocab.find_verdict(text, lang)


@pytest.mark.parametrize("text,lang", [
    ("Farmers with land can apply. Rs. 6,000 a year.", "en"),
    ("किसान परिवार को हर साल 6,000 रुपये मिलते हैं।", "hi"),
    ("शेतकरी कुटुंबाला वर्षाला 6,000 रुपये मिळतात.", "mr"),
])
def test_find_verdict_misses_rule_statements(text, lang):
    assert vocab.find_verdict(text, lang) is None


# --- confirm words -------------------------------------------------------------------------

@pytest.mark.parametrize("text,lang,want", [
    ("हाँ", "hi", True), ("हां", "hi", True), ("जी हाँ", "hi", True), ("सही है", "hi", True), ("ठीक है", "hi", True),
    ("नहीं", "hi", False), ("गलत", "hi", False),
    ("हो", "mr", True), ("होय", "mr", True), ("बरोबर", "mr", True), ("नाही", "mr", False), ("नको", "mr", False),
])
def test_devanagari_yes_no(text, lang, want):
    assert match_confirm(text, lang) is want


def test_hindi_ho_inside_a_sentence_is_not_a_yes():
    assert match_confirm("तुम बेकार हो", "hi") is None
    assert match_confirm("हो", "hi") is None


def test_english_first_when_english():
    assert match_confirm("Yes.", "hi", english=True) is True
    assert match_confirm("No, that is wrong", "mr", english=True) is False
    assert match_confirm("हाँ", "hi", english=True) is True   # backup path text still works
    assert Model(client=ScriptedClient()).confirm("Yes.", lang="hi", english=True) is True


# --- Model.answer --------------------------------------------------------------------------

def answer(client, question="How much does PM Kisan give?", lang="en", **kw):
    m = Model(client=client, translator=kw.pop("translator", None))
    return m, m.answer(question, lang, kw.pop("cards", CARDS), scheme_ids=["pm-kisan"], **kw)


def test_answer_good(tmp_path):
    client = ScriptedClient([ok({"answer": "The scheme pays Rs. 6,000 per year."})])
    _, text = answer(client)
    assert text == "The scheme pays Rs. 6,000 per year."
    assert client.calls[0]["task"] == "qa_answer"
    assert client.calls[0]["timeout"] is not None and client.calls[0]["timeout"] <= tunables.QA_TIMEOUT_S
    [line] = lines(tmp_path)
    assert line["blocked_by"] is None and line["answer"] == text and line["scheme_ids"] == ["pm-kisan"]
    assert {"ts", "lang", "question", "seconds"} <= set(line)


@pytest.mark.parametrize("reply,blocked", [
    ({"answer": None}, "model_null"),
    ({"answer": "NOT_IN_TEXT"}, "model_null"),
    ({"answer": "You can apply for it."}, "verdict"),
    ({"answer": "You are eligible for the scheme."}, "forbidden"),
    ({"answer": "The scheme pays Rs. 7,500 per year."}, "number"),
    ({"answer": " ".join(["word"] * 41)}, "too_long"),
])
def test_answer_blocked(reply, blocked, tmp_path):
    _, text = answer(ScriptedClient([ok(reply)]))
    assert text is None
    assert lines(tmp_path)[0]["blocked_by"] == blocked


def test_answer_rs_dot_is_not_a_sentence_end():
    _, text = answer(ScriptedClient([ok({"answer": "It pays Rs. 6,000 a year. It comes in three parts."})]))
    assert text is not None


def test_answer_devanagari_digits_count_as_digits():
    cards = "benefit_text: साल में 6,000 रुपये"
    _, text = answer(ScriptedClient([ok({"answer": "हर साल ६००० रुपये।"})]), lang="hi", cards=cards)
    assert text is not None


def test_answer_client_error_gives_none_and_no_failure(tmp_path):
    client = ScriptedClient([fail(True), fail(True)])
    m, text = answer(client)
    assert text is None and m.failures == 0 and not m.keypad_only
    assert lines(tmp_path)[0]["blocked_by"] == "timeout"
    assert len(client.calls) == 2


def test_answer_backup_model_is_tried_once(monkeypatch):
    monkeypatch.setattr(tunables, "QA_BACKUP_MODEL", "backup/model")
    client = ScriptedClient([fail(), ok({"answer": "It pays Rs. 6,000 a year."})])
    _, text = answer(client)
    assert text == "It pays Rs. 6,000 a year."
    assert client.calls[0]["model"] is None and client.calls[1]["model"] == "backup/model"
    assert client.calls[1]["timeout"] <= tunables.QA_TIMEOUT_S


def test_answer_a_raising_client_never_raises():
    m, text = answer(ScriptedClient([RuntimeError("x"), RuntimeError("y")]))
    assert text is None and m.failures == 0


def test_answer_masks_long_digit_runs(tmp_path):
    client = ScriptedClient([ok({"answer": None})])
    answer(client, question="my aadhaar is 123456789012 and phone ९८७६५४३२१०")
    sent = client.calls[0]["messages"][1]["content"]
    assert "123456789012" not in sent and "…" in sent
    assert "123456789012" not in json.dumps(lines(tmp_path))
    assert mask_digits("age 65") == "age 65"


def test_answer_no_cards_is_none_without_a_call():
    client = ScriptedClient()
    _, text = answer(client, cards="")
    assert text is None and client.calls == []


def test_answer_prompt_has_the_rules():
    client = ScriptedClient([ok({"answer": None})])
    answer(client)
    system = client.calls[0]["messages"][0]["content"]
    assert "NEVER tell the caller yes or no" in system and CARDS in system


# --- ENGLISH_PIPE --------------------------------------------------------------------------

def test_pipe_translates_and_logs_both(monkeypatch, tmp_path):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)
    tr = FakeTranslator("योजना साल में 6,000 रुपये देती है।")
    client = ScriptedClient([ok({"answer": "The scheme pays Rs. 6,000 per year."})])
    _, text = answer(client, lang="hi", english=True, translator=tr)
    assert text == "योजना साल में 6,000 रुपये देती है।"
    assert tr.seen == [("The scheme pays Rs. 6,000 per year.", "hi")]
    assert "Write in English" in client.calls[0]["messages"][0]["content"]
    line = lines(tmp_path)[0]
    assert line["answer"] == text and line["answer_en"].startswith("The scheme") and line["question_en"]


def test_pipe_changed_number_gives_none(monkeypatch, tmp_path):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)
    tr = FakeTranslator("योजना साल में 3,200 रुपये देती है।")
    _, text = answer(ScriptedClient([ok({"answer": "The scheme pays Rs. 6,000 per year."})]),
                     lang="hi", english=True, translator=tr)
    assert text is None and lines(tmp_path)[0]["blocked_by"] == "translate"


@pytest.mark.parametrize("out", [None, "आप आवेदन कर सकते हैं 6,000"])
def test_pipe_translate_failure_or_verdict_gives_none(monkeypatch, out):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)
    _, text = answer(ScriptedClient([ok({"answer": "The scheme pays Rs. 6,000 per year."})]),
                     lang="hi", english=True, translator=FakeTranslator(out))
    assert text is None


def test_pipe_off_never_translates(monkeypatch):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", False)
    tr = FakeTranslator("should not be used")
    client = ScriptedClient([ok({"answer": "योजना साल में 6,000 रुपये देती है।"})])
    _, text = answer(client, lang="hi", english=True, translator=tr, cards="benefit_text: 6,000 रुपये")
    assert text and tr.seen == []
    assert "Write in Hindi" in client.calls[0]["messages"][0]["content"]


def test_digits_of():
    assert digits_of("Rs. 6,000 and ६००० and 65") == {"6000", "65"}


def test_a_long_answer_keeps_its_first_two_sentences():
    """Whole sentences cut off the end add nothing untrue; the answer is not thrown away."""
    from haqdaar.model.answer import shorten
    assert shorten("One. Two. Three.") == "One. Two."
    assert shorten("Rs. 5 is paid. Two. Three.") == "Rs. 5 is paid. Two."
    assert shorten("एक। दो। तीन।") == "एक। दो।"
    assert shorten("Only one.") == "Only one."


def test_answer_takes_one_text_per_scheme_as_the_engine_gives_it(tmp_path):
    """Found by a full typed call at Claude's review: the engine passes a list of cards."""
    from haqdaar.model import answer as qa
    assert qa.check_answer("It pays 6,000.", "en", "\n\n".join(["Card one: 6,000 a year.", "Card two."])) is None
    import inspect
    from haqdaar.model.router import Model
    assert "isinstance(cards, str)" in inspect.getsource(Model.answer)
