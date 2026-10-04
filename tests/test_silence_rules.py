"""T1 (step 7.11): the silence rule and the unclear rule, on the engine with fake callers.

Total quiet: a reminder after the first long wait, goodbye after the second, at every stage.
Noise is not a reply: the real line drops it. Unclear words: three tries, then the key list. A clear answer or an answered
question starts the count again. (The 30 s and 60 s on a clock are in tests/test_barge_eval.py.)
"""
from __future__ import annotations

import pytest

from haqdaar.audio import phone as phone_mod
from haqdaar.audio.phone import PhoneAudio
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Noise, Silence, Speech
from haqdaar.data.log import Log
from haqdaar.engine.call import Engine, _door_a_pick

from tests.test_barge_sweep import (
    BASE_KEYS, SweepModel, WaitRecorder, _kind, _reprompt_is_right,
)
from tests.test_call import corpus  # noqa: F401  (corpus is a fixture)

JUNK = Speech("hello hello can you hear me")
QUESTION = Speech("what does the tractor subsidy give?")


def _run(corpus, tmp_path, name, script):
    audio = WaitRecorder(script)
    Engine.run_call(audio, SweepModel(), corpus, Log.open(name, corpus.snapshot_id, logs_dir=tmp_path))
    return audio


# the six places that wait on the caller, as a script that ends in total quiet there
SITES = {
    "opener": ([Digit("3")], "opener"),
    "question": ([Digit("3"), Digit("1"), Digit("2")], "box"),
    "confirm": ([Digit("3"), Digit("1"), Digit("2"), Speech("I am a woman")], "confirm"),
    "readback": (BASE_KEYS[:5], "readback"),
    "anything_else": (BASE_KEYS[:10], "anything_else"),
}


@pytest.mark.parametrize("site", list(SITES))
def test_total_quiet_reminds_once_then_says_goodbye(corpus, tmp_path, site):
    script, kind = SITES[site]
    audio = _run(corpus, tmp_path, f"quiet_{site}", script + [Silence(n=1), Silence(n=2)])
    assert audio.hung_up and audio.played[-1] == "closing_farewell"
    assert audio.silent_waits == 2
    assert audio.played.count("waiting_for_reply") == 1
    prompt, said, _ = audio.reprompts[0]
    assert _kind(prompt) == kind and _reprompt_is_right(prompt, said)


@pytest.mark.parametrize("site", list(SITES))
def test_a_reply_after_the_reminder_carries_on(corpus, tmp_path, site):
    script, _ = SITES[site]
    audio = _run(corpus, tmp_path, f"carry_{site}", script + [Silence(n=1), Digit("2")])
    assert audio.played.count("waiting_for_reply") == 1
    assert audio.played.count("closing_farewell") == 1   # only the real end of the call


# These two engine tests still hold: mock audios and the simulators still send Noise to the engine.
# At anything-else a noise already means "no" and ends the call (not changed here), so it is not tried.
@pytest.mark.parametrize("site", [k for k in SITES if k != "anything_else"])
def test_noise_between_two_quiets_does_not_end_the_call(corpus, tmp_path, site):
    """The engine, given a Noise between two quiets, does not hang up at the second quiet."""
    script, _ = SITES[site]
    audio = _run(corpus, tmp_path, f"noise_{site}", script + [Silence(n=1), Noise(), Silence(n=1), Digit("2")])
    assert audio.played.count("waiting_for_reply") == 2
    assert audio.played.count("closing_farewell") == 1


def test_total_quiet_at_the_language_pick_replays_only_the_greeting(corpus, tmp_path):
    class Turn0(WaitRecorder):
        def select_language(self):
            self.played.append("greeting_trilingual")
            return self.inputs.pop(0) if self.inputs else Silence(n=2)

    audio = Turn0([Silence(n=1), Silence(n=2)])
    Engine.run_call(audio, SweepModel(), corpus, Log.open("t0_quiet", corpus.snapshot_id, logs_dir=tmp_path))
    assert audio.played == ["greeting_trilingual", "greeting_trilingual", "closing_farewell"]


def test_total_quiet_at_the_two_name_pick(corpus, tmp_path):
    log = Log.open("pick_quiet", corpus.snapshot_id, logs_dir=tmp_path)
    audio = WaitRecorder([Silence(n=1), Silence(n=2)])
    assert _door_a_pick(audio, log, 1, "S1", "S2") == "hangup"
    assert audio.played.count("waiting_for_reply") == 1 and audio.played[-1] == "closing_farewell"
    audio = WaitRecorder([Silence(n=1), Digit("1")])
    assert _door_a_pick(audio, log, 1, "S1", "S2") == "1"


# --- the phone side: a noise is not a reply, the wait goes on for the time left ----------------


class _Clock:
    """A clock that only moves when the fake turn waits."""
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t


