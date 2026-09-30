"""Plan 2.6 — keys and the silence timer."""
from __future__ import annotations

import threading
import time

from haqdaar.audio.mouth import Mouth
from haqdaar.audio.turn import HANGUP, Turn


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
