"""tests/test_live_speech.py

Step 7.2 audio side, fakes only: the prompt that is sounding (A1, A2), the English pipe at the ear
(B), saying an answer aloud (C), and the caller's voice stopping a clip (D, rows S1-S8).
"""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

import pytest

from haqdaar.audio import ear as ear_mod
from haqdaar.audio import live_tts
from haqdaar.audio.ear import Ear, GroqWhisperSTT, SarvamSTT, SttResult
from haqdaar.audio.mouth import Mouth
from haqdaar.audio.phone import PhoneAudio
from haqdaar.audio.pool import AudioPool
from haqdaar.audio.turn import Turn
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Noise, Silence, Speech

LOUD = b"\x00\x10" * 160   # one 20 ms frame of 16-bit PCM at 8 kHz, rms about 4096
QUIET = b"\x00\x00" * 160


class FakeTrace:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def input_event(self, **row: Any) -> None:
        self.rows.append(row)

    def why(self, event: str) -> list[tuple[bool, str]]:
        return [(r["took"], r["why"]) for r in self.rows if r["event"] == event]


class FakeSTT:
    def __init__(self, result: Optional[SttResult] = None) -> None:
        self.result = result or SttResult(transcript="kisan ke baare mein", lang="hi-IN")
        self.calls = 0

    def reset_circuit(self) -> None:
        pass

    def transcribe(self, audio: bytes, lang: str = "", hint: str = "", is_wav: bool = False) -> SttResult:
        self.calls += 1
        return self.result


class FakeCorpus:
    def audio(self, token: str, lang: str, *rest: Any) -> str:
        return token

    def chunks(self, sid: str, lang: str) -> list[str]:
        return []

    def values(self, box: str) -> list[str]:
        return []


class FakePool:
    """Every render key is `sec` seconds of sound."""

    def __init__(self, sec: float = 3.0) -> None:
        self.sec = sec

    def get(self, key: str) -> bytes:
        return b"\x55" * int(8000 * self.sec)


class Line:
    """A Mouth, Turn, Ear and PhoneAudio wired the way server.py wires them."""

    def __init__(self, clock=time.monotonic, stt: Optional[FakeSTT] = None, pool: Any = None, speak=None) -> None:
        self.clock = clock
        self.sent: list[dict] = []
        self.trace = FakeTrace()
        self.mouth = Mouth(self.sent.append, "MZ1", clock=clock)
        self.ear = Ear(stt=stt or FakeSTT())
        self.turn = Turn(self.mouth, ear=self.ear, trace=self.trace, clock=clock)
        self.phone = PhoneAudio(
            FakeCorpus(), pool if pool is not None else FakePool(), self.mouth, self.turn,
            close=lambda: None, trace=self.trace, speak=speak,
        )

    def marks_back(self) -> None:
        for mark in list(self.mouth._pending):
            self.mouth.on_mark(mark)

    def voice(self, loud: int, quiet: int = 0) -> None:
        for _ in range(loud):
            self.ear.push_media(LOUD, is_ulaw=False)
        for _ in range(quiet):
            self.ear.push_media(QUIET, is_ulaw=False)


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(tunables, "KEY_GUARD_MS", 0)
    monkeypatch.setattr(tunables, "SILENCE_GAP_S", 0.3)
    monkeypatch.setattr(tunables, "SILENCE_REMIND_S", 0.3)
    monkeypatch.setattr(tunables, "SILENCE_HANGUP_S", 0.6)
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", True)


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def _later(delay: float, fn, *args) -> None:
    threading.Timer(delay, fn, args).start()


# --- A1: the stamp names the clip that is really sounding --------------------------------


def test_a1_a_key_during_scheme_one_is_stamped_with_scheme_one_but_still_answers():
    clock = Clock()
    line = Line(clock=clock)
    line.phone.say(("preamble",))
    line.phone.say(("scheme_1",))
    line.phone.say(("anything_else",))   # prompt_n is now 3
    clock.t += 10.0                      # long after the guard window
    first_mark = sorted(line.mouth._pending)[0]
    line.mouth.on_mark(first_mark)       # the preamble is done; scheme_1 sounds
    line.turn.push_key("1")
    key = line.turn.get_valid_key()
    assert key is not None and key.digit == "1"          # judged against what the engine waits on
    row = line.trace.rows[-1]
    assert (row["event"], row["took"]) == ("key", True)
    assert (row["prompt"], row["prompt_n"], row["cut_clip"]) == ("scheme_1", 2, "scheme_1")


