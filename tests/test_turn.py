"""Plan 2.6 — keys and the silence timer."""
from __future__ import annotations

import queue
import threading
import time

from haqdaar.audio.mouth import Mouth
from haqdaar.audio.turn import HANGUP, Turn
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Silence, Speech


def _pair():
    out: list[dict] = []
    mouth = Mouth(out.append, "S")
    return mouth, Turn(mouth), out


def test_a_key_is_returned():
    _, turn, _ = _pair()
    turn.push_key("3")
    assert turn.wait(1.0) == "3"


def test_silence_after_the_gap():
    _, turn, _ = _pair()
    t0 = time.monotonic()
    assert turn.wait(0.1) is None
    assert 0.09 < time.monotonic() - t0 < 0.5


def test_silence_clock_starts_after_the_line_finishes():
    mouth, turn, _ = _pair()
    mouth.play([("prompt", b"\x10" * 2400)])  # 0.3 s of audio, marks never come back
    t0 = time.monotonic()
    assert turn.wait(0.1) is None
    assert time.monotonic() - t0 >= 0.38


def test_a_key_during_a_line_stops_it_and_is_kept():
    mouth, turn, out = _pair()
    mouth.play([("not_understood", b"\x10" * 80000)])  # a 10 s retry line
    turn.push_key("2")                                 # pressed while it plays
    assert out[-1]["event"] == "clear" and not mouth.playing
    assert turn.has_key()
    t0 = time.monotonic()
    assert turn.wait(5.0) == "2"                       # returned at once, not after 10 s
    assert time.monotonic() - t0 < 0.1


def test_keys_pressed_fast_first_taken_rest_dropped():
    _, turn, _ = _pair()
    turn.push_key("1")
    turn.push_key("2")
    turn.push_key("3")
    assert turn.wait(1.0) == "1"
    assert turn.wait(0.1) is None


def test_hangup_wakes_a_waiting_engine():
    _, turn, _ = _pair()
    threading.Timer(0.05, turn.push_hangup).start()
    assert turn.wait(5.0) == HANGUP
    assert turn.hung_up.is_set()


class _FakeEar:
    def __init__(self, speech_text: str = "kisan", keypad_only: bool = False) -> None:
        self.speech_text = speech_text
        self.keypad_only = keypad_only
        self._keys: queue.Queue[str] = queue.Queue()
        self.drained = False
        self.listened_timeout: float = 0.0
        self.listened_lang: str = ""
        self.listened_hint: str = ""

    def drain_media(self) -> None:
        self.drained = True

    def push_dtmf(self, digit: str) -> None:
        self._keys.put(digit)

    def listen(self, timeout: float = 6.0, lang: str = "", hint: str = "") -> Speech:
        self.listened_timeout = timeout
        self.listened_lang = lang
        self.listened_hint = hint
        return Speech(text=self.speech_text)


def test_wait_input_pre_queued_key():
    _, turn, _ = _pair()
    turn.push_key("5")
    res = turn.wait_input(gap_s=1.0)
    assert isinstance(res, Digit)
    assert res.digit == "5"


def test_wait_input_pre_queued_hangup():
    _, turn, _ = _pair()
    turn.push_hangup()
    res = turn.wait_input(gap_s=1.0)
    assert isinstance(res, Hangup)


def test_wait_input_hung_up_flag():
    _, turn, _ = _pair()
    turn.hung_up.set()
    res = turn.wait_input(gap_s=1.0)
    assert isinstance(res, Hangup)


def test_wait_input_keypad_silence():
    _, turn, _ = _pair()
    t0 = time.monotonic()
    res = turn.wait_input(gap_s=0.1, profile="normal")
    assert isinstance(res, Silence)
    assert res.n == 1
    assert 0.09 < time.monotonic() - t0 < 0.5


