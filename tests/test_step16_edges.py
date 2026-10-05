"""Step 1.6: edge cases of the talk call. The speech service fails, a model fails, the voice
fails, the call reaches its cap. Also the faults the read of 1.3b found in the talk loop."""
from types import SimpleNamespace

import pytest

from haqdaar.audio import phone as phone_mod
from haqdaar.contracts import tunables
from haqdaar.contracts.types import UNASKED, Noise, Silence, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.log import Log
from haqdaar.engine import talk as talk_mod
from haqdaar.engine import talk_words
from haqdaar.engine.call import Engine
from haqdaar.prompts import talk as prompt

from tests.test_silence_rules import _phone
from tests.test_talk import Audio, Client, Index, _say, call, corpus  # noqa: F401  (fixtures)


class _Models:
    """A client where the named models fail in the named way."""

    def __init__(self, fail, reply):
        self.fail, self.reply, self.models = fail, reply, []

    def call(self, messages, task="", timeout=None, model=None):
        self.models.append(model)
        if model in self.fail:
            return SimpleNamespace(success=False, data=None, is_429=False, is_timeout=self.fail[model] == "timeout")
        return SimpleNamespace(success=True, data=self.reply)


def _run(corpus, tmp_path, monkeypatch, audio, client, name):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())
    log = Log.open(name, corpus.snapshot_id, logs_dir=str(tmp_path))
    Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
    return log_text.read_rows(log.path)


# --- the model ---
@pytest.mark.parametrize("how", ["timeout", "http"])
def test_a_model_that_fails_hands_over_to_the_next_one(corpus, tmp_path, monkeypatch, how):
    monkeypatch.setattr(tunables, "TALK_MODELS", "big,small")
    audio, client = Audio([Speech("what is PM Kisan")]), _Models({"big": how}, _say("It is for farmers."))
    _run(corpus, tmp_path, monkeypatch, audio, client, f"m_{how}")
    assert client.models == ["big", "small"] and audio.answers == ["It is for farmers."]


def test_no_new_model_is_tried_when_the_time_of_two_calls_is_used_up(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "TALK_MODELS", "a,b,c")
    monkeypatch.setattr(tunables, "TALK_TIMEOUT_S", 0.0)
    audio, client = Audio([Speech("what is PM Kisan")]), _Models({"a": "timeout", "b": "timeout"}, _say("x"))
    _run(corpus, tmp_path, monkeypatch, audio, client, "m_budget")
    assert client.models == ["a"] and " ".join(audio.answers) == prompt.NOT_SURE["en"]


# --- the voice ---
class _Mute(Audio):
    """The voice gives no sound for the first `fails` tries of a reply sentence."""

    def __init__(self, inputs, fails):
        super().__init__(inputs)
        self.fails, self.tries = fails, []

    def say_text(self, text):
        if text in prompt.HELLO["en"]:
            return super().say_text(text)
        self.tries.append(text)
        if self.fails > 0:
            self.fails -= 1
            return False
        return super().say_text(text)


def test_the_voice_is_tried_once_more(corpus, tmp_path, monkeypatch):
    audio = _Mute([Speech("what is PM Kisan")], fails=1)
    rows = _run(corpus, tmp_path, monkeypatch, audio, Client([_say("It is for farmers.")]), "v_once")
    assert audio.tries == ["It is for farmers."] * 2 and audio.answers == ["It is for farmers."]
    assert "unclear_prompt" not in audio.played
    assert not [r for r in rows if r.get("rule") == "voice_failed"]


def test_a_reply_with_no_voice_gets_a_recorded_line_not_silence(corpus, tmp_path, monkeypatch):
    audio = _Mute([Speech("what is PM Kisan"), Speech("how do I apply")], fails=2)
    rows = _run(corpus, tmp_path, monkeypatch, audio,
                Client([_say("It is for farmers."), _say("Go to the bank.")]), "v_line")
    assert audio.played.count("unclear_prompt") == 1
    assert [r["text"] for r in rows if r.get("rule") == "voice_failed"] == ["It is for farmers."]
    assert audio.answers == ["Go to the bank."]             # the talk goes on


def test_two_replies_in_a_row_with_no_voice_end_the_call(corpus, tmp_path, monkeypatch):
    audio = _Mute([Speech("what is PM Kisan"), Speech("how do I apply"), Speech("hello")], fails=99)
    client = Client([_say("It is for farmers."), _say("Go to the bank."), _say("Yes.")])
    _run(corpus, tmp_path, monkeypatch, audio, client, "v_down")
    assert len(client.calls) == 2 and audio.played[-1] == "closing_farewell" and audio.hung_up