class _FakeTurn:
    """Each item is (seconds into the wait, input), or Silence for a full quiet wait. Keeps how
    long the phone was told to wait each time."""
    keypad_only = False

    def __init__(self, clock, inputs):
        self.clock, self.inputs, self.gaps = clock, list(inputs), []

    def wait_input(self, gap, profile="normal", lang=""):
        self.gaps.append(gap)
        item = self.inputs.pop(0)
        if isinstance(item, tuple):
            after, item = item
            self.clock.t += min(after, gap)
            return item
        self.clock.t += gap
        return item


def _phone(monkeypatch, inputs):
    clock = _Clock()
    monkeypatch.setattr(phone_mod, "time", clock)
    turn = _FakeTurn(clock, inputs)
    return PhoneAudio(None, None, None, turn, lambda: None), turn


def test_a_noise_does_not_reset_the_count_and_the_wait_goes_on_for_the_time_left(monkeypatch):
    # a cough 10 s into the first wait, then quiet; another 5 s into the second wait, then quiet
    phone, turn = _phone(monkeypatch, [(10.0, Noise()), Silence(n=1), (5.0, Noise()), Silence(n=1)])
    got = [phone.next_input("spoken") for _ in range(2)]
    assert [g.n for g in got] == [1, 2]                      # the count goes 1 then 2, never reset
    assert all(isinstance(g, Silence) for g in got)          # no Noise reaches the engine
    assert turn.gaps == [30.0, 20.0, 30.0, 25.0]             # 30 s in all, 30 s in all


def test_a_noise_at_the_language_pick_is_quiet_not_a_reply(monkeypatch):
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", True)
    phone, turn = _phone(monkeypatch, [(10.0, Noise()), Silence(n=1), (4.0, Noise()), Silence(n=1)])
    phone.say = lambda sequence: None
    got = [phone.select_language() for _ in range(2)]
    assert got == [Silence(n=1), Silence(n=2)]
    assert turn.gaps == [30.0, 20.0, 30.0, 26.0]


def test_words_after_a_noise_still_reset_the_count(monkeypatch):
    phone, _ = _phone(monkeypatch, [Silence(n=1), (10.0, Noise()), (5.0, Speech("hello"))])
    assert phone.next_input("spoken").n == 1
    assert isinstance(phone.next_input("spoken"), Speech)
    assert phone._silence == 0


def test_a_noise_that_runs_past_the_gap_ends_the_wait(monkeypatch):
    phone, turn = _phone(monkeypatch, [(40.0, Noise())])      # an utterance in progress at the gap end
    assert phone.next_input("spoken") == Silence(n=1)
    assert len(turn.gaps) == 1


# --- unclear words: three tries, then the key list -------------------------------------------


def test_three_unclear_answers_at_a_question_bring_the_keys(corpus, tmp_path):
    audio = _run(corpus, tmp_path, "unclear_q", [Digit("3"), Digit("1"), Digit("2"), JUNK, JUNK, JUNK] + BASE_KEYS[3:])
    asked = [t for o in audio.opening for t in o if t.endswith("_gender")]
    assert asked[:4] == ["q_gender", "rephrase_gender", "rephrase_gender", "keypad_gender"]


def test_two_unclear_answers_do_not_bring_the_keys(corpus, tmp_path):
    audio = _run(corpus, tmp_path, "unclear_q2", [Digit("3"), Digit("1"), Digit("2"), JUNK, JUNK, Speech("I am a woman"),
                                                  Speech("yes")] + BASE_KEYS[4:])
    assert "keypad_gender" not in audio.played and "rephrase_gender" in audio.played


def test_unclear_then_a_question_answered_starts_the_count_again(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "QA_ENABLED", True)
    monkeypatch.setattr(tunables, "QA_SEARCH", True)
    # at a question: 1 miss, a question that is answered, 2 more misses: three in all but not in a row
    script = [Digit("3"), Digit("1"), Digit("2"), JUNK, QUESTION, JUNK, JUNK, Speech("I am a woman"), Speech("yes")]
    audio = _run(corpus, tmp_path, "reset_q", script + BASE_KEYS[4:])
    assert "keypad_gender" not in audio.played
    # at the opener: the same
    audio = _run(corpus, tmp_path, "reset_open", [Digit("3"), JUNK, QUESTION, JUNK, JUNK] + BASE_KEYS[1:])
    assert "opener_prompt" not in audio.played


def test_silence_does_not_count_as_an_unclear_answer(corpus, tmp_path):
    audio = _run(corpus, tmp_path, "silent_not_unclear", [Digit("3"), Digit("1"), Digit("2"), JUNK, Silence(n=1), JUNK]
                 + [Speech("I am a woman"), Speech("yes")] + BASE_KEYS[4:])
    assert "keypad_gender" not in audio.played


def test_a_quiet_caller_at_the_opener_hears_the_key_list_once_before_the_goodbye(corpus, tmp_path):
    audio = _run(corpus, tmp_path, "quiet_list", [Digit("3"), Silence(n=1), Silence(n=2)])
    assert audio.hung_up and audio.played[-1] == "closing_farewell"
    assert audio.played.count("opener_short_prompt") == 1
    assert audio.played.count("opener_prompt") == 1          # the line that brings the key list
    assert audio.played.index("waiting_for_reply") < audio.played.index("opener_prompt")
