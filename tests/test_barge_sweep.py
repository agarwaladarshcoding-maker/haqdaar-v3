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
from haqdaar.audio.lines import load_lines
from haqdaar.audio.ear import SttResult
from haqdaar.engine.call import Engine, _door_a_pick

from tests.test_call import MockAudio, corpus  # noqa: F401  (corpus is a fixture)
from tests.test_live_speech import FakeSTT as _LiveFakeSTT, Line as _LiveLine, _NoPool as _LiveNoPool, _later

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


class CutTrackingAudio(SweepAudio):
    """Fails if next_input is called after a cut without speech in between."""

    def __init__(self, inputs, said=True):
        super().__init__(inputs, said=said)
        self.cut_pending = False
        self.cuts_seen = 0

    def select_language(self):
        self.waits += 1
        if self.inputs and getattr(self.inputs[0], "cut_clip", ""):
            self.cut_pending = True
            self.cuts_seen += 1
        return super().select_language()

    def next_input(self, profile="normal"):
        if self.cut_pending:
            raise AssertionError("Engine listened again without speaking after a cut")
        inp = super().next_input(profile=profile)
        if getattr(inp, "cut_clip", ""):
            self.cut_pending = True
            self.cuts_seen += 1
        return inp

    def say(self, sequence):
        if sequence:
            self.cut_pending = False
        super().say(sequence)

    def say_text(self, text):
        if text:
            self.cut_pending = False
        return super().say_text(text)

    def repeat(self):
        self.cut_pending = False
        super().repeat()


CUT_INJECT = {
    "voice_cut_question": [Speech("what does the tractor subsidy give?", cut_clip="scheme:S1:summary", heard_ms=900)],
    "voice_cut_unanswerable": [Speech("what is the price of gold?", cut_clip="scheme:S1:summary", heard_ms=900)],
    "voice_cut_junk": [Speech("hello hello can you hear me", cut_clip="scheme:S1:summary", heard_ms=900)],
    "voice_cut_answer": [Speech("I am a woman", cut_clip="q_gender", heard_ms=400)],
    "key_cut_valid": [Digit("1", cut_clip="scheme:S1:summary", heard_ms=500)],
    "key_cut_wrong": [Digit("8", cut_clip="scheme:S1:summary", heard_ms=500)],
    "key_cut_zero": [Digit("0", cut_clip="scheme:S1:summary", heard_ms=500)],
    "key_cut_nine": [Digit("9", cut_clip="scheme:S1:summary", heard_ms=500)],
}

# The call ends on the base's last two inputs, so a cut put at or after them is never played;
# those positions would pass without checking anything, so they are left out.
CUT_CASES = [
    (base_name, pos, name)
    for base_name, base in (("keys", BASE_KEYS), ("spoken", BASE_SPOKEN))
    for pos in range(len(base) - 1)
    for name in CUT_INJECT
]


@pytest.mark.parametrize("qa", [False, True], ids=["qa_off", "qa_on"])
@pytest.mark.parametrize("base_name,pos,name", CUT_CASES, ids=[f"cut-{b}-at{p}-{n}" for b, p, n in CUT_CASES])
def test_cut_is_always_answered(corpus, tmp_path, monkeypatch, base_name, pos, name, qa):
    monkeypatch.setattr(tunables, "QA_ENABLED", qa)
    monkeypatch.setattr(tunables, "QA_SEARCH", qa)
    base = BASE_KEYS if base_name == "keys" else BASE_SPOKEN
    audio = CutTrackingAudio(base[:pos] + CUT_INJECT[name] + base[pos:])
    log = Log.open("cut_sweep", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio, SweepModel(), corpus, log)
    assert audio.cuts_seen, "the call ended before the cut was played, so nothing was checked"
    assert not audio.cut_pending, "Call ended without speaking after cut"
    _check([json.loads(l) for l in open(tmp_path / "cut_sweep.jsonl")], audio)