def test_wait_input_spoken_delegates_to_ear():
    mouth, _, _ = _pair()
    ear = _FakeEar(speech_text="pm kisan")
    turn = Turn(mouth, ear=ear)
    res = turn.wait_input(gap_s=2.0, profile="spoken", lang="hi", hint="kisan")
    assert isinstance(res, Speech)
    assert res.text == "pm kisan"
    assert ear.drained is True
    assert ear.listened_timeout == 2.0
    assert ear.listened_lang == "hi"
    assert ear.listened_hint == "kisan"


def test_wait_input_spoken_barge_in_during_playback():
    mouth, _, out = _pair()
    ear = _FakeEar()
    turn = Turn(mouth, ear=ear)
    mouth.play([("prompt", b"\x10" * 80000)])  # 10 s line
    turn.push_key("1")  # barge-in
    res = turn.wait_input(gap_s=1.0, profile="spoken")
    assert isinstance(res, Digit)
    assert res.digit == "1"
    assert not mouth.playing


def test_wait_input_spoken_degraded_to_keypad_only():
    mouth, _, _ = _pair()
    ear = _FakeEar(keypad_only=True)
    turn = Turn(mouth, ear=ear)
    turn.push_key("2")
    res = turn.wait_input(gap_s=1.0, profile="spoken")
    assert isinstance(res, Digit)
    assert res.digit == "2"
    assert ear.drained is False


# --- 7.5: voice in the busy gap. The key guards are not changed. ---------------------------


class _GapEar(_FakeEar):
    """An ear that has queued voice (or not) while the engine was busy."""

    def __init__(self, voice: str, text: str = "new words") -> None:
        super().__init__(speech_text=text)
        self.voice = voice
        self.watch_starts = 0
        self.resumed: list[bool] = []

    def start_watch(self) -> None:
        self.watch_starts += 1

    def watch_voice(self, in_guard: bool = False) -> str:
        return self.voice

    def listen(self, timeout: float = 6.0, lang: str = "", hint: str = "", resume: bool = False) -> Speech:
        self.resumed.append(resume)
        return super().listen(timeout=timeout, lang=lang, hint=hint)


def test_newer_input_gives_the_words_the_caller_said_while_busy(monkeypatch):
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", True)
    mouth, _, _ = _pair()
    ear = _GapEar("cut")
    turn = Turn(mouth, ear=ear)
    got = turn.newer_input(1.0, lang="hi")
    assert got == Speech(text="new words")
    assert ear.resumed == [True] and ear.listened_lang == "hi"   # carries on with the voice already heard


def test_newer_input_is_none_when_the_caller_stayed_quiet_or_it_is_off(monkeypatch):
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", True)
    mouth, _, _ = _pair()
    ear = _GapEar("short")                       # a cough is not new words
    assert Turn(mouth, ear=ear).newer_input(1.0) is None and ear.resumed == []
    assert Turn(mouth).newer_input(1.0) is None  # no ear
    ear = _GapEar("cut", text="x")
    assert Turn(mouth, ear=ear).newer_input(1.0) is not None
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", False)
    ear = _GapEar("cut")
    assert Turn(mouth, ear=ear).newer_input(1.0) is None and ear.resumed == []
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", True)
    assert Turn(mouth, ear=_FakeEar(keypad_only=True)).newer_input(1.0) is None


def test_a_key_in_the_gap_is_still_dropped_whatever_newer_input_found(monkeypatch):
    """G8 stays: a key pressed for a prompt the engine has moved past never answers the next one."""
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", True)
    monkeypatch.setattr(tunables, "KEY_GUARD_MS", 0)
    mouth, _, _ = _pair()
    turn = Turn(mouth, ear=_GapEar("cut"))
    turn.start_prompt("question")
    turn.push_key("1")                      # pressed for the question
    turn.start_prompt("answer")             # the engine moved on while it worked
    assert turn.newer_input(1.0) == Speech(text="new words")
    assert turn.get_valid_key() is None     # the old key is still dropped (prompt_closed)
