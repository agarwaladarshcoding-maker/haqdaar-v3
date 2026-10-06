"""Phase 3 (keys): keys and talk switch inside one call.

Key 6 in talk goes to keys with the answers so far; key 6 at the greeting starts in keys; words in the
keys part go back to talk with the key answers kept; three questions with no usable reply offer keys;
greeting keys 1-5 follow the five-language greeting. With TALK_ONLY off nothing changes.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from haqdaar.audio.turn import Turn
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Noise, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.log import Log
from haqdaar.engine.call import Engine
from haqdaar.prompts import talk as prompt

from tests.test_talk import Audio, Client, Index, _say, corpus  # noqa: F401  (corpus is a fixture)


class KeysAudio(Audio):
    """Records the profile of each wait. `greeting_six`: the caller presses 6 at the greeting."""

    def __init__(self, inputs, greeting_six=False):
        super().__init__(inputs)
        self.greeting_six, self.profiles = greeting_six, []

    def select_language(self):
        if not self.greeting_six:
            return super().select_language()
        self.played.append("greeting_trilingual")
        self.inputs.pop(0)                      # the language key Audio puts first
        return Digit("6")

    def next_input(self, profile="normal"):
        self.profiles.append(profile)
        return super().next_input(profile)


class AskClient(Client):
    """Asks the picker's box while the caller says "not sure" or "do not know"; otherwise a short answer."""

    def call(self, messages, task="", timeout=None, model=None):
        content = messages[1]["content"]
        words = re.search(r'NEWEST CALLER WORDS: "(.*)"', content).group(1).lower()
        box = re.search(r"NEXT QUESTION: (\w+)", content).group(1)
        n = len(self.calls) + 1
        if ("not sure" in words or "know" in words) and box != "none":
            self.replies = [{"action": "ask", "say": f"Could you tell me more, number {'x' * n}?", "ask_box": box,
                             "facts": {}}]
        else:
            self.replies = [_say(f"Here is a short answer {'y' * n}.")]
        return super().call(messages, task, timeout, model)


@pytest.fixture
def go(corpus, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "KEYS_IN_TALK", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())
    calls = []

    def run(inputs, replies=(), greeting_six=False, client=None, audio=KeysAudio):
        calls.append(1)
        audio = audio(inputs, greeting_six)
        client = client or Client(list(replies))
        log = Log.open(f"keys_test_{len(calls)}", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
        rows = log_text.read_rows(log.path)
        assert not [r for r in rows if r.get("invalid")]
        return audio, client, rows

    return run


def _modes(rows):
    return [r["to"] for r in rows if r.get("ev") == "mode"]


def _answers(rows):
    return [(r["box"], r["value"]) for r in rows if r.get("class") == "ANSWER" and r.get("box")]


def _keypad_boxes(audio):
    return {t[len("keypad_"):] for t in audio.played if t.startswith("keypad_") and t != "keypad_only_mode"}


def test_key_6_in_talk_hands_over_with_the_answers_kept_and_the_call_open(go):
    audio, _, rows = go(
        [Speech("I am a worker, a woman"), Digit("6"), Digit("0"), Hangup()],
        [_say("Tell me more.", facts={"occupation": "worker", "gender": "female"})],
    )
    assert [r["means"] for r in rows if r.get("ev") == "key" and r["key"] == "6"] == ["go to keys"]
    assert _modes(rows) == ["keys"]
    assert "closing_farewell" not in audio.played             # talk did not say goodbye or hang up at the key
    assert audio.played.count("opener_prompt") == 1            # the need was not answered in talk: asked by key
    assert _keypad_boxes(audio) == {"age"}                     # occupation and gender are known: never asked again
    assert ("occupation", "worker") in _answers(rows) and rows[-1].get("stop")


def test_key_6_at_the_greeting_starts_in_keys(go):
    audio, client, rows = go([Digit("0"), Hangup()], greeting_six=True)
    assert client.calls == [] and audio.language == "hi"
    assert [r["means"] for r in rows if r.get("ev") == "key"][:1] == ["go to keys"]
    assert _modes(rows) == ["keys"]
    assert next(r for r in rows if r.get("lang_source"))["lang_source"] == "default"
    assert "opener_prompt" in audio.played and audio.profiles[0] == "spoken"
    assert [b for b, _ in _answers(rows)][:1] == ["category"]  # the key answered the opener


def test_speech_in_keys_goes_back_to_talk_with_the_key_answers_kept(go):
    audio, client, rows = go(
        [Digit("0"), Speech("how much money does it give"), Hangup()],
        [_say("It gives money to families.")], greeting_six=True,
    )
    assert _modes(rows) == ["keys", "talk"]
    assert "category = UNKNOWN" in client.calls[0]             # a key answer, UNKNOWN too, stays
    assert 'NEWEST CALLER WORDS: "how much money does it give"' in client.calls[0]
    assert audio.answers == ["It gives money to families."] and audio.hello == 0   # turn 1, no second hello
    assert audio.hung_up and rows[-1].get("stop")


def test_one_word_or_noise_in_keys_does_not_switch(go):
    audio, client, rows = go([Digit("0"), Speech("farming"), Noise(), Digit("1"), Hangup()], greeting_six=True)
    assert client.calls == [] and _modes(rows) == ["keys"]


def test_talk_to_keys_to_talk_twice_keeps_every_answer(go):
    audio, client, rows = go(
        [Speech("I am a worker"), Digit("6"), Digit("0"), Speech("how much money does it give"),
         Digit("6"), Digit("3"), Speech("which papers are needed"), Hangup()],
        [_say("Tell me more.", facts={"occupation": "worker"}),
         _say("It gives money to families."), _say("You need an Aadhaar card.")],
    )
    assert _modes(rows) == ["keys", "talk", "keys", "talk"]
    assert [r["key"] for r in rows if r.get("ev") == "key" and r.get("means") == "go to keys"] == ["6", "6"]
    assert "category = UNKNOWN" in client.calls[1] and "occupation = worker" in client.calls[1]
    assert "category = UNKNOWN" in client.calls[2] and "gender = other" in client.calls[2]   # keys answers of both rounds
    assert "occupation = worker" in client.calls[2]                                       # and the talk's fact
    assert len(audio.answers) == 3 and rows[-1].get("stop")


def test_the_keys_offer_is_said_once_after_three_questions_with_no_reply(go):
    said = ["I am not sure what I need"] + ["I do not know"] * 4
    audio, _, rows = go([Speech(w) for w in said], client=AskClient([]))
    offers = [r for r in rows if r.get("ev") == "act" and r.get("action") == "keys_offer"]
    assert len(offers) == 1
    said_text = " ".join(audio.answers)
    assert prompt.KEYS_OFFER["en"].split(". ")[1] in said_text
    asks = [r for r in rows if r.get("ev") == "act" and r.get("action") == "ask"]
    assert len(asks) == 3 and rows.index(offers[0]) > rows.index(asks[2])    # after the third question's reply


def test_no_keys_offer_when_keys_in_talk_is_off(go, monkeypatch):
    monkeypatch.setattr(tunables, "KEYS_IN_TALK", False)
    said = ["I am not sure what I need"] + ["I do not know"] * 4
    audio, _, rows = go([Speech(w) for w in said], client=AskClient([]))
    assert not [r for r in rows if r.get("action") == "keys_offer"]
    assert "Press 6" not in " ".join(audio.answers)


def test_greeting_keys_follow_the_five_language_greeting(monkeypatch):
    monkeypatch.setattr(tunables, "LANGS_OFFERED", ("hi", "en"))
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "GREETING_FIVE", True)
    assert tunables.turn0_keys() == {"1": "hi", "2": "en", "3": "mr", "4": "gu", "5": "ta"}
    monkeypatch.setattr(tunables, "GREETING_FIVE", False)
    assert tunables.turn0_keys() == {"1": "hi", "2": "en"}
    monkeypatch.setattr(tunables, "GREETING_FIVE", True)
    monkeypatch.setattr(tunables, "TALK_ONLY", False)
    assert tunables.turn0_keys() == {"1": "hi", "2": "en"}