class OneSchemeTrackingAudio(SweepAudio):
    """Tracks readback waits and verifies current_scheme equals the scheme last heard."""

    def __init__(self, inputs, said=True):
        super().__init__(inputs, said=said)
        self.readback_waits: list[dict[str, Any]] = []

    def next_input(self, profile="normal"):
        if profile == "readback":
            last_heard = None
            for token in reversed(self.played):
                if token.startswith("name:"):
                    last_heard = token.split(":", 1)[1]
                    break
                elif token.startswith("end:"):
                    last_heard = token.split(":", 1)[1]
                    break
            cur = getattr(Engine, "current_scheme", None)
            assert cur is not None, "Engine.current_scheme is None during readback wait"
            assert cur == last_heard, (
                f"current_scheme ({cur}) != last_heard ({last_heard}) at wait {len(self.readback_waits) + 1}"
            )
            self.readback_waits.append({
                "wait_n": len(self.readback_waits) + 1,
                "current_scheme": cur,
                "last_heard": last_heard,
            })
        return super().next_input(profile=profile)


def test_one_scheme_at_a_time(corpus, tmp_path, monkeypatch):
    """7.2 sweep lock: N matching schemes produce N separate waits, and
    current-scheme always equals the scheme last heard."""
    monkeypatch.setattr(tunables, "QA_ENABLED", True)
    monkeypatch.setattr(tunables, "QA_SEARCH", True)

    # 1. Keypad walk: 2 matching schemes produce 2 separate waits, each matching current-scheme
    inputs_keys = [
        Digit("3"), Digit("1"), Digit("2"), Digit("1"), Digit("3"),
        Digit("9"), Digit("9"), Digit("0"), Digit("2"),
    ]
    audio1 = OneSchemeTrackingAudio(inputs_keys)
    log1 = Log.open("one_at_a_time_keys", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio1, SweepModel(), corpus, log1)
    _check([json.loads(l) for l in open(tmp_path / "one_at_a_time_keys.jsonl")], audio1)

    assert len(audio1.readback_waits) == 2, f"Expected 2 separate waits for 2 schemes, got {len(audio1.readback_waits)}"
    assert [w["current_scheme"] for w in audio1.readback_waits] == ["S1", "S2"]
    assert all(w["current_scheme"] == w["last_heard"] for w in audio1.readback_waits)

    # 2. Spoken questions at readback: "this scheme" resolves to current scheme,
    # and a named scheme jumps to that scheme.
    class QAInspectModel(SweepModel):
        def __init__(self):
            super().__init__()
            self.answered_schemes: list[list[str]] = []

        def answer(self, question, lang, cards, profile=None, scheme_ids=None, english=False):
            self.answered_schemes.append(list(scheme_ids or []))
            return "Fifty percent subsidy."

    inputs_qa = [
        Digit("3"), Digit("1"), Digit("2"), Digit("1"), Digit("3"),
        # At S1: ask about "this scheme" -> answered from S1
        Speech("what does this scheme give?"),
        # Advance to S2
        Digit("9"),
        # At S2: ask about "this scheme" -> answered from S2
        Speech("what does this scheme give?"),
        # At S2: ask about S1 by name -> jumps to S1
        Speech("what does kisan credit give?"),
        # Finish call
        Digit("9"), Digit("0"), Digit("2"),
    ]
    model2 = QAInspectModel()
    audio2 = OneSchemeTrackingAudio(inputs_qa)
    log2 = Log.open("one_at_a_time_qa", corpus.snapshot_id, logs_dir=tmp_path)
    Engine.run_call(audio2, model2, corpus, log2)
    _check([json.loads(l) for l in open(tmp_path / "one_at_a_time_qa.jsonl")], audio2)

    # All readback waits had current_scheme == last_heard
    assert all(w["current_scheme"] == w["last_heard"] for w in audio2.readback_waits)
    # The two schemes S1 and S2 were heard in order
    schemes_heard = [w["current_scheme"] for w in audio2.readback_waits]
    assert "S1" in schemes_heard and "S2" in schemes_heard
    # Question 1 (on S1) answered about S1
    assert model2.answered_schemes[0] == ["S1"]
    # Question 2 (on S2) answered about S2
    assert model2.answered_schemes[1] == ["S2"]
    # Question 3 (on S2, named tractor subsidy) jumped to S1
    assert model2.answered_schemes[2] == ["S1"]


# --- 7.3 talk-first opener and the one silence rule -------------------------------------------

