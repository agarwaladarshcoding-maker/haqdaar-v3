"""Barge-in at any part: a fixed, repeatable sweep (owner, 4 Oct 2026).

Take a whole call as a list of caller inputs. For every position in that list (= every prompt
the call waits on) and for every kind of thing a caller can do there, put that one thing in
and let the call run on. No clock, no chance: the same run every time. Each run must hold the
rules at the bottom (`_check`).
"""
from __future__ import annotations

import json

import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.types import Answer, Digit, Hangup, Noise, Question, Repeat, Silence, Speech, Unclear
from haqdaar.data.log import Log
from haqdaar.engine.call import Engine

from tests.test_call import MockAudio, corpus  # noqa: F401  (corpus is a fixture)

MAX_WAITS = 200  # a call that asks the caller more often than this is stuck in a loop


class SweepAudio(MockAudio):
    """Plays the script, then presses 2 a few times, then hangs up. Counts every wait."""

    def __init__(self, inputs, said=True):
        super().__init__(inputs, "en")
        self.waits = 0
        self.answers: list[str] = []
        self._said = said

    def select_language(self):
        self.waits += 1
        return super().select_language()

    def next_input(self, profile="normal"):
        self.waits += 1
        if self.waits > MAX_WAITS:
            raise AssertionError("the call never ended")
        if self.inputs:
            item = self.inputs.pop(0)
            return Digit(digit=item) if isinstance(item, str) else item
        return Digit("2") if self.waits < 60 else Hangup()

    def say_text(self, text):
        self.answers.append(text)
        return self._said

    def pending_key(self):  # G7: a key that came while the router was thinking
        if self.inputs and isinstance(self.inputs[0], tuple):
            return self.inputs.pop(0)[1]
        return None


class SweepModel:
    """Sorts words by fixed rules, so a run is the same every time."""
    keypad_only = False

    def turn(self, transcript, box=None, ask_count=0):
        t = transcript.lower()
        if t.endswith("?"):
            return Question()
        if "again" in t:
            return Repeat()
        if "woman" in t and box == "gender":
            return Answer(box="gender", value="female", span="woman")
        return Unclear(reason="unclear")

    def opener(self, transcript, lang="en"):
        return Unclear(reason="unclear")

    def confirm(self, text, lang=None):
        t = text.lower().strip()
        return True if t == "yes" else False if t == "no" else None

    def sort(self, asked, transcript):
        return "QUESTION" if transcript.strip().endswith("?") else "OTHER"

    def answer(self, question, lang, cards, profile=None, scheme_ids=None, english=False):
        return None if "gold" in question else "It gives fifty percent subsidy."


# A whole call by keys: language, category, a few boxes, the results menu, anything else.
BASE_KEYS = [Digit("3"), Digit("1"), Digit("2"), Digit("1"), Digit("3"), Digit("1"), Digit("9"),
             Digit("1"), Digit("9"), Digit("9"), Digit("0"), Digit("2")]
# The same call with spoken turns in it.
BASE_SPOKEN = [Digit("3"), Digit("1"), Speech("I am a woman"), Speech("yes"), Digit("1"), Digit("3"),
               Digit("1"), Digit("9"), Digit("9"), Digit("0"), Speech("no")]

