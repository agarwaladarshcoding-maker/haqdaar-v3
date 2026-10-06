"""Speech in the keys part's read-out (section menu) and at anything-else goes back to talk."""
from types import SimpleNamespace

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Noise, Speech
from haqdaar.data import log_text, scheme_index
from haqdaar.data.log import Log
from haqdaar.engine.call import Engine

from tests.test_step3_keys import KeysAudio, _modes
from tests.test_talk import Client, Index, _say, corpus  # noqa: F401  (corpus is a fixture)

NEED = {"category": "farming", "occupation": "farmer", "state": "maharashtra", "age": "36-59", "gender": "male"}


@pytest.fixture
def go(corpus, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(scheme_index, "get", lambda snapshot_id="CURRENT": Index())
    calls = []

    def run(inputs, replies, keys_in_talk=True):
        monkeypatch.setattr(tunables, "KEYS_IN_TALK", keys_in_talk)
        calls.append(1)
        audio, client = KeysAudio(inputs), Client(list(replies))
        log = Log.open(f"readout_test_{len(calls)}", corpus.snapshot_id, logs_dir=str(tmp_path))
        Engine.run_call(audio, SimpleNamespace(client=client, keypad_only=False), corpus, log)
        rows = log_text.read_rows(log.path)
        assert not [r for r in rows if r.get("invalid")]
        return audio, client, rows

    return run


def _start():
    return [Speech("I am a farmer in maharashtra"), Digit("6")]


def test_speech_at_the_section_menu_goes_to_talk(go):
    audio, client, rows = go(
        _start() + [Speech("how much money does it give"), Hangup()],
        [_say("Tell me more.", facts=NEED), _say("It gives money to families.")],
    )
    assert _modes(rows) == ["keys", "talk"]
    assert audio.profiles[-2:] == ["spoken", "spoken"] and "section_menu" in audio.played
    assert len(client.calls) == 2 and 'NEWEST CALLER WORDS: "how much money does it give"' in client.calls[1]
    assert audio.answers[-1] == "It gives money to families."
    assert audio.hung_up and rows[-1].get("stop") and len([r for r in rows if r.get("stop")]) == 1


def test_key_6_again_after_the_section_menu_says_the_scheme_block_again(go):
    audio, _, rows = go(
        _start() + [Speech("how much money does it give"), Digit("6"), Hangup()],
        [_say("Tell me more.", facts=NEED), _say("It gives money to families.")],
    )
    assert _modes(rows) == ["keys", "talk", "keys"]
    assert audio.played.count("section_menu") == 2 and audio.played.count("name:pm-kisan") == 2
    assert audio.played.index("section_menu") < len(audio.played) - 1


def test_speech_at_anything_else_goes_to_talk(go):
    audio, client, rows = go(
        _start() + [Digit("0"), Speech("how much money does it give"), Hangup()],
        [_say("Tell me more.", facts=NEED), _say("It gives money to families.")],
    )
    assert audio.played.count("anything_else") == 1 and audio.profiles[-2] == "spoken"
    assert _modes(rows) == ["keys", "talk"]
    assert audio.answers[-1] == "It gives money to families."
    assert audio.hung_up and len([r for r in rows if r.get("stop")]) == 1


def test_key_6_again_from_anything_else_asks_it_again(go):
    audio, _, rows = go(
        _start() + [Digit("0"), Speech("how much money does it give"), Digit("6"), Hangup()],
        [_say("Tell me more.", facts=NEED), _say("It gives money to families.")],
    )
    assert _modes(rows) == ["keys", "talk", "keys"]
    assert audio.played.count("anything_else") == 2


def test_one_word_or_noise_at_the_section_menu_is_as_before(go):
    audio, client, rows = go(
        _start() + [Speech("farming"), Noise(), Hangup()], [_say("Tell me more.", facts=NEED)],
    )
    assert _modes(rows) == ["keys"] and len(client.calls) == 1
    assert audio.played.count("unclear_prompt") == 2


class Plain(KeysAudio):
    """Keys from the greeting, no model client; key 1 at every question, then words at the section menu."""

    def __init__(self, inputs, greeting_six=False):
        super().__init__([], True)
        self.spoke = False

    def next_input(self, profile="normal"):
        self.profiles.append(profile)
        if "section_menu" in self.played:
            if not self.spoke:
                self.spoke = True
                return Speech("how much money does it give")
            return Hangup()
        return Digit("1")


def test_without_can_talk_the_read_out_is_as_before(corpus, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "KEYS_IN_TALK", True)
    audio = Plain([])
    log = Log.open("readout_plain", corpus.snapshot_id, logs_dir=str(tmp_path))
    Engine.run_call(audio, SimpleNamespace(client=None, keypad_only=False), corpus, log)
    rows = log_text.read_rows(log.path)
    assert audio.profiles[-2:] == ["readback", "readback"] and "spoken" not in audio.profiles[1:]
    assert "unclear_prompt" in audio.played
    assert _modes(rows) == ["keys"]
