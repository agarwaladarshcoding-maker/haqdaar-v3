"""Step 2.2: with the cut-in gate on, the ear listens from the first sound of a reply, not from when
the whole reply is queued. Gate off: nothing of this runs (the ear is drained when the talk waits, as before).
"""
from types import SimpleNamespace

import pytest

from haqdaar.audio.mouth import Mouth
from haqdaar.audio.turn import Turn
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Speech
from haqdaar.engine import talk as talk_mod
from tools import talk_eval as te


class Ear:
    """Records what the Turn asks of it. The voice is heard on the first look: a cut."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def drain_media(self) -> int:
        self.calls.append(("drain",))
        return 0

    def start_watch(self) -> None:
        self.calls.append(("watch",))

    def watch_voice(self, in_guard=False, min_ms=0, gap_ms=0) -> str:
        self.calls.append(("look", in_guard))
        return "" if in_guard else "cut"

    def listen(self, timeout=6.0, lang="", hint="", drain_stale=False, resume=False):
        self.calls.append(("listen", resume))
        return Speech(text="wait tell me about the pension", lang="en-IN")

    def push_dtmf(self, digit: str) -> None:
        pass


def _turn(monkeypatch, gate):
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "CUT_IN_GATE", gate)
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", False)
    out: list[dict] = []
    mouth = Mouth(out.append, "S")
    ear = Ear()
    turn = Turn(mouth, ear=ear)
    n = turn.start_prompt("answer")
    mouth.play([("answer", b"\x10" * 80000)], tag=(n, "answer"))   # a 10 s reply, its sentence queued just now
    return turn, ear


def test_gate_on_the_watch_starts_at_the_first_sound_and_is_kept(monkeypatch):
    turn, ear = _turn(monkeypatch, True)
    turn.ear_on()
    assert ear.calls == [("drain",), ("watch",)]
    ear.calls.clear()
    inp = turn.wait_input(gap_s=1.0, profile="spoken")
    # No new drain, no new watch, and no guard on the sound heard since the reply began.
    assert ear.calls[0] == ("look", False)
    assert ("drain",) not in ear.calls and ("watch",) not in ear.calls
    assert isinstance(inp, Speech) and inp.cut_clip == "answer"
    assert not turn._ear_on                          # used once: the next wait starts clean


def test_gate_on_without_the_first_sound_mark_waits_as_before(monkeypatch):
    turn, ear = _turn(monkeypatch, True)
    turn.wait_input(gap_s=1.0, profile="spoken")
    assert ear.calls[:3] == [("drain",), ("watch",), ("look", True)]   # drained, and the guard of the new sentence holds


def test_gate_off_the_first_sound_mark_does_nothing(monkeypatch):
    turn, ear = _turn(monkeypatch, False)
    turn.ear_on()
    assert ear.calls == [] and not turn._ear_on


def test_the_mark_is_not_carried_to_a_later_wait(monkeypatch):
    turn, ear = _turn(monkeypatch, True)
    turn.ear_on()
    turn.wait_input(gap_s=1.0, profile="normal")     # a wait that does not listen for words still uses the mark up
    assert not turn._ear_on


@pytest.mark.parametrize("gate", [False, True])
def test_speak_marks_the_first_sound_only_with_the_gate_on(monkeypatch, gate):
    monkeypatch.setattr(tunables, "CUT_IN_GATE", gate)
    monkeypatch.setattr(tunables, "LIVE_TTS_STREAM", False)
    order: list[str] = []
    audio = SimpleNamespace(say_text=lambda s, on_first=None: order.append("say") or True,
                            ear_on=lambda: order.append("ear_on"))
    t = SimpleNamespace(audio=audio)
    assert talk_mod._Talk._speak(t, "One. Two.", lambda: order.append("first"))
    assert order == (["ear_on", "first", "say"] if gate else ["first", "say"])


# --- a whole talk call ------------------------------------------------------------------

def _first_reply(res):
    return [c for c in res.clips if c["name"] == "answer"][2]["start"]   # the hello is two sentences before it


def test_words_over_the_start_of_a_reply_stop_it_sooner_and_are_heard_whole():
    plain = te.run_call("ask", True)
    first = _first_reply(plain)
    res = te.run_call("ask", True, te._inject("cut_in", first + 0.3))
    assert te.check(res) == []
    cut_at = min(c["cut_at"] for c in res.clips if c["cut_at"] is not None)
    # Before 2.2 the cut came 1.68 s in: the voice said while the reply was queued was thrown away.
    assert cut_at - first < 1.2
    heard = [r["text"] for r in res.log_rows if r.get("ev") == "heard"]
    assert heard[1].startswith("wait tell me about the pension scheme")


def test_a_hmm_over_the_start_of_a_reply_does_not_stop_it():
    plain = te.run_call("ask", True)
    res = te.run_call("ask", True, te._inject("hmm", _first_reply(plain) + 0.1))
    assert te.check(res) == [] and res.clears == []


def test_gate_off_the_call_is_as_before():
    plain = te.run_call("ask", False)
    res = te.run_call("ask", False, te._inject("cut_in", _first_reply(plain) + 0.3))
    assert res.clears == []
    assert [c["name"] for c in res.clips][:5] == [c["name"] for c in plain.clips][:5]