def test_a1_a_hangup_is_stamped_with_the_clip_that_sounded():
    clock = Clock()
    line = Line(clock=clock)
    line.phone.say(("preamble",))
    line.phone.say(("anything_else",))
    line.turn.push_hangup()
    row = line.trace.rows[-1]
    assert (row["event"], row["prompt"], row["prompt_n"]) == ("hangup", "preamble", 1)


# --- A2: heard(token) ---------------------------------------------------------------------


def test_a2_heard_after_its_mark_or_its_time_but_not_after_a_cut():
    clock = Clock()
    line = Line(clock=clock, pool=FakePool(1.0))
    line.phone.say(("a",))
    assert line.phone.heard("a") is False            # still playing
    clock.t += 1.5                                   # its time ran out, no clear
    assert line.phone.heard("a") is True

    line.phone.say(("b",))
    clock.t += 0.5
    line.mouth.clear()                               # cut half way
    assert line.phone.heard("b") is False

    line.phone.say(("c",))
    line.mouth.on_mark(sorted(line.mouth._pending)[0])
    assert line.phone.heard("c") is True             # mark came back, clock not moved


# --- B: the English pipe ------------------------------------------------------------------


class _FakeResponse:
    status_code = 200

    def json(self) -> dict:
        return {"transcript": "hello", "language_code": "hi-IN"}


def _fake_client(sent: list[dict]):
    class Client:
        def __init__(self, **kw: Any) -> None:
            pass

        def __enter__(self) -> "Client":
            return self

        def __exit__(self, *a: Any) -> None:
            pass

        def post(self, url: str, headers: dict, data: dict, files: dict) -> _FakeResponse:
            sent.append(data)
            return _FakeResponse()

    return Client


def test_b1_off_the_request_is_as_before(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", False)
    monkeypatch.setattr(ear_mod.httpx, "Client", _fake_client(sent))
    res = SarvamSTT(api_key="k", model="saaras:v4").transcribe(b"wav", lang="hi")
    assert sent == [{"model": "saaras:v4", "mode": "transcribe", "language_code": "hi-IN"}]
    assert res.english is False


def test_b1_on_it_translates_and_keeps_the_callers_language(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)
    monkeypatch.setattr(ear_mod.httpx, "Client", _fake_client(sent))
    res = SarvamSTT(api_key="k", model="saaras:v4").transcribe(b"wav", lang="hi")
    assert sent == [{"model": "saaras:v4", "mode": "translate", "language_code": "hi-IN"}]
    assert (res.english, res.lang) == (True, "hi-IN")


def test_b1_the_speech_the_ear_gives_carries_english_and_lang(monkeypatch):
    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)
    ear = Ear(stt=FakeSTT(SttResult(transcript="how much", lang="hi-IN", english=True)))
    _burst(ear, loud=10, quiet=45)
    got = ear.listen(timeout=1.0)
    assert got == Speech(text="how much", lang="hi-IN", english=True)


def test_b2_the_groq_backup_gives_the_callers_language(monkeypatch):
    class Client(_fake_client([])):
        def post(self, url: str, headers: dict, data: dict, files: dict) -> Any:
            class R:
                status_code = 200

                def json(self) -> dict:
                    return {"text": "kisan", "language": "hindi"}

            return R()

    monkeypatch.setattr(tunables, "ENGLISH_PIPE", True)
    monkeypatch.setattr(ear_mod.httpx, "Client", Client)
    res = GroqWhisperSTT(api_key="k").transcribe(b"wav", lang="hi")
    assert (res.english, res.lang) == (False, "hi-IN")


def _burst(ear: Ear, loud: int, quiet: int) -> None:
    for _ in range(loud):
        ear.push_media(LOUD, is_ulaw=False)
    for _ in range(quiet):
        ear.push_media(QUIET, is_ulaw=False)


# --- C: saying an answer ------------------------------------------------------------------


def _said(line: Line) -> list[str]:
    return [m["mark"]["name"].split(":", 1)[1] for m in line.sent if m.get("event") == "mark"]


def test_c3_off_it_says_nothing_and_does_not_ask_for_sound(monkeypatch):
    monkeypatch.setattr(tunables, "QA_SPEAK", False)
    asked: list[str] = []
    line = Line(speak=lambda t, l: asked.append(t) or b"\x55" * 8000)
    assert line.phone.say_text("छह हज़ार रुपये मिलते हैं।") is False
    assert asked == [] and line.sent == []


