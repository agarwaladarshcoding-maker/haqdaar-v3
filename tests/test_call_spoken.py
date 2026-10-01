"""tests/test_call_spoken.py

Unit and integration tests for spoken answers and confirmation turns (HAQDAAR v2 Step 4.4).
Verifies:
- Confirm-accept: model extracts spoken answer, Mouth plays confirmation, caller presses 1, accepted.
- Confirm-accept with spoken affirmation ("haan", "yes").
- Confirm-mismatch: caller presses 2 to fix, turn re-asks with rephrase prompt.
- Two confirm mismatches (strikes = 2) drops box to keypad menu.
- Silence handling during confirmation: rung 1 repeats confirmation, rung 2 plays presence, rung 3 hangs up.
- Noise and invalid digits during confirmation: logged as NOISE/UNCLEAR, increments strikes.
- Language switch (*) and repeat (#) during confirmation turn.
- Model failure (2 errors/timeouts) degrades call to keypad_only mode.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
import pytest

from haqdaar.contracts import tunables
from haqdaar.contracts.log_schema import (
    STOP_LE_4_SURVIVORS,
    STOP_MAX_TURNS,
    STOP_ZERO_SURVIVORS,
    TurnLogRecord,
)
from haqdaar.contracts.types import (
    Answer,
    Digit,
    Hangup,
    Lang,
    LangSource,
    Noise,
    Silence,
    Speech,
    Stamp,
    Unclear,
)
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.engine.call import Engine
from haqdaar.model.client import ModelClientResponse
from haqdaar.sim import FakeAudio, SimModelClient


class MockAudioSession:
    """Mock audio session tracking played lines and feeding scripted inputs."""

    def __init__(self, inputs: Optional[list[Any]] = None, initial_lang: Lang = "hi") -> None:
        self.inputs = list(inputs) if inputs else []
        self.language: Lang = initial_lang
        self.played: list[str] = []
        self.hung_up: bool = False
        self._last_played: tuple[str, ...] = ()
        self.marks: list[str] = []
        self.input_profiles: list[str] = []

    def select_language(self) -> tuple[Lang, LangSource]:
        self.played.append("greeting_trilingual")
        if self.inputs and isinstance(self.inputs[0], Digit):
            d = self.inputs.pop(0).digit
            if d == "2":
                self.language = "mr"
                return "mr", "keypad"
            elif d == "3":
                self.language = "en"
                return "en", "keypad"
        return "hi", "keypad"

    def say(self, sequence: tuple[str, ...]) -> None:
        self._last_played = sequence
        for token in sequence:
            self.played.append(token)

    def repeat(self) -> None:
        self.played.append("REPEAT")
        if self._last_played:
            for token in self._last_played:
                self.played.append(token)

    def clear(self) -> None:
        self.played.append("CLEAR")

    def on_mark(self, mark: str) -> float:
        self.marks.append(mark)
        return 0.0

    def hangup(self) -> None:
        self.hung_up = True

    def next_input(self, profile: str = "normal") -> Digit | Noise | Silence | Hangup | Speech:
        self.input_profiles.append(profile)
        if self.inputs:
            item = self.inputs.pop(0)
            if isinstance(item, str):
                return Digit(digit=item)
            return item
        return Digit(digit="2")


class MockModelClient:
    """Mock client for testing model router and error conditions."""

    def __init__(
        self,
        stamps_to_return: Optional[list[dict[str, Any]]] = None,
        fail_count: int = 0,
        turn_response: Optional[dict[str, Any]] = None,
    ) -> None:
        self.stamps_to_return = stamps_to_return or [
            {"box": "category", "value": "farming", "span": "farming"}
        ]
        self.fail_count = fail_count
        self.current_fails = 0
        self.turn_response = turn_response or {
            "class": "ANSWER",
            "box": "occupation",
            "value": "farmer",
            "span": "farmer",
        }

    def call(self, messages: list[dict[str, str]], task: str = "model_opener") -> ModelClientResponse:
        if self.current_fails < self.fail_count:
            self.current_fails += 1
            return ModelClientResponse(success=False, data=None, error="simulated_timeout", is_timeout=True)

        if task == "model_opener":
            return ModelClientResponse(
                success=True,
                data={"stamps": self.stamps_to_return},
                latency_s=0.005,
            )
        elif task == "model_turn":
            return ModelClientResponse(
                success=True,
                data=self.turn_response,
                latency_s=0.005,
            )
        return ModelClientResponse(success=True, data={}, latency_s=0.005)


class MockModel:
    """Mock Model router meeting the duck-typed Model interface for call.py."""

    def __init__(
        self,
        opener_res: Optional[list[Stamp] | Unclear] = None,
        turn_res: Optional[Any] = None,
        failures: int = 0,
    ) -> None:
        self._opener_res = opener_res if opener_res is not None else [
            Stamp(box="category", value="farming", span="farming")
        ]
        self._turn_res = turn_res
        self._failures = failures

    @property
    def failures(self) -> int:
        return self._failures

    @property
    def keypad_only(self) -> bool:
        return self._failures >= tunables.MODEL_FAILURES_TO_KEYPAD

    def opener(self, transcript: str, lang: str = "en") -> list[Stamp] | Unclear:
        if self.keypad_only:
            return Unclear(reason="keypad_only")
        return self._opener_res

    def turn(self, transcript: str, box: str, window=None, ask_count: int = 0) -> Any:
        if self.keypad_only:
            return Unclear(reason="keypad_only")
        if self._turn_res is not None:
            return self._turn_res
        return Answer(box=box, value="farmer", span="farmer")


@pytest.fixture
def fixture_corpus(tmp_path, monkeypatch):
    """Fixture providing a test snapshot built from fixtures/schemes.jsonl."""
    root_dir = Path(__file__).resolve().parent.parent
    schemes_file = root_dir / "fixtures" / "schemes.jsonl"

    schemes = []
    with open(schemes_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                if row.get("scheme_id") != "S6":
                    schemes.append(row)

    snap_dir = tmp_path / "snapshots"
    audio_dir = tmp_path / "audio"
    snap_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(tunables, "SNAPSHOTS_DIR", str(snap_dir))
    monkeypatch.setattr(tunables, "AUDIO_DIR", str(audio_dir))

    snap_id = build_snapshot(
        schemes_data=schemes,
        snapshot_id="test_spoken_snap",
        snapshots_dir=snap_dir,
        audio_dir=audio_dir,
        render_stubs=True,
    )
    return Corpus.load(snap_id)


def test_confirm_accept_spoken_answer(fixture_corpus, tmp_path):
    """Caller speaks answer, Mouth reads back echo, caller presses 1 to accept."""
    audio = MockAudioSession(inputs=[
        Digit("1"),                             # Turn 0: language Hindi
        Speech(text="I need farming schemes"),  # Spoken answer to category opener
        Digit("1"),                             # Confirm turn: "1" = accept
        Digit("2"),                             # State: 2 = OTHER
        Digit("1"),                             # Gender: 1 = female
        Digit("3"),                             # Social category: 3 = SC
        Digit("2"),                             # Terminal readback: 2 = next scheme
        Digit("2"),                             # Terminal readback: 2 = next scheme
        Digit("2"),                             # Anything else: 2 = no
    ])
    log = Log.open("test_confirm_accept", fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = MockModel(opener_res=[Stamp(box="category", value="farming", span="farming")])

    Engine.run_call(audio, model, fixture_corpus, log)

    # Verify confirmation tokens played
    assert "bundle_confirm_intro" in audio.played
    assert "chip_category_farming" in audio.played
    assert "confirm_yn_suffix" in audio.played

    # Verify input profiles
    assert "spoken" in audio.input_profiles
    assert "confirm" in audio.input_profiles

    # Check LOG lines
    lines = [json.loads(l) for l in open(tmp_path / "test_confirm_accept.jsonl")]
    ans_lines = [l for l in lines if l.get("class") == "ANSWER"]
    # Turn 1: spoken answer parsed
    t1 = next(l for l in ans_lines if l.get("turn_n") == 1)
    assert t1["box"] == "category"
    assert t1["value"] == "farming"
    assert t1["transcript"] == "I need farming schemes"
    assert t1["span"] == "farming"

    # Turn 2: confirmation accepted
    t2 = next(l for l in ans_lines if l.get("turn_n") == 2)
    assert t2["box"] == "category"
    assert t2["value"] == "farming"
    assert t2["transcript"] == "1"

    # Call reached valid terminal
    assert lines[-1]["mode"] == "voice"
    assert lines[-1]["stop"] == STOP_LE_4_SURVIVORS


def test_confirm_accept_with_spoken_affirmation(fixture_corpus, tmp_path):
    """Caller confirms what was heard using spoken affirmation ('haan' / 'yes')."""
    audio = MockAudioSession(inputs=[
        Digit("1"),                             # Turn 0: Hindi
        Speech(text="I need farming schemes"),  # Spoken opener
        Speech(text="haan"),                    # Spoken confirmation "haan"
        Digit("2"),                             # State: OTHER
        Digit("1"),                             # Gender: female
        Digit("3"),                             # Social category: SC
        Digit("2"),
        Digit("2"),
        Digit("2"),
    ])
    log = Log.open("test_confirm_voice_accept", fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = MockModel(opener_res=[Stamp(box="category", value="farming", span="farming")])

    Engine.run_call(audio, model, fixture_corpus, log)

    assert "bundle_confirm_intro" in audio.played
    assert "chip_category_farming" in audio.played
    assert "confirm_yn_suffix" in audio.played

    lines = [json.loads(l) for l in open(tmp_path / "test_confirm_voice_accept.jsonl")]
    t2 = next(l for l in lines if l.get("turn_n") == 2 and l.get("class") == "ANSWER")
    assert t2["box"] == "category"
    assert t2["value"] == "farming"
    assert t2["transcript"] == "haan"


def test_confirm_mismatch_reask_and_then_accept(fixture_corpus, tmp_path):
    """Caller rejects readback (presses 2), turn re-asks with unclear_prompt, then accepts."""
    audio = MockAudioSession(inputs=[
        Digit("1"),                             # Turn 0: Hindi
        Speech(text="I need farming schemes"),  # Turn 1: spoken opener
        Digit("2"),                             # Confirm turn: "2" = mismatch / fix!
        Speech(text="I want farming loans"),    # Turn 3: re-asked spoken opener
        Digit("1"),                             # Turn 4: confirm accept!
        Digit("2"),                             # State: OTHER
        Digit("1"),                             # Gender: female
        Digit("3"),                             # Social category: SC
        Digit("2"),
        Digit("2"),
        Digit("2"),
    ])
    log = Log.open("test_confirm_mismatch", fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = MockModel(opener_res=[Stamp(box="category", value="farming", span="farming")])

    Engine.run_call(audio, model, fixture_corpus, log)

    # Unclear prompt was played on mismatch
    assert "unclear_prompt" in audio.played

    lines = [json.loads(l) for l in open(tmp_path / "test_confirm_mismatch.jsonl")]
    # Turn 2 must be logged as UNCLEAR on key '2'
    t2 = next(l for l in lines if l.get("turn_n") == 2)
    assert t2["class"] == "UNCLEAR"
    assert t2["transcript"] == "2"

    # Turn 4 must be the accepted ANSWER
    t4 = next(l for l in lines if l.get("turn_n") == 4)
    assert t4["class"] == "ANSWER"
    assert t4["box"] == "category"
    assert t4["value"] == "farming"


def test_confirm_mismatch_two_strikes_drops_to_keypad(fixture_corpus, tmp_path):
    """2 mismatches / strikes on a box drops that box to the keypad menu."""
    audio = MockAudioSession(inputs=[
        Digit("1"),                             # Turn 0: Hindi
        Speech(text="I need farming schemes"),  # Spoken opener
        Digit("2"),                             # Strike 1: mismatch
        Speech(text="Still farming"),           # Re-ask spoken opener
        Digit("2"),                             # Strike 2: mismatch -> box drops to keypad menu!
        # Now box is keypad! Opener prompt is re-played with keypad menu.
        Digit("1"),                             # Keypad selection: 1 = farming!
        Digit("2"),                             # State: OTHER
        Digit("1"),                             # Gender: female
        Digit("3"),                             # Social category: SC
        Digit("2"),
        Digit("2"),
        Digit("2"),
    ])
    log = Log.open("test_confirm_keypad_drop", fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = MockModel(opener_res=[Stamp(box="category", value="farming", span="farming")])

    Engine.run_call(audio, model, fixture_corpus, log)

    lines = [json.loads(l) for l in open(tmp_path / "test_confirm_keypad_drop.jsonl")]
    unclears = [l for l in lines if l.get("class") == "UNCLEAR"]
    assert len(unclears) >= 2

    # After 2 strikes, the next ANSWER for category is keypad-based
    answers = [l for l in lines if l.get("class") == "ANSWER" and l.get("box") == "category"]
    keypad_ans = answers[-1]
    assert keypad_ans["transcript"] == "1"
    assert keypad_ans["value"] == "farming"


def test_confirm_silence_handling_ladder(fixture_corpus, tmp_path):
    """Silence during confirmation runs the silence ladder: rung 1 repeat, rung 2 presence, rung 3 farewell & hangup."""
    audio = MockAudioSession(inputs=[
        Digit("1"),                             # Turn 0: Hindi
        Speech(text="I need farming schemes"),  # Spoken opener
        Silence(n=1),                           # Silence rung 1 -> repeat
        Silence(n=2),                           # Silence rung 2 -> presence
        Silence(n=3),                           # Silence rung 3 -> closing farewell & hangup
    ])
    log = Log.open("test_confirm_silence", fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = MockModel(opener_res=[Stamp(box="category", value="farming", span="farming")])

    Engine.run_call(audio, model, fixture_corpus, log)

    assert "REPEAT" in audio.played
    assert "silence_presence" in audio.played
    assert "closing_farewell" in audio.played
    assert audio.hung_up is True

    lines = [json.loads(l) for l in open(tmp_path / "test_confirm_silence.jsonl")]
    silence_lines = [l for l in lines if l.get("class") == "SILENCE"]
    assert len(silence_lines) == 3
    assert silence_lines[0]["silence_n"] == 1
    assert silence_lines[1]["silence_n"] == 2
    assert silence_lines[2]["silence_n"] == 3


def test_confirm_noise_and_invalid_digits(fixture_corpus, tmp_path):
    """Noise and out-of-menu digits during confirmation are logged as NOISE/UNCLEAR and increment strikes."""
    audio = MockAudioSession(inputs=[
        Digit("1"),                             # Turn 0: Hindi
        Speech(text="I need farming schemes"),  # Spoken opener
        Noise(),                                # Noise during confirmation -> logs NOISE, strike=1
        Speech(text="I need farming schemes"),  # Re-ask
        Digit("9"),                             # Invalid digit '9' during confirmation -> logs UNCLEAR, strike=2
        # Box drops to keypad
        Digit("1"),                             # Keypad pick 1 = farming
        Digit("2"),
        Digit("1"),
        Digit("3"),
        Digit("2"),
        Digit("2"),
        Digit("2"),
    ])
    log = Log.open("test_confirm_noise_invalid", fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = MockModel(opener_res=[Stamp(box="category", value="farming", span="farming")])

    Engine.run_call(audio, model, fixture_corpus, log)

    lines = [json.loads(l) for l in open(tmp_path / "test_confirm_noise_invalid.jsonl")]
    assert any(l.get("class") == "NOISE" for l in lines)
    assert any(l.get("class") == "UNCLEAR" and l.get("transcript") == "9" for l in lines)


def test_confirm_language_switch_and_repeat(fixture_corpus, tmp_path):
    """Key '*' switches language during confirmation, '#' repeats the echo."""
    audio = MockAudioSession(inputs=[
        Digit("1"),                             # Turn 0: Hindi
        Speech(text="I need farming schemes"),  # Spoken opener
        Digit("#"),                             # Repeat confirmation
        Digit("*"),                             # Switch language to Marathi ('mr')
        Digit("1"),                             # Confirm accept in Marathi!
        Digit("2"),
        Digit("1"),
        Digit("3"),
        Digit("2"),
        Digit("2"),
        Digit("2"),
    ])
    log = Log.open("test_confirm_controls", fixture_corpus.snapshot_id, logs_dir=tmp_path)
    model = MockModel(opener_res=[Stamp(box="category", value="farming", span="farming")])

    Engine.run_call(audio, model, fixture_corpus, log)

    assert "REPEAT" in audio.played
    lines = [json.loads(l) for l in open(tmp_path / "test_confirm_controls.jsonl")]
    lang_switches = [l for l in lines if "lang" in l and l.get("lang_source") == "keypad"]
    assert any(l.get("lang") == "mr" for l in lang_switches)


def test_model_failure_degrades_to_keypad_only(fixture_corpus, tmp_path):
    """Two model client failures degrade call to keypad_only mode."""
    audio = MockAudioSession(inputs=[
        Digit("1"),                             # Turn 0: Hindi
        Speech(text="Hello"),                   # Opener attempt 1 -> model fails (strike 1)
        Speech(text="Hello again"),             # Opener attempt 2 -> model fails (strike 2 -> keypad_only)
        # Call is now in keypad_only mode!
        Digit("1"),                             # Keypad category choice 1 = farming
        Digit("2"),                             # State: OTHER
        Digit("1"),                             # Gender: female
        Digit("3"),                             # Social category: SC
        Digit("2"),
        Digit("2"),
        Digit("2"),
    ])
    log = Log.open("test_model_degrade", fixture_corpus.snapshot_id, logs_dir=tmp_path)

    # Mock model that fails twice
    class FailingModel:
        def __init__(self):
            self._fails = 0

        @property
        def failures(self):
            return self._fails

        @property
        def keypad_only(self):
            return self._fails >= 2

        def opener(self, transcript, lang="en"):
            self._fails += 1
            return Unclear(reason="timeout")

        def turn(self, transcript, box, window=None, ask_count=0):
            self._fails += 1
            return Unclear(reason="timeout")

    model = FailingModel()
    Engine.run_call(audio, model, fixture_corpus, log)

    assert "keypad_only_mode" in audio.played
    lines = [json.loads(l) for l in open(tmp_path / "test_model_degrade.jsonl")]
    assert any(l.get("mode") == "keypad_only" for l in lines)
    assert lines[-1]["mode"] == "keypad_only"