def test_a_gujarati_key_at_the_greeting_is_taken(go):
    class GujaratiAudio(KeysAudio):
        def select_language(self):
            self.inputs.pop(0)
            self.language = "gu"
            return "gu", "keypad"

    audio, _, rows = go([Speech("what is PM Kisan"), Hangup()], [_say("It is for farmers.")], audio=GujaratiAudio)
    langs = [r for r in rows if r.get("lang_source")]
    assert langs[-1]["lang"] == "gu" and langs[-1]["lang_source"] == "keypad"
    assert [r["means"] for r in rows if r.get("ev") == "key"][:1] == ["language = gu"]
    assert audio.answers and rows[-1].get("stop")


def test_talk_ignores_key_6_and_nothing_in_keys_mode(monkeypatch):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "PHOTO_IN_CALL", True)
    monkeypatch.setattr(tunables, "KEYS_IN_TALK", True)
    turn = Turn(SimpleNamespace())
    assert not turn._talk_ignores("6", "answer") and not turn._talk_ignores("9", "answer")
    assert turn._talk_ignores("5", "answer")
    turn.keys_mode = True
    assert not turn._talk_ignores("5", "keypad_age")
    turn.keys_mode = False
    monkeypatch.setattr(tunables, "KEYS_IN_TALK", False)
    assert turn._talk_ignores("6", "answer")


def test_with_talk_only_off_key_6_is_a_plain_key(corpus, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tunables, "TALK_ONLY", False)
    monkeypatch.setattr(tunables, "KEYS_IN_TALK", True)       # only the call's own switch matters
    audio = KeysAudio([Hangup()], greeting_six=True)
    log = Log.open("keys_off", corpus.snapshot_id, logs_dir=str(tmp_path))
    Engine.run_call(audio, None, corpus, log)
    rows = log_text.read_rows(log.path)
    assert [r["means"] for r in rows if r.get("ev") == "key"][:3] == ["not on the menu"] * 3
    assert not _modes(rows) and not [r for r in rows if r.get("means") == "go to keys"]
    assert audio.profiles[0] == "normal" and "spoken" not in audio.profiles
