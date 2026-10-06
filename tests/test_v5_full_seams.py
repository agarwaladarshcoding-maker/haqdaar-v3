"""v5-full seams: the call-back skips the greeting and the pick; the photo state lives for the whole call
(key 6 -> keys -> talk); languages outside hi mr en gu ta take no slot. Fakes only: no network, no money."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.log import Log
from haqdaar.engine import talk as talk_mod
from haqdaar.engine.call import Engine
from haqdaar.photo import cases, in_call
from haqdaar.prompts import talk as prompt

from tests.test_photo_in_call import NUMBER, _ready, corpus, photo_dir, sms  # noqa: F401  (fixtures)
from tests.test_step18_followup import FIRST_IDS, NamedIndex
from tests.test_step3_keys import KeysAudio
from tests.test_talk import Audio, Client, _say

P = prompt.PHOTO


class _Greeting(Audio):
    """A caller who speaks in language `lang` after a pick. `picked` counts the calls of select_language."""

    def __init__(self, inputs, lang="en"):
        super().__init__(inputs)
        self.picked = 0
        self.language = lang

    def select_language(self):
        self.picked += 1
        return super().select_language()


class _CallBackAudio(_Greeting):
    """The pick key is not there: a call-back never asks for it."""

    def __init__(self, inputs, lang="en"):
        super().__init__(inputs, lang)
        self.inputs.pop(0)


@pytest.fixture
def run(corpus, tmp_path, monkeypatch, photo_dir, sms):  # noqa: F811
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "KEYS_IN_TALK", True)
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": NamedIndex(FIRST_IDS))
    made = []

    def go(inputs, replies=(), audio=_Greeting, lang="en"):
        made.append(1)
        audio = audio(inputs, lang)
        audio.caller_number = NUMBER
        client = Client(list(replies))
        log = Log.open(f"seams_{len(made)}", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
        return audio, client, log_text.read_rows(log.path)

    return go


def _said(audio):
    return " ".join(audio.answers).strip()


def test_a_pending_answer_skips_the_greeting_and_the_pick(run, photo_dir):
    _ready(lang="hi")
    audio, client, rows = run([Speech("how are you")], [_say("Fine.")], audio=_CallBackAudio)
    assert audio.picked == 0 and "greeting_trilingual" not in audio.played
    assert _said(audio).startswith(P["back"]["hi"])               # the answer, in the stored language
    assert "Fine." in audio.answers or any("Fine" in a for a in audio.answers)   # and the talk goes on
    row = next(r for r in rows if r.get("lang_source"))
    assert row["lang"] == "hi" and row["lang_source"] == "default"
    assert not (photo_dir / "next_call.json").exists()           # _call_back took it


def test_no_pending_answer_the_greeting_is_as_before(run):
    audio, _, _ = run([Speech("how are you")], [_say("Fine.")])
    assert audio.picked == 1 and "greeting_trilingual" in audio.played


def test_a_fault_in_pending_leaves_the_call_as_it_is(run, monkeypatch):
    seen = []

    def boom(now=None):
        seen.append(1)
        if len(seen) == 1:      # the call's own check; the talk's own read has no guard today
            raise RuntimeError("x")
        return None
    monkeypatch.setattr(in_call, "pending", boom)
    audio, _, _ = run([Hangup()])
    assert audio.picked == 1


def test_photo_in_call_off_the_pending_answer_does_not_skip_the_greeting(run, monkeypatch):
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", False)
    _ready()
    audio, _, _ = run([Hangup()])
    assert audio.picked == 1


def test_key_6_keys_talk_key_9_says_already_sent_and_makes_no_second_case(run, sms, monkeypatch, photo_dir):
    monkeypatch.setattr(tunables, "PHOTO_HANGUP", False)
    audio, _, rows = run(
        [Speech("can I send a photo"), Speech("yes"), Digit("6"), Digit("0"),
         Speech("how much money does it give"), Digit("9"), Hangup()],
        [_say("It gives money to families.")], audio=KeysAudio)
    assert len(sms) == 1
    assert _said(audio).count(P["sent"]["hi"]) == 1 and P["already"]["hi"] in _said(audio)
    assert len([d for d in photo_dir.iterdir() if d.is_dir()]) == 1


def test_call_back_after_key_6_and_back_the_prompt_still_has_the_first_call_and_photo_blocks(run, photo_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "CALL_LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(tunables, "PHOTO_FIRST_CALL", True)
    run([Speech("I am a farmer from Bihar and my wheat is yellow"), Hangup()], [_say("There is a crop scheme.")])
    case = _ready()
    cases.set_first_call(case.token, "seams_1", ["pm-kisan"])
    audio, client, _ = run(
        [Digit("6"), Digit("0"), Speech("what should I do about it"), Hangup()],
        [_say("Spray it.")], audio=lambda i, l: _CallBackKeys(i, l))
    asked = client.calls[0]
    assert "THE FIRST CALL" in asked and "WHAT THE PHOTO SHOWS" in asked and "wheat is yellow" in asked


class _CallBackKeys(KeysAudio):
    def __init__(self, inputs, lang="en"):
        super().__init__(inputs)
        self.inputs.pop(0)
        self.picked = 0


def test_languages_outside_the_five_take_no_slot(corpus, photo_dir, sms):  # noqa: F811
    class A:
        language = "bn"

    talk = talk_mod._Talk(A(), None, corpus, None, "bn", NamedIndex(FIRST_IDS))
    for lang in ("te", "kn", "pa", "hi", "mr"):
        talk.lang = lang
        talk._note_lang()
    assert talk.langs_spoken == ["hi", "mr"]
    res = in_call.send_link("mr", talk.langs_spoken, NUMBER, sms=lambda to, text: "SM1")
    assert set(cases.get(res["token"]).langs) == {"hi", "mr"}


# Step D: the photo answer in the caller's language; "send the link" is a photo ask.
_BACK_SAY = "Close-up of green leaves. Leaves look pale. नमस्ते यह हिंदी है।"


def _back_run(run, monkeypatch, fake, lang="hi"):
    from haqdaar.model import middle
    monkeypatch.setattr(tunables, "PHOTO_BACK_TRANSLATE", True)
    monkeypatch.setattr(middle, "reply_in", fake)
    case = _ready(lang=lang)
    (cases._base_dir() / "next_call.json").write_text(
        json.dumps({"token": case.token, "lang": lang, "say": _BACK_SAY, "made": case.made}))
    audio, _, _ = run([Hangup()], audio=_CallBackAudio, lang=lang)
    return _said(audio)


def test_call_back_translates_the_english_sentences_only_and_keeps_the_order(run, monkeypatch):
    from haqdaar.model.middle import Out
    sent = []

    def fake(text, lang):
        sent.append(text)
        yield Out(text="HI[" + text + "]", ok=True, ms=0)
    said = _back_run(run, monkeypatch, fake)
    assert sent == ["Close-up of green leaves.", "Leaves look pale."]
    assert said.index("HI[Close-up of green leaves.]") < said.index("HI[Leaves look pale.]") < said.index("नमस्ते यह हिंदी है।")


def test_call_back_says_the_english_when_the_translate_raises(run, monkeypatch):
    def boom(text, lang):
        raise RuntimeError("x")
    said = _back_run(run, monkeypatch, boom)
    assert "Close-up of green leaves. Leaves look pale." in said


def test_call_back_in_english_never_calls_reply_in(run, monkeypatch):
    def fake(text, lang):
        raise AssertionError("called")
    said = _back_run(run, monkeypatch, fake, lang="en")
    assert "Close-up of green leaves." in said


@pytest.mark.parametrize("words", ["Yes, please send the link.", "लिंक भेज दीजिए", "link bhej do", "लिंक पाठव"])
def test_asking_for_the_link_with_no_offer_open_gives_the_offer_and_no_model_call(run, words):
    audio, client, _ = run([Speech(words), Hangup()], [_say("MODEL")])
    assert P["offer"]["en"] in _said(audio) and client.calls == []


def test_a_plain_yes_with_no_offer_open_is_not_a_photo_ask(run):
    audio, client, _ = run([Speech("yes"), Hangup()], [_say("MODEL")])
    assert P["offer"]["en"] not in _said(audio)