class WaitRecorder(SweepAudio):
    """Keeps what was said between waits, and checks what follows each silent wait."""

    def __init__(self, inputs, said=True):
        super().__init__(inputs, said=said)
        self.said: list[tuple[str, ...]] = []      # say() calls since the last wait
        self.opening: list[tuple[str, ...]] = []   # say() calls before each wait, in order
        self.prompt: tuple[str, ...] = ()          # the last thing said before the wait now open
        self.after_silence = None                  # (prompt, language) of a silent wait not yet answered
        self.silent_waits = 0
        self.reprompts: list[tuple[tuple[str, ...], tuple[str, ...], str]] = []  # (prompt, said after, lang)

    def say(self, sequence):
        self.said.append(tuple(sequence))
        super().say(sequence)

    def next_input(self, profile="normal"):
        if self.after_silence is not None:
            flat = tuple(t for call in self.said for t in call)
            self.reprompts.append((self.after_silence[0], flat, self.after_silence[1]))
            self.after_silence = None
        self.opening.append(tuple(t for call in self.said for t in call))
        if self.said:
            self.prompt = self.said[-1]
        self.said = []
        inp = super().next_input(profile=profile)
        if isinstance(inp, Silence):
            self.silent_waits += 1
            self.after_silence = (self.prompt, self.language)
        return inp


def _lines(tmp_path, name):
    return [json.loads(l) for l in open(tmp_path / f"{name}.jsonl")]


def test_talk_first_opener(corpus, tmp_path):
    """7.3: the opener is one short line. The list plays only on key 0 or after two misses; a
    key 1-9 pressed at once still answers. Keys stay a full second way in."""
    def run(name, script, model=None):
        audio = WaitRecorder(script)
        log = Log.open(name, corpus.snapshot_id, logs_dir=tmp_path)
        Engine.run_call(audio, model or SweepModel(), corpus, log)
        _check(_lines(tmp_path, name), audio)
        return audio, _lines(tmp_path, name)

    junk = Speech("hello hello can you hear me")
    rest = BASE_KEYS[1:]  # category key 1, then the rest of a whole keypad call

    # A fresh call: the first wait follows exactly one line, and the list is never played.
    audio, lines = run("direct", [Digit("3")] + rest)
    assert audio.opening[0] == ("opener_short_prompt",)  # the language is chosen before any wait
    assert "opener_prompt" not in audio.played
    assert any(l.get("class") == "ANSWER" and l.get("box") == "category" and l.get("transcript") == "1"
               for l in lines), "a key pressed at once at the short line must still answer"

    # Key 0 plays the list (the opener question and its choices) and is not "don't know".
    audio, lines = run("zero", [Digit("3"), Digit("0")] + rest)
    assert audio.opening[0] == ("opener_short_prompt",)
    assert audio.opening[1] == ("opener_prompt",)
    assert not any(l.get("box") == "category" and l.get("value") == "unknown" for l in lines)
    assert {"mode": "voice", "opener_menu": "key_0", "opener_misses": 0} in lines
    assert any(l.get("class") == "ANSWER" and l.get("box") == "category" and l.get("transcript") == "1"
               for l in lines)

    # Two misses, whether silence or words we cannot use, bring the list. Not before.
    for name, misses in (("silent", [Silence(n=1), Silence(n=2)]), ("junk", [junk, junk]),
                         ("mixed", [junk, Silence(n=1)])):
        audio, lines = run(f"misses_{name}", [Digit("3")] + misses + rest)
        said = audio.opening[:3]
        assert "opener_prompt" not in said[0] and "opener_prompt" not in said[1], name
        assert said[0] == ("opener_short_prompt",), name
        assert "opener_short_prompt" in said[1], name  # one miss: still the short line
        assert "opener_prompt" in said[2], name       # two misses: the list
        assert {"mode": "voice", "opener_menu": "two_misses", "opener_misses": 2} in lines, name
        assert any(l.get("class") == "ANSWER" and l.get("box") == "category" for l in lines), name

    # One miss alone does not bring the list.
    audio, lines = run("one_miss", [Digit("3"), junk] + rest)
    assert "opener_prompt" not in audio.played


