"""The call-back call that does not finish: the demo's cut line (the drop flag) and a caller who hangs up
mid-answer. The file must stay, so the end of the call sends the answer by SMS. Fake audio, model and SMS."""
import threading
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.log import Log
from haqdaar.engine.call import Engine
from haqdaar.photo import cases, in_call
from haqdaar.prompts import talk as prompt

from tests.test_photo_in_call import _ready, _said, call, corpus, photo_dir, sms  # noqa: F401  (fixtures)
from tests.test_step18_followup import FIRST_IDS, LangAudio, NamedIndex
from tests.test_talk import Client, _say

P = prompt.PHOTO


class HangsUpWhen(LangAudio):
    """The caller hangs up while `text` is being said: say_text comes back normally, as on a real line."""

    def __init__(self, inputs, text):
        super().__init__(inputs, "en")
        self.turn = SimpleNamespace(hung_up=threading.Event())
        self.when = text

    def say_text(self, text, *a, **kw):
        ok = super().say_text(text, *a, **kw)
        if self.when in text:
            self.turn.hung_up.set()
        return ok


@pytest.fixture
def run(corpus, tmp_path, monkeypatch, photo_dir, sms):  # noqa: F811
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": NamedIndex(FIRST_IDS))

    def go(audio):
        client = Client([_say("Fine.")], 0.0)
        audio.caller_number = "+919999900001"
        log = Log.open("back_drop", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
        return audio, client, log_text.read_rows(log.path)

    return go


def test_the_drop_flag_says_the_hello_then_hangs_up_and_keeps_the_file(call, photo_dir):
    case = _ready()
    assert in_call.set_drop(case.token)
    audio, client, rows = call([Speech("how are you")], [_say("Fine.")])
    assert _said(audio) == P["back"]["en"]                    # the hello only: no answer, no talk
    assert client.calls == [] and (photo_dir / "next_call.json").exists()
    assert cases.get(case.token).state != "called"


def test_the_drop_flag_with_a_bad_photo_also_keeps_the_file(call, photo_dir):
    case = _ready(sure=0.1)
    in_call.set_drop(case.token)
    audio, _, _ = call([Speech("how are you")], [])
    assert _said(audio) == P["bad"]["en"] and (photo_dir / "next_call.json").exists()
    assert cases.get(case.token).state == "read"             # done() did not run: the photo is not dropped


def test_without_the_flag_the_call_back_is_as_before(call, photo_dir):
    case = _ready()
    audio, _, _ = call([Speech("how are you")], [_say("Fine.")])
    assert _said(audio).startswith(P["back"]["en"] + " I see a wall.")
    assert not (photo_dir / "next_call.json").exists() and cases.get(case.token).state == "called"


def test_a_caller_who_hangs_up_in_the_hello_keeps_the_file(run, photo_dir):
    case = _ready()
    audio, client, _ = run(HangsUpWhen([Speech("how are you")], P["back"]["en"].split(".")[0]))
    assert "I see a wall." not in _said(audio) and client.calls == []
    assert (photo_dir / "next_call.json").exists() and cases.get(case.token).state != "called"


def test_a_caller_who_hangs_up_in_the_answer_keeps_the_file(run, photo_dir):
    """The answer's last sentence is cut off: say_text returns normally, only the hang-up flag tells."""
    case = _ready()
    audio, _, _ = run(HangsUpWhen([Speech("how are you")], "I see a wall."))
    assert "I see a wall." in _said(audio)
    assert (photo_dir / "next_call.json").exists() and cases.get(case.token).state != "called"


def test_a_caller_who_hears_it_all_clears_the_file(run, photo_dir):
    case = _ready()
    run(HangsUpWhen([Speech("how are you")], "never said"))
    assert not (photo_dir / "next_call.json").exists() and cases.get(case.token).state == "called"