def test_c3_on_the_answer_plays_as_a_clip_and_a_key_cuts_it(monkeypatch):
    monkeypatch.setattr(tunables, "QA_SPEAK", True)
    line = Line(pool=_NoPool(), speak=lambda t, l: b"\x55" * 24000)
    assert line.phone.say_text("Six thousand rupees a year.") is True
    assert _said(line) == ["answer"]
    time.sleep(0.01)
    line.turn.push_key("5")
    assert line.mouth.last_cut[0] == "answer"
    assert line.phone.heard("answer") is False


def test_c3_no_sound_in_time_gives_false(monkeypatch):
    monkeypatch.setattr(tunables, "QA_SPEAK", True)
    line = Line(pool=_NoPool(), speak=lambda t, l: None)
    assert line.phone.say_text("anything") is False
    assert line.sent == []


def test_c2_the_same_answer_is_not_asked_for_twice(monkeypatch, tmp_path):
    monkeypatch.setattr(tunables, "QA_SPEAK", True)
    asked: list[str] = []

    def speak(text: str, lang: str) -> bytes:
        asked.append(text)
        return b"\x55" * 16000

    line = Line(pool=AudioPool(audio_dir=tmp_path, tier2="none"), speak=speak)
    assert line.phone.say_text("Six thousand rupees a year.") is True
    line.mouth.clear()
    assert line.phone.say_text("Six thousand rupees a year.") is True
    assert len(asked) == 1
    assert len(list(tmp_path.glob("*.ulaw"))) == 1


class _NoPool:
    """No saved answers and nowhere to save them."""

    audio_dir = "/nonexistent-for-tests"

    def get(self, key: str) -> bytes:
        raise KeyError(key)