def _reprompt_is_right(prompt, said):
    """After a silent wait: the no-reply line (after "I am still here" on the second), then the
    live prompt again. The short opener line grows into the list on the second miss."""
    said = said[1:] if said[:1] == ("silence_presence",) else said
    if said[:1] != ("did_not_get_reply",) or len(said) < 2:
        return False
    again = said[1:]
    return set(again) <= set(prompt) or (prompt == ("opener_short_prompt",) and again == ("opener_prompt",))


def _kind(prompt):
    if prompt[:1] in (("opener_short_prompt",), ("opener_prompt",)):
        return "opener"
    if prompt[0].startswith(("q_", "rephrase_", "keypad_", "state_q")):
        return "box"
    if prompt[0] == "bundle_confirm_intro":
        return "confirm"
    if prompt == ("anything_else",):
        return "anything_else"
    return "readback" if "section_menu" in prompt else "other"


class GoneCaller(SweepAudio):
    """Plays the script, then never says or presses anything: Silence with the ladder count a
    real line would give (it grows on each silent wait and resets on a key)."""

    def __init__(self, inputs):
        super().__init__(inputs)
        self.silent_run = 0

    def select_language(self):
        self.silent_run = 0
        return super().select_language()

    def next_input(self, profile="normal"):
        if not self.inputs:
            self.waits += 1
            self.silent_run += 1
            if self.waits > MAX_WAITS:
                raise AssertionError("the call never ended")
            return Silence(n=self.silent_run)
        self.silent_run = 0
        return super().next_input(profile=profile)


def test_language_prompt_wrong_keys(corpus, tmp_path):
    """Three wrong keys at the language prompt fall back to Hindi (lang_source default);
    one or two replay the greeting."""
    class Turn0Keys(SweepAudio):
        def select_language(self):
            self.played.append("greeting_trilingual")
            return self.inputs.pop(0) if self.inputs else Hangup()

    def run(name, script):
        audio = Turn0Keys(script)
        Engine.run_call(audio, SweepModel(), corpus, Log.open(name, corpus.snapshot_id, logs_dir=tmp_path))
        picked = [l for l in _lines(tmp_path, name) if "lang_source" in l and "call_id" not in l]
        return audio, picked

    audio, picked = run("wrong3", [Digit("8"), Digit("8"), Digit("8")] + BASE_KEYS[1:])
    assert audio.played[:3] == ["greeting_trilingual"] * 3
    assert audio.language == "hi" and picked and picked[0]["lang_source"] == "default"

    audio, picked = run("wrong2", [Digit("8"), Digit("8"), ("en", "keypad")] + BASE_KEYS[1:])
    assert audio.played[:3] == ["greeting_trilingual"] * 3
    assert audio.language == "en" and picked and picked[0]["lang_source"] == "keypad"


