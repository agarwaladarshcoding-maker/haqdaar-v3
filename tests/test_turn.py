"""Plan 2.6 — keys and the silence timer."""
from __future__ import annotations

import queue
import threading
import time

from haqdaar.audio.mouth import Mouth
from haqdaar.audio.turn import HANGUP, Turn
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


def test_keys_pressed_fast_all_arrive_in_order():
    _, turn, _ = _pair()
    for k in "1*9#":
        turn.push_key(k)
    assert [turn.wait(1.0) for _ in range(4)] == list("1*9#")


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