def test_c1_clean_text_and_streamed_bytes(monkeypatch):
    assert live_tts.clean("**50%** ‑ दर", "hi") == "50 प्रतिशत - दर"
    assert live_tts.clean("see [here](http://x) now", "en") == "see here now"

    class Resp:
        status_code = 200

        def __init__(self, chunks: list[bytes]) -> None:
            self.chunks = chunks

        def __enter__(self) -> "Resp":
            return self

        def __exit__(self, *a: Any) -> None:
            pass

        def iter_bytes(self):
            yield from self.chunks

    monkeypatch.setenv("SARVAM_API_KEY", "k")
    monkeypatch.setattr(live_tts, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(live_tts.httpx, "stream", lambda *a, **k: Resp([b"\x01\x02", b"\x03"]))
    assert live_tts.speak("hello", "en") == b"\x01\x02\x03"

    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("network down")

    monkeypatch.setattr(live_tts.httpx, "stream", boom)
    assert live_tts.speak("hello", "en") is None
    monkeypatch.delenv("SARVAM_API_KEY")
    assert live_tts.speak("hello", "en") is None


# --- D: the caller's voice stops a clip (S1-S8) --------------------------------------------


def _play_prompt(line: Line, name: str = "prompt", sec: float = 3.0) -> None:
    line.phone.pool = FakePool(sec)
    line.phone.say((name,))


@pytest.mark.parametrize("profile", ["spoken", "confirm", "readback"])
def test_s1_voice_for_400_ms_stops_the_clip_and_one_speech_is_given(monkeypatch, profile):
    monkeypatch.setattr(tunables, "QA_ENABLED", True)
    line = Line()
    _play_prompt(line)
    _later(0.05, line.voice, 25, 45)       # 500 ms of voice, then quiet
    got = line.phone.next_input(profile)
    assert isinstance(got, Speech) and got.text == "kisan ke baare mein"
    assert got.cut_clip == "prompt" and got.heard_ms >= 0
    assert line.mouth.playing is False
    assert (True, "cut_in") in line.trace.why("speech")


def test_s2_a_short_burst_does_not_stop_the_clip():
    line = Line()
    _play_prompt(line, sec=0.6)
    _later(0.05, line.voice, 5, 45)        # 100 ms of voice
    _later(0.4, line.marks_back)
    got = line.phone.next_input("spoken")
    assert isinstance(got, Silence)
    assert line.mouth.last_cut == ("", -1)
    assert line.trace.why("speech") == [(False, "short_voice")]


def test_s3_voice_in_the_guard_window_is_ignored(monkeypatch):
    monkeypatch.setattr(tunables, "KEY_GUARD_MS", 5000)
    line = Line()
    _play_prompt(line, sec=0.6)
    line.turn.prompt_start_t = time.monotonic()
    _later(0.05, line.voice, 30, 45)
    _later(0.4, line.marks_back)
    got = line.phone.next_input("spoken")
    assert not isinstance(got, Speech)
    assert line.mouth.last_cut == ("", -1)


def test_s4_a_key_after_the_voice_wins_and_the_words_are_dropped():
    line = Line()
    _play_prompt(line)

    def voice_then_key() -> None:
        line.voice(25)                     # voice goes on, no end yet
        while line.mouth.last_cut[0] == "":
            time.sleep(0.01)
        line.turn.push_key("2")

    _later(0.05, voice_then_key)
    got = line.phone.next_input("spoken")
    assert isinstance(got, Digit) and got.digit == "2"
    assert (False, "key_beat_speech") in line.trace.why("speech")


def test_s5_the_greeting_and_a_normal_profile_do_not_hear_the_voice():
    for profile in ("turn0", "normal"):
        line = Line()
        _play_prompt(line, sec=0.6)
        _later(0.05, line.voice, 30, 45)
        _later(0.4, line.marks_back)
        got = line.phone.next_input(profile)
        assert not isinstance(got, Speech)
        assert line.mouth.last_cut == ("", -1)


def test_s6_keypad_only_does_not_hear_the_voice():
    line = Line()
    line.ear.force_stt_failure()
    _play_prompt(line, sec=0.6)
    _later(0.05, line.voice, 30, 45)
    _later(0.4, line.marks_back)
    got = line.phone.next_input("spoken")
    assert isinstance(got, Silence)
    assert line.mouth.last_cut == ("", -1)


def test_s7_the_caller_can_cut_an_answer(monkeypatch):
    monkeypatch.setattr(tunables, "QA_SPEAK", True)
    line = Line(pool=_NoPool(), speak=lambda t, l: b"\x55" * 40000)
    assert line.phone.say_text("Six thousand rupees a year.") is True
    _later(0.05, line.voice, 25, 45)
    got = line.phone.next_input("confirm")
    assert isinstance(got, Speech) and got.cut_clip == "answer"


def test_s8_a_hangup_during_the_voice_is_its_own_event():
    line = Line()
    _play_prompt(line)

    def voice_then_hangup() -> None:
        line.voice(10)
        line.turn.push_hangup()

    _later(0.05, voice_then_hangup)
    got = line.phone.next_input("spoken")
    assert isinstance(got, Hangup)
    assert [r["event"] for r in line.trace.rows if r["event"] == "hangup"] == ["hangup"]
    assert not any(r["event"] == "key" for r in line.trace.rows)


def test_switch_off_the_voice_does_not_stop_the_clip(monkeypatch):
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", False)
    line = Line()
    _play_prompt(line, sec=0.6)
    _later(0.05, line.voice, 30, 45)
    _later(0.4, line.marks_back)
    got = line.phone.next_input("spoken")
    assert not isinstance(got, Speech)
    assert line.mouth.last_cut == ("", -1)


# --- 7.14: the live voice plays as its sound arrives --------------------------------------


def _media(line: Line) -> list[str]:
    return [m["event"] for m in line.sent]


def test_s14_a_new_sentence_is_sent_piece_by_piece_as_one_clip_and_saved_whole(monkeypatch, tmp_path):
    monkeypatch.setattr(tunables, "QA_SPEAK", True)
    monkeypatch.setattr(tunables, "LIVE_TTS_STREAM", True)
    seen: list[int] = []
    order: list[str] = []
    line = Line(pool=AudioPool(audio_dir=tmp_path, tier2="none"))

    def stream(text: str, lang: str):
        for piece in (b"\x11" * 800, b"\x22" * 800, b"\x33" * 400):
            yield piece
            seen.append(len([m for m in line.sent if m.get("event") == "media"]))

    monkeypatch.setattr(live_tts, "stream", stream)
    assert line.phone.say_text("Six thousand rupees a year.", on_first=lambda: order.append(str(len(line.sent)))) is True
    assert order == ["0"]                               # called before the first sound is sent
    assert seen == [1, 2, 3]                            # each piece went out before the next one came
    assert _media(line) == ["media", "media", "media", "mark"] and _said(line) == ["answer"]
    assert abs(line.mouth.remaining() - 0.25) < 0.05    # one clip, 2000 bytes long
    saved = list(tmp_path.glob("*.ulaw"))
    assert len(saved) == 1 and saved[0].read_bytes() == b"\x11" * 800 + b"\x22" * 800 + b"\x33" * 400
    line.mouth.clear()
    monkeypatch.setattr(live_tts, "stream", lambda t, l: (_ for _ in ()).throw(AssertionError))
    assert line.phone.say_text("Six thousand rupees a year.") is True      # the saved sound, no new ask


def test_s14_a_stream_with_no_sound_says_nothing_and_one_that_breaks_is_not_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(tunables, "QA_SPEAK", True)
    monkeypatch.setattr(tunables, "LIVE_TTS_STREAM", True)
    line = Line(pool=AudioPool(audio_dir=tmp_path, tier2="none"))

    def fails(text: str, lang: str):
        raise RuntimeError("http 500")
        yield b""

    monkeypatch.setattr(live_tts, "stream", fails)
    first: list[int] = []
    assert line.phone.say_text("anything", on_first=lambda: first.append(1)) is False
    assert line.sent == [] and first == []

    def breaks(text: str, lang: str):
        yield b"\x11" * 800
        raise TimeoutError("too slow")

    monkeypatch.setattr(live_tts, "stream", breaks)
    assert line.phone.say_text("anything") is True
    assert _media(line) == ["media", "mark"] and list(tmp_path.glob("*.ulaw")) == []


def test_s14_a_clear_stops_the_sending_and_off_is_as_before(monkeypatch):
    monkeypatch.setattr(tunables, "QA_SPEAK", True)
    monkeypatch.setattr(tunables, "LIVE_TTS_STREAM", True)
    line = Line(pool=_NoPool())

    def pieces():
        yield b"\x11" * 800
        line.mouth.clear()
        yield b"\x22" * 800

    assert line.mouth.play_stream("answer", pieces()) == b"\x11" * 800 + b"\x22" * 800
    assert _media(line) == ["media", "clear"] and line.mouth.remaining() == 0.0

    monkeypatch.setattr(tunables, "LIVE_TTS_STREAM", False)
    off = Line(pool=_NoPool())
    monkeypatch.setattr(live_tts, "speak", lambda t, l: b"\x55" * 1600)
    monkeypatch.setattr(live_tts, "stream", lambda t, l: (_ for _ in ()).throw(AssertionError))
    assert off.phone.say_text("Six thousand rupees a year.") is True
    assert _media(off) == ["media", "mark"]


def test_s14_stream_gives_the_pieces_and_speak_is_their_join(monkeypatch):
    class Resp:
        status_code = 200

        def __init__(self, pieces):
            self.pieces = pieces

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_bytes(self):
            return iter(self.pieces)

    monkeypatch.setenv("SARVAM_API_KEY", "k")
    monkeypatch.setattr(live_tts.httpx, "stream", lambda *a, **k: Resp([b"\x01\x02", b"", b"\x03"]))
    assert list(live_tts.stream("hello", "en")) == [b"\x01\x02", b"\x03"]
    assert live_tts.speak("hello", "en") == b"\x01\x02\x03"
    bad = Resp([])
    bad.status_code = 500
    monkeypatch.setattr(live_tts.httpx, "stream", lambda *a, **k: bad)
    assert live_tts.speak("hello", "en") is None


# --- 7.14 (B5): cut-in with a strict gate in a talk call -----------------------------------


def _gate_line(monkeypatch, words: str, false_max: int = 2) -> Line:
    monkeypatch.setattr(tunables, "SPEECH_CUT_IN", False)
    monkeypatch.setattr(tunables, "CUT_IN_GATE", True)
    monkeypatch.setattr(tunables, "TALK_ONLY", True)
    monkeypatch.setattr(tunables, "QA_SPEAK", True)
    monkeypatch.setattr(tunables, "LIVE_TTS_STREAM", False)
    monkeypatch.setattr(tunables, "CUT_IN_FALSE_MAX", false_max)
    line = Line(stt=FakeSTT(SttResult(transcript=words, lang="hi-IN")), pool=_NoPool(),
                speak=lambda t, l: b"\x55" * 40000)
    assert line.phone.say_text("First sentence of the reply.") and line.phone.say_text("Second sentence.")
    return line


def _clears(line: Line) -> int:
    return len([m for m in line.sent if m.get("event") == "clear"])


def test_g1_real_words_counts_only_words_that_are_more_than_a_listening_sound():
    from haqdaar.audio.turn import real_words

    assert real_words("हम्म, अच्छा।") == 0 and real_words("ok ok") == 0 and real_words("") == 0
    assert real_words("हम्म रुको") == 1
    assert real_words("रुको रुको, एक मिनट") == 4 and real_words("Wait, stop.") == 2


def test_g2_half_a_second_of_voice_does_not_pause_the_agent(monkeypatch):
    line = _gate_line(monkeypatch, "ruko ek minute")
    _later(0.05, line.voice, 25, 45)                  # 500 ms: under the 600 ms gate
    _later(0.4, line.marks_back)
    got = line.phone.next_input("spoken")
    assert not isinstance(got, Speech) and _clears(line) == 0 and _said(line) == ["answer", "answer"]


def test_g3_a_cut_with_under_two_real_words_says_the_cut_sentence_again_and_the_rest(monkeypatch):
    line = _gate_line(monkeypatch, "हम्म, अच्छा।")
    _later(0.05, line.voice, 40, 45)                  # 800 ms of voice
    _later(0.5, line.marks_back)
    got = line.phone.next_input("spoken")
    assert isinstance(got, Silence)                   # no turn was made of it
    assert _clears(line) == 1 and _said(line) == ["answer"] * 4
    assert (False, "false_cut") in line.trace.why("speech")
    assert line.phone.say_cut_again() is False        # nothing is kept aside


def test_g4_two_real_words_are_the_callers_turn_and_the_cut_reply_can_be_said_again(monkeypatch):
    line = _gate_line(monkeypatch, "ruko ek minute")
    _later(0.05, line.voice, 40, 45)
    got = line.phone.next_input("spoken")
    assert isinstance(got, Speech) and got.text == "ruko ek minute" and got.cut_clip == "answer"
    assert _clears(line) == 1 and line.mouth.playing is False
    line.phone.say(("one_moment",))                   # the Mouth forgets its own copy here
    assert line.phone.say_cut_again() is True
    assert _said(line)[-2:] == ["answer", "answer"] and line.phone.say_cut_again() is False


def test_g5_after_the_cap_the_rest_of_the_reply_is_said_with_strict_turns(monkeypatch):
    line = _gate_line(monkeypatch, "hmm", false_max=1)
    _later(0.05, line.voice, 40, 45)                  # cut 1: said again, then no more cuts
    _later(0.45, line.voice, 40, 45)
    _later(0.9, line.marks_back)
    got = line.phone.next_input("spoken")
    assert not isinstance(got, Speech) or got.cut_clip == ""
    assert _clears(line) == 1 and _said(line) == ["answer"] * 4


def test_g6_off_the_agent_does_not_listen_while_it_talks(monkeypatch):
    line = _gate_line(monkeypatch, "ruko ek minute")
    monkeypatch.setattr(tunables, "CUT_IN_GATE", False)
    _later(0.05, line.voice, 40, 45)
    _later(0.4, line.marks_back)
    line.phone.next_input("spoken")
    assert _clears(line) == 0 and _said(line) == ["answer", "answer"]


def test_g7_silero_calls_a_voice_a_voice_and_a_noise_a_noise(tmp_path):
    import math
    import random
    import shutil
    import struct
    import subprocess

    from haqdaar.audio.ear import EnergyVAD
    from haqdaar.audio.silero import make

    vad = make()
    assert vad is not None

    def voiced_ms(v, pcm: bytes) -> int:
        v.reset()
        n = 0
        for i in range(0, len(pcm) - 319, 320):
            v.feed_frame(pcm[i:i + 320])
            n += v.last_level >= v.end_rms
        return n * 20

    rnd = random.Random(1)
    size = 16000
    noises = {
        "hiss": [int(rnd.gauss(0, 3000)) for _ in range(size)],
        "tone": [int(4000 * math.sin(2 * math.pi * 440 * i / 8000)) for i in range(size)],
        "claps": [int(rnd.gauss(0, 9000)) if i % 4000 < 400 else 0 for i in range(size)],
    }
    for name, samples in noises.items():
        pcm = struct.pack(f"<{size}h", *[max(-32000, min(32000, s)) for s in samples])
        assert voiced_ms(EnergyVAD(), pcm) >= 200, name      # the loudness check takes it for a voice
        assert voiced_ms(vad, pcm) == 0 and not vad.started, name
    if not (shutil.which("say") and shutil.which("afconvert")):
        pytest.skip("no Mac voice to test with")
    aiff, wav = tmp_path / "a.aiff", tmp_path / "a.wav"
    subprocess.run(["say", "-o", str(aiff), "wait wait, one minute please"], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@8000", "-c", "1", str(aiff), str(wav)], check=True)
    assert voiced_ms(vad, wav.read_bytes()[44:]) >= 600 and vad.started