@pytest.mark.parametrize("lang,key", [("en", "3"), ("hi", "1"), ("mr", "2")])
def test_silence_always_reprompts(corpus, tmp_path, monkeypatch, lang, key):
    """7.3: every wait that hears nothing says the no-reply line, then asks again, in the
    caller's language; and a caller who stays silent is let go by the ladder, in three waits."""
    monkeypatch.setattr(tunables, "QA_ENABLED", True)
    monkeypatch.setattr(tunables, "QA_SEARCH", True)
    for line_id in ("opener_short_prompt", "did_not_get_reply"):
        assert all(load_lines()[line_id].get(l, "").strip() for l in ("en", "hi", "mr")), line_id

    # 1. One silence at every position of a whole call, by keys and by voice.
    kinds: set[str] = set()
    silent = 0
    # The spoken base never reaches a confirm, so a third script says a gender and then goes quiet.
    confirm_script = [Digit(key), Digit("1"), Digit("2"), Speech("I am a woman"), Silence(n=1),
                      Speech("yes")] + BASE_KEYS[4:]
    scripts = [(f"{n}_{pos}", [Digit(key)] + b[1:pos] + [Silence(n=1)] + b[pos:])
               for n, b in (("keys", BASE_KEYS), ("spoken", BASE_SPOKEN)) for pos in range(1, len(b) + 1)]
    for name, script in scripts + [("confirm", confirm_script)]:
        audio = WaitRecorder(script)
        name = f"silence_{name}"
        Engine.run_call(audio, SweepModel(), corpus, Log.open(name, corpus.snapshot_id, logs_dir=tmp_path))
        _check(_lines(tmp_path, name), audio)
        assert audio.language == lang
        assert len(audio.reprompts) == audio.silent_waits, f"{name}: a silent wait was not answered"
        for prompt, said, said_lang in audio.reprompts:
            assert _reprompt_is_right(prompt, said), f"{name}: {prompt} then {said}"
            assert said_lang == lang
            kinds.add(_kind(prompt))
        silent += audio.silent_waits
    assert silent >= 10, "the sweep never reached a silent wait"
    assert {"opener", "box", "confirm", "anything_else", "readback"} <= kinds, kinds

    # 2. Turn 0: silence asks for the language again; nothing is picked for the caller.
    class Turn0(SweepAudio):
        def select_language(self):
            if self.inputs and isinstance(self.inputs[0], Silence):
                self.waits += 1
                self.played.append("greeting_trilingual")  # the phone says it on each pass
                return self.inputs.pop(0)
            return super().select_language()

    audio = Turn0([Silence(n=1), Digit(key)] + BASE_KEYS[1:])
    Engine.run_call(audio, SweepModel(), corpus, Log.open("t0", corpus.snapshot_id, logs_dir=tmp_path))
    assert audio.played[:2] == ["greeting_trilingual", "greeting_trilingual"]  # the greeting replays
    assert "did_not_get_reply" not in audio.played  # no language is picked yet, so no one-language line
    assert audio.language == lang
    # (the log's header row carries "default" until a language is chosen; only the rows after count)
    picked = [l for l in _lines(tmp_path, "t0") if "lang_source" in l and "call_id" not in l]
    assert picked and all(l["lang_source"] == "keypad" for l in picked)

    audio = Turn0([Silence(n=1), Silence(n=2), Silence(n=3)])
    Engine.run_call(audio, SweepModel(), corpus, Log.open("t0_gone", corpus.snapshot_id, logs_dir=tmp_path))
    assert audio.played == ["greeting_trilingual", "greeting_trilingual", "greeting_trilingual", "closing_farewell"]
    assert audio.hung_up
    lines = _lines(tmp_path, "t0_gone")
    assert "stop" in lines[-1] and not any("lang_source" in l for l in lines if "call_id" not in l)

    # 3. Door A's two-name keypad turn: silence asks both names again, never declines.
    audio = WaitRecorder([Silence(n=1), Digit("2")])
    log = Log.open("pick", corpus.snapshot_id, logs_dir=tmp_path)
    assert _door_a_pick(audio, log, 1, "S1", "S2") == "2"
    assert audio.silent_waits == 1 and len(audio.reprompts) == 1
    prompt, said, _ = audio.reprompts[0]
    assert _reprompt_is_right(prompt, said) and "door_a_option_1" in said
    audio = WaitRecorder([Silence(n=1), Silence(n=2), Silence(n=3)])
    assert _door_a_pick(audio, log, 1, "S1", "S2") == "hangup"
    assert audio.played[-1] == "closing_farewell"

    # 4. A caller who goes quiet at any point is let go on the third silent wait in a row.
    runs = ladder_ends = 0
    for base in (BASE_KEYS, BASE_SPOKEN):
        for pos in range(len(base) + 1):
            audio = GoneCaller([Digit(key)] + base[1:pos])
            Engine.run_call(audio, SweepModel(), corpus, Log.open(f"gone_{runs}", corpus.snapshot_id, logs_dir=tmp_path))
            runs += 1
            assert audio.hung_up and audio.silent_run <= 3
            if audio.silent_run:
                assert audio.silent_run == 3 and audio.played[-1] == "closing_farewell"
                ladder_ends += 1
    assert ladder_ends >= runs // 2, "most runs should have ended by the ladder"


# --- 7.5 voice at any time --------------------------------------------------------------------