# Everything a caller can do at a prompt. A tuple ("then_key", Digit) is a key that arrives
# while the router is still working on the words before it (G7).
INJECT = {
    "valid_key": [Digit("1")],
    "wrong_key": [Digit("8")],
    "five_fast_same_keys": [Digit("1")] * 5,
    "keys_1_2_3_fast": [Digit("1"), Digit("2"), Digit("3")],
    "hash_repeat": [Digit("#")],
    "star_language": [Digit("*")],
    "zero": [Digit("0")],
    "nine": [Digit("9")],
    "silence": [Silence(n=1)],
    "silence_three_times": [Silence(n=1), Silence(n=2), Silence(n=3)],
    "noise": [Noise()],
    "hangup": [Hangup()],
    "spoken_answer": [Speech("I am a woman")],
    "spoken_question": [Speech("what does the tractor subsidy give?")],
    "question_with_no_answer": [Speech("what is the price of gold?")],
    "six_questions": [Speech("what does the tractor subsidy give?")] * 6,
    "skip_this_tell_me_about_that": [Speech("I do not want this, tell me about tractor subsidy?")],
    "say_it_again": [Speech("say that again")],
    "junk_words": [Speech("hello hello can you hear me")],
    "voice_cut_in_mid_clip": [Speech("what does the tractor subsidy give?", cut_clip="scheme:S1:summary", heard_ms=900)],
    "speech_then_key": [Speech("I am a woman"), ("then_key", Digit("2"))],
    "speech_then_hangup": [Speech("I am a woman"), Hangup()],
    "yes": [Speech("yes")],
    "no": [Speech("no")],
}

CASES = [
    (base_name, pos, name)
    for base_name, base in (("keys", BASE_KEYS), ("spoken", BASE_SPOKEN))
    for pos in range(len(base) + 1)
    for name in INJECT
]


def _check(lines: list[dict], audio: SweepAudio) -> None:
    # 1. The call ended, and it ended by itself: farewell or hangup, never a loop.
    assert audio.hung_up, "the line was not closed"
    assert audio.waits <= MAX_WAITS
    # 2. The log is closed on every path: the last row is the stop row.
    assert "stop" in lines[-1], f"log not closed: {lines[-1]}"
    assert sum(1 for l in lines if "stop" in l) == 1
    # 3. Questions: never more than the cap, each with an answer, and none moved the turn count.
    q = [l for l in lines if l.get("class") == "QUESTION"]
    assert len(q) <= tunables.QA_MAX_PER_CALL
    assert all(l.get("answer") for l in q) and len(audio.answers) >= len(q)
    # 4. Turn numbers never go backwards and never pass the cap.
    turns = [l["turn_n"] for l in lines if "turn_n" in l and "class" in l]
    assert turns == sorted(turns), f"turn numbers went back: {turns}"
    assert not turns or turns[-1] <= tunables.MAX_TURNS + 2
    # 5. No box holds two answers within one pass. ("Anything else? yes" starts a new pass,
    #    which begins with the category question again.)
    seen: set[str] = set()
    for l in lines:
        box = l.get("box")
        if l.get("class") != "ANSWER" or box in (None, "scheme"):
            continue
        if box == "category":
            seen = set()
        assert box not in seen, f"box {box} was answered twice in one pass"
        seen.add(box)


@pytest.mark.parametrize("qa", [False, True], ids=["qa_off", "qa_on"])
@pytest.mark.parametrize("base_name,pos,name", CASES, ids=[f"{b}-at{p}-{n}" for b, p, n in CASES])
def test_anything_at_any_point(corpus, tmp_path, monkeypatch, base_name, pos, name, qa):
    monkeypatch.setattr(tunables, "QA_ENABLED", qa)
    monkeypatch.setattr(tunables, "QA_SEARCH", qa)
    base = BASE_KEYS if base_name == "keys" else BASE_SPOKEN
    audio = SweepAudio(base[:pos] + INJECT[name] + base[pos:])
    log = Log.open("sweep", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, SweepModel(), corpus, log)
    _check([json.loads(l) for l in open(tmp_path / "sweep.jsonl")], audio)


def test_the_sweep_is_the_same_every_time(corpus, tmp_path):
    """Deterministic: two runs of one case give the same log, line for line."""
    def run(name):
        audio = SweepAudio(BASE_SPOKEN[:3] + INJECT["spoken_question"] + BASE_SPOKEN[3:])
        Engine.run_call(audio, SweepModel(), corpus, Log.open(name, corpus.snapshot_id, logs_dir=tmp_path))
        return [json.loads(l) for l in open(tmp_path / f"{name}.jsonl")][1:], audio.played
    assert run("a") == run("b")