# --- the cap ---
def test_the_call_says_goodbye_before_the_cap(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "CALL_CEILING_S", talk_mod.CAP_MARGIN_S)
    audio, client = Audio([Speech("what is PM Kisan")]), Client([_say("It is for farmers.")])
    _run(corpus, tmp_path, monkeypatch, audio, client, "cap")
    assert client.calls == [] and audio.played[-1] == "closing_farewell" and audio.hung_up


# --- the ear ---
def test_a_failed_speech_call_asks_the_caller_to_say_it_again(monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    phone, turn = _phone(monkeypatch, [(3.0, Noise()), (2.0, Speech("pm kisan"))])
    turn.ear = SimpleNamespace(failures=0)
    said, wait = [], turn.wait_input

    def failing(gap, profile="normal", lang=""):
        got = wait(gap, profile=profile, lang=lang)
        if isinstance(got, Noise):
            turn.ear.failures += 1
        return got

    turn.wait_input = failing
    phone.say = said.append
    assert isinstance(phone.next_input("spoken"), Speech)
    assert said == [("unclear_prompt",)]
    assert turn.gaps == [30.0, 30.0]                         # the wait starts again after the line


def test_a_cough_is_still_quiet(monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    phone, turn = _phone(monkeypatch, [(3.0, Noise()), Silence(n=1)])
    turn.ear = SimpleNamespace(failures=0)
    said = []
    phone.say = said.append
    assert phone.next_input("spoken") == Silence(n=1) and said == []


# --- faults of 1.3b in the talk loop ---
def test_a_wrong_type_from_the_model_does_not_break_the_turn(call):
    reply = {"action": "answer", "say": "It is for farmers.", "not": True, "just_tell": "false"}
    audio, _, rows = call([Speech("what is PM Kisan"), Speech("my crops died")],
                          [reply, dict(reply, **{"not": 5, "say": "It gives money."})])
    assert audio.answers[:1] == ["It is for farmers."] and len(audio.answers) >= 2


def test_just_tell_only_on_a_real_true(corpus, tmp_path):
    from tests.test_clarify_wire import _talk
    for value, want in (("false", False), (1, False), (True, True)):
        t = _talk(corpus, tmp_path, f"jt_{value}", Index())
        t.heard = ["what is PM Kisan"]
        t.model = SimpleNamespace(client=Client([{"action": "answer", "say": "It is for farmers.", "just_tell": value}]))
        t._decide("what is PM Kisan")
        assert t.just_tell is want


def test_every_ask_counts_and_one_is_given_back(corpus, tmp_path):
    """Bug A: the caller answers the last question and the model asks the next: both count."""
    from tests.test_clarify_wire import _talk
    t = _talk(corpus, tmp_path, "count", Index())
    t.asked, t.last_asked = {"category": 1}, "category"
    t.heard = ["farming"]
    nar, _ = t._state(t._found())
    t.bv["category"] = UNASKED
    ask = {"action": "ask", "say": "How old are you?", "ask_box": "", "facts": {"category": "farming"}}

    def reply(messages, task="", timeout=None, model=None):
        nxt, _ = t._state(t._found())
        return SimpleNamespace(success=True, data=dict(ask, ask_box=nxt.ask or ""))

    t.bv["category"] = "farming"
    nxt, _ = t._state(t._found())
    if not nxt.ask:
        pytest.skip("this snapshot has no second question for farming")
    t.bv["category"] = UNASKED
    t.model = SimpleNamespace(client=SimpleNamespace(call=lambda m, task="", timeout=None, model=None: SimpleNamespace(
        success=True, data=dict(ask, ask_box=nxt.ask))))
    action, _say_ = t._decide("farming")
    assert action == "ask" and t.asked == {"category": 1, nxt.ask: 1}


def test_an_answer_to_another_box_gives_the_ask_back():
    assert talk_mod._free_ask("age", {"state"}) and not talk_mod._free_ask("age", {"age"})


@pytest.mark.parametrize("words, who", [
    ("मेरी माँ के लिए पेंशन", "माँ"), ("for my mother", "mother"), ("माझ्या आईसाठी पेन्शन", "आई"),
    ("भाई मेरे लिए योजना बताओ", ""), ("bhai mere liye batao", ""), ("मुझे लोन चाहिए", ""),
])
def test_who_the_help_is_for(words, who):
    assert talk_words.other_person(words) == who


def test_the_same_person_named_again_does_not_wipe_the_age(corpus, tmp_path):
    from tests.test_clarify_wire import _talk
    t = _talk(corpus, tmp_path, "person", Index())
    t.model = SimpleNamespace(client=Client([{"action": "answer", "say": "Ok."}] * 2))
    t.heard = ["मेरी माँ के लिए पेंशन"]
    t._decide("मेरी माँ के लिए पेंशन")
    age = next(iter(corpus.values("age")))
    t.bv["age"] = age
    t.heard.append("हाँ माँ के लिए ही चाहिए")
    t._decide("हाँ माँ के लिए ही चाहिए")
    assert t.bv["age"] == age