class _LangSTT(_LiveFakeSTT):
    """Says what it is told, one reply per utterance, and keeps the language it was asked for."""

    def __init__(self, texts):
        super().__init__()
        self.texts = list(texts)
        self.asked_lang: list[str] = []

    def transcribe(self, audio, lang="", hint="", is_wav=False):
        self.calls += 1
        self.asked_lang.append(lang)
        text = self.texts.pop(0)
        return SttResult(transcript=text, lang="", success=bool(text))


def _greeting_line(texts, key=None):
    """A real Mouth, Turn, Ear and PhoneAudio; the greeting is playing; the caller then talks
    (or presses `key`) over it. Returns (line, stt, what select_language gave)."""
    stt = _LangSTT(texts)
    line = _LiveLine(stt=stt)
    if key is not None:
        _later(0.05, line.turn.push_key, key)
    else:
        _later(0.05, line.voice, 30, 45)
    return line, stt, line.phone.select_language


@pytest.mark.parametrize("lang,said", [
    ("hi", "Hindi"), ("hi", "हिंदी"), ("mr", "Marathi"), ("mr", "मराठी"), ("en", "English"), ("en", "अंग्रेज़ी"),
])
def test_voice_at_any_time_greeting_picks_the_language(monkeypatch, lang, said):
    monkeypatch.setattr(tunables, "LANGS_OFFERED", ("hi", "mr", "en"))
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", True)
    monkeypatch.setattr(tunables, "KEY_GUARD_MS", 0)
    line, stt, select = _greeting_line([said])
    got = select()
    assert got == (lang, "voice")
    assert line.phone.language == lang
    assert stt.calls == 1 and stt.asked_lang == [""]                  # the STT was not told a language
    assert line.mouth.last_cut[0] == "greeting_trilingual"            # the voice stopped the greeting
    assert not line.mouth.playing


@pytest.mark.parametrize("said", ["mm hello hello", "kisan ke baare mein", "Hindi English", ""])
def test_voice_at_any_time_unclear_speech_asks_again_and_picks_nothing(monkeypatch, said):
    monkeypatch.setattr(tunables, "LANGS_OFFERED", ("hi", "mr", "en"))
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", True)
    monkeypatch.setattr(tunables, "KEY_GUARD_MS", 0)
    line, stt, select = _greeting_line([said])
    line.phone.language = "mr"                                        # a pick would change this
    got = select()
    assert stt.calls == 1                                             # the case was really reached
    assert isinstance(got, (Speech, Noise)) and not isinstance(got, tuple)
    assert line.phone.language == "mr"
    assert not line.turn.hung_up.is_set()


def test_voice_at_any_time_a_key_still_works(monkeypatch):
    monkeypatch.setattr(tunables, "LANGS_OFFERED", ("hi", "mr", "en"))
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", True)
    monkeypatch.setattr(tunables, "KEY_GUARD_MS", 0)
    line, stt, select = _greeting_line([], key="2")
    assert select() == ("mr", "keypad")
    assert stt.calls == 0


def test_voice_at_any_time_voice_off_the_greeting_is_as_before(monkeypatch):
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", False)
    monkeypatch.setattr(tunables, "SILENCE_GAP_S", 0.2)
    monkeypatch.setattr(tunables, "TURN0_GAP_S", 0.2)
    line, stt, select = _greeting_line(["Hindi"])
    got = select()
    assert isinstance(got, Silence) and stt.calls == 0                # the voice is not heard


def test_voice_at_any_time_engine_asks_again_after_unclear_speech(corpus, tmp_path):
    """One miss (words that name no language) replays the greeting and picks nothing; the
    next answer, by voice, is logged as voice. Misses never hang the caller up."""
    class Turn0(SweepAudio):
        def select_language(self):
            self.played.append("greeting_trilingual")
            return self.inputs.pop(0) if self.inputs else Hangup()

    audio = Turn0([Speech("mm hello"), Noise(), ("en", "voice")] + BASE_KEYS[1:])
    Engine.run_call(audio, SweepModel(), corpus, Log.open("v_miss", corpus.snapshot_id, logs_dir=tmp_path))
    assert audio.played[:3] == ["greeting_trilingual"] * 3
    assert audio.language == "en"
    picked = [l for l in _lines(tmp_path, "v_miss") if "lang_source" in l and "call_id" not in l]
    assert picked and picked[0]["lang_source"] == "voice"
    assert "closing_farewell" not in audio.played[:3]


class _GapAudio(SweepAudio):
    """The caller speaks again on the `fire_on`-th look into the busy time (7.5). The new words
    then come from the next wait, as PhoneAudio gives them."""

    def __init__(self, inputs, fire_on, model):
        super().__init__(inputs)
        self.fire_on, self.model = fire_on, model
        self.looks = 0
        self.fired_after_answers: list[int] = []

    def newer_words(self):
        self.looks += 1
        if self.looks != self.fire_on:
            return False
        self.fired_after_answers.append(len(self.model.asked))
        self.inputs.insert(0, Speech(NEW_WORDS))
        return True


OLD_WORDS = "what does the tractor subsidy give?"
NEW_WORDS = "what does the tractor subsidy give a farmer?"


class _AskedModel(SweepModel):
    def __init__(self):
        self.asked: list[str] = []

    def answer(self, question, lang, cards, profile=None, scheme_ids=None, english=False):
        self.asked.append(question)
        return f"answer to: {question}"


@pytest.mark.parametrize("fire_on", [1, 2, 3])
def test_voice_at_any_time_newest_words_win_in_the_busy_gap(corpus, tmp_path, monkeypatch, fire_on):
    monkeypatch.setattr(tunables, "QA_ENABLED", True)
    monkeypatch.setattr(tunables, "QA_SEARCH", True)
    model = _AskedModel()
    audio = _GapAudio([Digit("3"), Digit("1"), Speech(OLD_WORDS)] + BASE_KEYS[3:], fire_on, model)
    Engine.run_call(audio, model, corpus, Log.open(f"gap{fire_on}", corpus.snapshot_id, logs_dir=tmp_path))
    lines = _lines(tmp_path, f"gap{fire_on}")
    _check(lines, audio)
    assert audio.fired_after_answers, "the caller never spoke again in the gap"
    assert f"answer to: {OLD_WORDS}" not in audio.answers             # the old answer is never said
    assert f"answer to: {NEW_WORDS}" in audio.answers                 # the newest words are used
    if audio.fired_after_answers[0] == 0:
        assert model.asked == [NEW_WORDS]                             # no paid call for thrown-away words
    assert all(l.get("transcript") != OLD_WORDS for l in lines if l.get("class") == "QUESTION")


def test_voice_at_any_time_gap_looks_reach_both_before_and_after_the_paid_call(corpus, tmp_path, monkeypatch):
    monkeypatch.setattr(tunables, "QA_ENABLED", True)
    monkeypatch.setattr(tunables, "QA_SEARCH", True)
    seen = set()
    for fire_on in (1, 2, 3):
        model = _AskedModel()
        audio = _GapAudio([Digit("3"), Digit("1"), Speech(OLD_WORDS)] + BASE_KEYS[3:], fire_on, model)
        Engine.run_call(audio, model, corpus, Log.open(f"look{fire_on}", corpus.snapshot_id, logs_dir=tmp_path))
        seen.update(audio.fired_after_answers)
    assert seen == {0, 1}, "the test must cover a drop before the paid call and one after it"


def test_voice_at_any_time_phone_gap_gives_the_newest_words_and_never_says_the_old_answer(monkeypatch):
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", True)
    monkeypatch.setattr(tunables, "QA_SPEAK", True)
    monkeypatch.setattr(tunables, "KEY_GUARD_MS", 0)
    spoken: list[str] = []
    stt = _LangSTT(["new question"])
    line = _LiveLine(stt=stt, pool=_LiveNoPool(), speak=lambda t, l: spoken.append(t) or b"\x55" * 8000)
    assert line.phone.newer_words() is False                          # a quiet line: nothing newer
    line.voice(30, 45)                                                # they speak while the engine works
    assert line.phone.say_text("Six thousand rupees a year.") is False   # rendered, then not said
    assert stt.calls == 1 and spoken                                  # the case was really reached
    assert [m for m in line.sent if m.get("event") == "media"] == []  # nothing went to the line
    got = line.phone.next_input("spoken")
    assert isinstance(got, Speech) and got.text == "new question"     # the next wait gives the new words
    assert stt.calls == 1                                             # heard once, not twice
