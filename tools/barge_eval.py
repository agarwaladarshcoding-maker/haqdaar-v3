"""Cut-in (barge-in) check: the real call on a virtual clock (step 7.9).

What is real: Engine.run_call, PhoneAudio, Turn, Mouth, Ear and its voice detector.
What is fake: the edges only.
  - the clock: `time` inside turn / ear / phone is swapped, and the two queues the audio
    code waits on move the clock when they are empty. One thread, no real waiting, so a
    run is the same every time and thousands of calls take seconds.
  - the phone line: plays what the Mouth sends, sends each mark back when the clip ends,
    and feeds one 20 ms frame of caller sound all the time (quiet, loud while they talk).
  - speech-to-text, the model and live speech: fixed rules, each costs clock time.

How places are found: the plain call is run once and EVERY clip it played is a place. Each
scenario is that same call with one thing put in at one moment inside one clip.

    make barge-eval            # whole matrix, writes scratch/barge-eval/
    make barge-eval ARGS=--quick
"""
from __future__ import annotations

import argparse
import base64
import heapq
import json
import os
import queue
import statistics
import struct
import sys
import tempfile
import time as real_time
import zlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from haqdaar.audio import ear as ear_mod
from haqdaar.audio import phone as phone_mod
from haqdaar.audio import turn as turn_mod
from haqdaar.audio.ear import Ear, SttResult
from haqdaar.audio.mouth import Mouth
from haqdaar.audio.phone import PhoneAudio
from haqdaar.audio.turn import Turn
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Answer, Question, Repeat, Unclear
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.engine.call import Engine

FRAME_S = 0.02
T0 = 1000.0              # the virtual clock starts here
MAX_WAITS = 200          # a call that asks more often than this is stuck
MAX_CALL_S = 900.0       # a call longer than this (virtual) is stuck
REACT_S = 0.5            # the plain caller answers this long after a prompt ends
STT_S = 0.35             # what speech-to-text costs
MODEL_S = 0.5            # what one model call costs
ANSWER_S = 1.2           # what writing an answer costs
TTS_S = 0.7              # what live speech costs
LOUD, QUIET = 3000, 0


def _frame(level: int) -> bytes:
    """One 20 ms frame of 16-bit sound at this loudness (a square wave, so rms == level)."""
    return struct.pack("<2h", level, -level) * 80 if level else b"\x00" * 320


# --- the virtual world -----------------------------------------------------------------


class Stuck(Exception):
    pass


class World:
    """The clock, the things due to happen, and the caller's side of the line."""

    def __init__(self) -> None:
        self.now = T0
        self._heap: list[tuple[float, int, Callable[[], Any]]] = []
        self._seq = 0
        self._next_frame = self.now
        self.frames_on = True
        self.talk: list[tuple[float, float, int]] = []   # caller sound: start, end, level
        self.echo_level = 0
        self.bed = QUIET          # the sound of the place the caller is in, all the time
        self.line: Any = None
        self.turn: Any = None
        self._busy = False

    def at(self, t: float, fn: Callable[[], Any]) -> None:
        self._seq += 1
        heapq.heappush(self._heap, (max(t, self.now), self._seq, fn))

    def next_time(self) -> Optional[float]:
        times = []
        if self._heap:
            times.append(self._heap[0][0])
        if self.frames_on:
            times.append(self._next_frame)
        return min(times) if times else None

    def _level(self, t: float) -> int:
        level = self.bed
        for a, b, lv in self.talk:
            if a <= t < b:
                level = max(level, lv)
        if self.echo_level and self.line is not None and self.line.sounding(t):
            level = max(level, self.echo_level)
        return level

    def advance_to(self, t: float) -> None:
        if self._busy:   # something that happens on the line never moves the clock itself
            return
        if t - T0 > MAX_CALL_S:
            raise Stuck(f"the call ran past {MAX_CALL_S:.0f} s")
        while True:
            ev_t = self._heap[0][0] if self._heap else None
            fr_t = self._next_frame if self.frames_on else None
            if ev_t is not None and ev_t <= t and (fr_t is None or ev_t <= fr_t):
                _, _, fn = heapq.heappop(self._heap)
                self.now = max(self.now, ev_t)
                self._busy = True
                try:
                    fn()
                finally:
                    self._busy = False
            elif fr_t is not None and fr_t <= t:
                self.now = max(self.now, fr_t)
                self._next_frame = fr_t + FRAME_S
                if self.turn is not None:
                    self.turn.push_media(_frame(self._level(fr_t)), is_ulaw=False)
            else:
                break
        self.now = max(self.now, t)


class FakeTime:
    """Stands in for the `time` module inside the audio code."""

    def __init__(self, world: World) -> None:
        self._w = world

    def monotonic(self) -> float:
        return self._w.now

    def time(self) -> float:
        return self._w.now

    def sleep(self, s: float) -> None:
        self._w.advance_to(self._w.now + s)

    def __getattr__(self, name: str) -> Any:
        return getattr(real_time, name)


class VQueue(queue.Queue):
    """A queue whose blocking get() moves the virtual clock instead of sleeping."""

    def __init__(self, world: World) -> None:
        super().__init__()
        self._w = world

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Any:
        if not block:
            return super().get(False)
        deadline = None if timeout is None else self._w.now + timeout
        while True:
            try:
                return super().get(False)
            except queue.Empty:
                pass
            nt = self._w.next_time()
            if deadline is not None and (nt is None or nt > deadline):
                self._w.advance_to(deadline)
                return super().get(False)   # raises queue.Empty when still nothing
            if nt is None:
                raise Stuck("waiting on a queue that nothing will ever fill")
            self._w.advance_to(nt)


class Line:
    """The phone line going out: what the caller hears, and when."""

    def __init__(self, world: World) -> None:
        self._w = world
        self.clips: list[dict[str, Any]] = []
        self.clears: list[float] = []
        self.play_end = world.now
        self._gen = 0
        self._cur_start: Optional[float] = None
        self.on_mark: Callable[[str], Any] = lambda name: None
        self.closed_at: Optional[float] = None

    def emit(self, msg: dict[str, Any]) -> None:
        now = self._w.now
        ev = msg.get("event")
        if ev == "media":
            n = len(base64.b64decode(msg["media"]["payload"]))
            start = max(now, self.play_end)
            if self._cur_start is None:
                self._cur_start = start
            self.play_end = start + n / tunables.SAMPLE_RATE
        elif ev == "mark":
            mark = msg["mark"]["name"]
            start = self._cur_start if self._cur_start is not None else max(now, self.play_end)
            self._cur_start = None
            self.clips.append({"name": mark.split(":", 1)[-1], "start": start, "end": self.play_end,
                               "cut_at": None, "i": len(self.clips), "sent": now})
            gen = self._gen
            self._w.at(self.play_end, lambda: self.on_mark(mark) if gen == self._gen else None)
        elif ev == "clear":
            self._gen += 1
            self.clears.append(now)
            for c in self.clips:
                if c["cut_at"] is None and c["end"] > now:
                    c["cut_at"] = now
            self.play_end = now
            self._cur_start = None

    def sounding(self, t: float) -> Optional[dict[str, Any]]:
        for c in reversed(self.clips):
            end = c["cut_at"] if c["cut_at"] is not None else c["end"]
            if c["start"] <= t < end:
                return c
        return None


class Rec:
    """The trace: every line the audio code logs and every input row, with the virtual time."""

    def __init__(self, world: World) -> None:
        self._w = world
        self.lines: list[tuple[float, str]] = []
        self.rows: list[dict[str, Any]] = []
        self.log_rows: list[dict[str, Any]] = []

    def __call__(self, line: str) -> None:
        self.lines.append((self._w.now, line))

    def input_event(self, **kw: Any) -> None:
        self.rows.append({"t": self._w.now, **kw})

    def record(self, row: Any) -> None:
        if isinstance(row, str):
            try:
                row = json.loads(row)
            except ValueError:
                row = {"raw": row}
        if isinstance(row, dict):
            self.log_rows.append({"t": self._w.now, **row})


class Caller:
    """The person on the phone. Answers each wait from a script; a scenario adds one more thing."""

    def __init__(self, world: World, script: list[Any]) -> None:
        self._w = world
        self.script = list(script)
        self.waits = 0
        self.wait_log: list[dict[str, Any]] = []
        self.said: list[dict[str, Any]] = []     # every utterance: t0, t1, words by time
        self.keys: list[tuple[float, str]] = []
        self.hung_up_at: Optional[float] = None
        self._token = 0
        self._ix = 0

    # -- things the caller does ---------------------------------------------------------
    def press(self, digit: str) -> None:
        self.keys.append((self._w.now, digit))
        self._w.turn.push_key(digit)

    def speak(self, t0: float, dur: float, text: str, level: int = LOUD) -> None:
        words = text.split()
        step = dur / (len(words) + 1) if words else 0.0
        self.said.append({"t0": t0, "t1": t0 + dur, "text": text, "level": level,
                          "words": [(t0 + step * (i + 1), w) for i, w in enumerate(words)]})
        self._w.talk.append((t0, t0 + dur, level))

    def hang_up(self) -> None:
        if self.hung_up_at is None:
            self.hung_up_at = self._w.now
            self._w.turn.push_hangup()
            self._w.frames_on = False

    def take_words(self, since: float, now: float) -> str:
        """What speech-to-text gives back: the words said inside the sound it was handed.
        Words said earlier, while nobody listened, are gone."""
        out: list[str] = []
        for u in self.said:
            while u["words"] and u["words"][0][0] <= now:
                t, w = u["words"].pop(0)
                if t >= since:
                    out.append(w)
        return " ".join(out)

    # -- the plain script ---------------------------------------------------------------
    def on_wait(self, profile: str) -> None:
        self.waits += 1
        if self.waits > MAX_WAITS:
            raise Stuck(f"more than {MAX_WAITS} waits")
        self._token += 1
        token = self._token
        if self._ix < len(self.script):
            item = self.script[self._ix]
        else:
            item = "2" if self.waits < 60 else "h"
        self._ix += 1
        self.wait_log.append({"t": self._w.now, "profile": profile, "plan": item})
        if item == "s":
            return

        def act() -> None:
            if token != self._token:
                return
            if self._w.line.play_end > self._w.now - REACT_S + 1e-6:   # still talking: wait for the end
                self._w.at(self._w.line.play_end + REACT_S, act)
            elif isinstance(item, tuple):          # ("say", text, seconds)
                self.speak(self._w.now, item[2], item[1])
            elif item == "h":
                self.hang_up()
            else:
                self.press(item)

        self._w.at(self._w.now + 0.01, act)

    def drop_plan(self) -> None:
        """The scenario's own input answers this wait: the scripted answer for it is not given."""
        self._token += 1


class FakeSTT:
    def __init__(self, world: World, caller: Caller) -> None:
        self._w, self._caller = world, caller
        self.calls = 0
        self.fail = False

    def reset_circuit(self) -> None:
        pass

    def transcribe(self, audio_bytes: bytes, lang: str = "", hint: str = "", is_wav: bool = False) -> SttResult:
        self.calls += 1
        self._w.advance_to(self._w.now + STT_S)
        if self.fail:
            return SttResult(transcript="", lang=lang, provider="fake", success=False, error="timeout",
                             latency_s=STT_S)
        heard_s = len(audio_bytes) / 2 / tunables.SAMPLE_RATE   # 16-bit sound
        since = self._w.now - STT_S - heard_s - 0.3
        return SttResult(transcript=self._caller.take_words(since, self._w.now), lang=lang or "en",
                         provider="fake", success=True, latency_s=STT_S)


class EvalModel:
    """Sorts words by fixed rules (same rules as the sweep test), and costs clock time."""
    keypad_only = False

    def __init__(self, world: World) -> None:
        self._w = world
        self.answers = 0

    def _cost(self, s: float) -> None:
        self._w.advance_to(self._w.now + s)

    def turn(self, transcript: str, box: Any = None, ask_count: int = 0, **kw: Any) -> Any:
        self._cost(MODEL_S)
        t = transcript.lower()
        if t.endswith("?"):
            return Question()
        if "again" in t:
            return Repeat()
        if "woman" in t and box == "gender":
            return Answer(box="gender", value="female", span="woman")
        return Unclear(reason="unclear")

    def opener(self, transcript: str, lang: str = "en", **kw: Any) -> Any:
        self._cost(MODEL_S)
        return Unclear(reason="unclear")

    def confirm(self, text: str, lang: Any = None, **kw: Any) -> Optional[bool]:
        self._cost(MODEL_S)
        t = text.lower().strip()
        return True if t in ("yes", "haan", "ho") else False if t in ("no", "nahi") else None

    def sort(self, asked: str, transcript: str, **kw: Any) -> str:
        self._cost(MODEL_S)
        return "QUESTION" if transcript.strip().endswith("?") else "OTHER"

    def answer(self, question: str, lang: str, cards: Any, **kw: Any) -> Optional[str]:
        self._cost(ANSWER_S)
        self.answers += 1
        return None if "gold" in question else "It gives fifty percent subsidy."


class Pool:
    """Every clip is 1.2 to 2.5 s of sound; the same key is always the same length."""

    def __init__(self, audio_dir: str) -> None:
        self.audio_dir = audio_dir

    def get(self, key: str) -> bytes:
        sec = 1.2 + (zlib.crc32(key.encode()) % 14) / 10.0
        return b"\x55" * int(tunables.SAMPLE_RATE * sec)

    def prefetch(self, keys: Any) -> None:
        pass


# --- one call --------------------------------------------------------------------------

_CORPUS: Optional[Corpus] = None
_TMP: Optional[tempfile.TemporaryDirectory] = None


def corpus() -> Corpus:
    """The fixture snapshot, built once per process (same data `make sim` uses)."""
    global _CORPUS, _TMP
    if _CORPUS is None:
        root = Path(__file__).resolve().parent.parent
        schemes = []
        for line in (root / "fixtures" / "schemes.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row.get("scheme_id") != "S6":
                    schemes.append(row)
        _TMP = tempfile.TemporaryDirectory()
        snap, aud = Path(_TMP.name) / "snapshots", Path(_TMP.name) / "audio"
        snap.mkdir()
        aud.mkdir()
        (Path(_TMP.name) / "logs").mkdir()
        # Point the loader at the throwaway folders only while it loads: this module also runs
        # inside pytest, and the other tests must find the real folders afterwards.
        saved = (tunables.SNAPSHOTS_DIR, tunables.AUDIO_DIR)
        tunables.SNAPSHOTS_DIR, tunables.AUDIO_DIR = str(snap), str(aud)
        try:
            sid = build_snapshot(schemes_data=schemes, snapshot_id="barge_eval_snap", snapshots_dir=snap,
                                 audio_dir=aud, render_stubs=True)
            _CORPUS = Corpus.load(sid)
        finally:
            tunables.SNAPSHOTS_DIR, tunables.AUDIO_DIR = saved
    return _CORPUS


FLAGS = {
    "keys_only": dict(SPEECH_CUT_IN=False, QA_ENABLED=False, QA_SPEAK=False),   # today's default
    "voice": dict(SPEECH_CUT_IN=True, QA_ENABLED=False, QA_SPEAK=False),
    "voice_qa": dict(SPEECH_CUT_IN=True, QA_ENABLED=True, QA_SPEAK=True),       # the phone-check set
}

# The plain calls. First item answers the greeting. "s" = stay quiet, ("say", words, seconds).
Q = ("say", "what does the tractor subsidy give?", 1.6)
SCRIPTS: dict[str, list[Any]] = {
    "keys": ["2", "1", "2", "1", "3", "1", "9", "1", "9", "9", "0", "2"],
    "spoken": ["2", "1", ("say", "I am a woman", 1.0), ("say", "yes", 0.5), "1", "3", "1", "9", "9", "0",
               ("say", "no", 0.5)],
    "question": ["2", "1", "2", "1", "3", Q, "1", Q, "9", "9", "0", "2"],
    "quiet": ["2", "s", "1", "2", "s", "1", "3", "s", "1", "9", "9", "s", "0", "2"],
}


@dataclass
class Result:
    clips: list[dict[str, Any]] = field(default_factory=list)
    clears: list[float] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    lines: list[tuple[float, str]] = field(default_factory=list)
    log_rows: list[dict[str, Any]] = field(default_factory=list)
    waits: list[dict[str, Any]] = field(default_factory=list)
    said: list[dict[str, Any]] = field(default_factory=list)
    keys: list[tuple[float, str]] = field(default_factory=list)
    closed_at: Optional[float] = None
    hung_up_at: Optional[float] = None
    end_t: float = 0.0
    error: str = ""
    stt_calls: int = 0
    model_answers: int = 0
    keypad_only: bool = False


def lang_key(lang: str) -> str:
    """The greeting key for a language, as offered right now (LANGS_OFFERED)."""
    keys = {v: k for k, v in tunables.turn0_keys().items()}
    return keys.get(lang, "1")


def run_call(script_name: str, flags_name: str, lang: str = "en",
             inject: Optional[Callable[[World, Caller], None]] = None,
             echo_level: int = 0, stt_fail: bool = False, bed: int = QUIET, n: int = 0) -> Result:
    """One whole call on the real engine. `inject` may plan extra caller actions before it starts."""
    corp = corpus()
    saved = {k: getattr(tunables, k) for k in FLAGS[flags_name]}
    saved_time = (turn_mod.time, ear_mod.time, phone_mod.time)
    for k, v in FLAGS[flags_name].items():
        setattr(tunables, k, v)
    world = World()
    world.echo_level = echo_level
    world.bed = bed
    turn_mod.time = ear_mod.time = phone_mod.time = FakeTime(world)
    res = Result()
    try:
        line = Line(world)
        rec = Rec(world)
        caller = Caller(world, [lang_key(lang)] + SCRIPTS[script_name][1:])
        stt = FakeSTT(world, caller)
        stt.fail = stt_fail
        clock = lambda: world.now  # noqa: E731
        mouth = Mouth(line.emit, "MZ-eval", clock=clock, log=rec)
        ear = Ear(stt=stt, log=rec)
        ear._events = VQueue(world)
        turn = Turn(mouth, ear=ear, trace=rec, log=rec, clock=clock)
        turn._keys = VQueue(world)

        def close() -> None:
            line.closed_at = world.now
            world.frames_on = False

        def speak(text: str, lang: str) -> bytes:
            world.advance_to(world.now + TTS_S)
            return b"\x55" * int(tunables.SAMPLE_RATE * 2.5)

        phone = PhoneAudio(corp, Pool(str(Path(_TMP.name) / "audio")), mouth, turn, close=close,
                           log=rec, trace=rec, speak=speak)
        phone._saved_answer = lambda key: None      # always the slow path: render, never the cache
        phone._save_answer = lambda key, audio: None
        line.on_mark = phone.on_mark
        world.line, world.turn = line, turn

        real_next, real_lang = phone.next_input, phone.select_language

        def next_input(profile: str = "normal") -> Any:
            caller.on_wait(profile)
            inp = real_next(profile)
            caller.wait_log[-1].update(got=type(inp).__name__, got_t=world.now,
                                       text=getattr(inp, "text", getattr(inp, "digit", "")))
            return inp

        def select_language() -> Any:
            caller.on_wait("greeting")
            out = real_lang()
            if isinstance(out, tuple):   # (language, "keypad" or "voice")
                caller.wait_log[-1].update(got="Digit" if out[1] == "keypad" else "Speech", got_t=world.now,
                                           text=out[0])
            else:
                caller.wait_log[-1].update(got=type(out).__name__, got_t=world.now,
                                           text=getattr(out, "text", getattr(out, "digit", "")))
            return out

        phone.next_input, phone.select_language = next_input, select_language
        if inject is not None:
            inject(world, caller)

        log = Log.open(call_id=f"barge_{n}", snapshot_id=corp.snapshot_id, logs_dir=str(Path(_TMP.name) / "logs"))
        log.tap = rec.record
        model = EvalModel(world)
        try:
            Engine.run_call(audio=phone, model=model, corpus=corp, log=log)
        except Stuck as e:
            res.error = f"stuck: {e}"
        except Exception as e:  # a crash is a finding, not a reason to stop the run
            res.error = f"crash: {type(e).__name__}: {e}"
        res.clips, res.clears, res.rows, res.lines = line.clips, line.clears, rec.rows, rec.lines
        res.log_rows, res.waits, res.said, res.keys = rec.log_rows, caller.wait_log, caller.said, caller.keys
        res.closed_at, res.hung_up_at, res.end_t = line.closed_at, caller.hung_up_at, world.now
        res.stt_calls, res.model_answers = stt.calls, model.answers
        res.keypad_only = bool(getattr(ear, "keypad_only", False))
        try:
            (Path(_TMP.name) / "logs" / f"barge_{n}.jsonl").unlink()
        except OSError:
            pass
    finally:
        turn_mod.time, ear_mod.time, phone_mod.time = saved_time
        for k, v in saved.items():
            setattr(tunables, k, v)
    return res


def show(res: Result, lo: float = 0.0, hi: float = 1e9) -> None:
    """Print one call as a timeline, for a person to read."""
    ev: list[tuple[float, str]] = []
    for c in res.clips:
        cut = f"  CUT at {c['cut_at'] - c['start']:.2f}s" if c["cut_at"] is not None else ""
        ev.append((c["start"], f"agent  {c['name']} ({c['end'] - c['start']:.1f}s){cut}"))
    for t, d in res.keys:
        ev.append((t, f"caller key {d}"))
    for u in res.said:
        ev.append((u["t0"], f"caller says \"{u['text']}\" ({u['t1'] - u['t0']:.1f}s)"))
    for r in res.rows:
        ev.append((r["t"], f"  trace {r.get('event')} {r.get('value')!r} took={r.get('took')} why={r.get('why')} "
                           f"prompt={r.get('prompt')} cut={r.get('cut_clip')}@{r.get('heard_ms')}"))
    for w in res.waits:
        ev.append((w["t"], f"  wait[{w['profile']}] -> {w.get('got')} {w.get('text', '')!r}"))
    for r in res.log_rows:
        if "stop" in r or "class" in r:
            ev.append((r["t"], f"  log {json.dumps({k: v for k, v in r.items() if k != 't'}, ensure_ascii=False)[:150]}"))
    for t, s in sorted(ev, key=lambda x: x[0]):
        if lo <= t - T0 <= hi:
            print(f"{t - T0:7.2f}  {s}")
    print(f"closed_at={None if res.closed_at is None else round(res.closed_at - T0, 2)} error={res.error!r} "
          f"clips={len(res.clips)} clears={len(res.clears)} waits={len(res.waits)}")


# --- what a caller can do at a moment ----------------------------------------------------
# Each kind plans its actions from time T (a moment inside one clip of the plain call).
# answers=True: this is the caller's answer, so the scripted answer for that wait is dropped.

QUESTION = "what does the tractor subsidy give?"
LONG_TALK = ("I wanted to ask you one thing about the money for the farm because my brother told me "
             "that there is some help for a tractor so what does the tractor subsidy give?")


def _key(d: str, dt: float = 0.0) -> Callable[[World, Caller, float], None]:
    return lambda w, c, T: w.at(T + dt, lambda: c.press(d))


def _say(text: str, dur: float, dt: float = 0.0, level: int = LOUD) -> Callable[[World, Caller, float], None]:
    return lambda w, c, T: c.speak(T + dt, dur, text, level)


KINDS: dict[str, dict[str, Any]] = {
    # keys
    "key_valid": dict(acts=[_key("1")], answers=True, voice=False),
    "key_wrong": dict(acts=[_key("8")], answers=True, voice=False),
    "key_twice": dict(acts=[_key("1"), _key("1", 0.1)], answers=True, voice=False),
    "key_three_fast": dict(acts=[_key("1"), _key("2", 0.15), _key("3", 0.3)], answers=True, voice=False),
    "key_hash": dict(acts=[_key("#")], answers=True, voice=False),
    "key_star": dict(acts=[_key("*")], answers=True, voice=False),
    "key_zero": dict(acts=[_key("0")], answers=True, voice=False),
    "key_nine": dict(acts=[_key("9")], answers=True, voice=False),
    # clear speech
    "voice_answer": dict(acts=[_say("I am a woman", 1.0)], answers=True, voice=True, real=True),
    "voice_question": dict(acts=[_say(QUESTION, 1.6)], answers=True, voice=True, real=True),
    "voice_yes": dict(acts=[_say("yes", 0.5)], answers=True, voice=True, real=True),
    "voice_again": dict(acts=[_say("say that again", 0.9)], answers=True, voice=True, real=True),
    "voice_soft": dict(acts=[_say(QUESTION, 1.6, level=600)], answers=False, voice=True),   # under the detector
    # not speech meant for the agent
    "cough": dict(acts=[_say("", 0.2)], answers=False, voice=True),
    "cough_long": dict(acts=[_say("", 0.6)], answers=False, voice=True),
    "backchannel": dict(acts=[_say("hmm", 0.5)], answers=False, voice=True),
    "two_coughs": dict(acts=[_say("", 0.25), _say("", 0.25, 0.5)], answers=False, voice=True),
    # mixes
    "voice_then_key": dict(acts=[_say("I am a woman", 1.0), _key("1", 0.7)], answers=True, voice=True, real=True),
    "key_then_voice": dict(acts=[_key("1"), _say(QUESTION, 1.6, 0.2)], answers=True, voice=True),
    "voice_twice": dict(acts=[_say(QUESTION, 1.6), _say("say that again", 0.9, 3.6)], answers=True, voice=True, real=True),
    "voice_stop_start": dict(acts=[_say("what does the", 0.6), _say("tractor subsidy give?", 0.9, 1.1)],
                             answers=True, voice=True, real=True),   # a 500 ms breath inside one sentence
    "voice_long": dict(acts=[_say(LONG_TALK, 8.5)], answers=True, voice=True, real=True),
    "voice_then_hangup": dict(acts=[_say(QUESTION, 1.6), lambda w, c, T: w.at(T + 0.9, c.hang_up)],
                              answers=True, voice=True),
    "hangup": dict(acts=[lambda w, c, T: w.at(T, c.hang_up)], answers=True, voice=False),
}


def make_inject(kind: str, T: float) -> Callable[[World, Caller], None]:
    k = KINDS[kind]

    def inject(world: World, caller: Caller) -> None:
        for act in k["acts"]:
            act(world, caller, T)
        if k["answers"]:
            world.at(T, caller.drop_plan)
    return inject


# --- one scenario -> one row of numbers --------------------------------------------------


def place_of(name: str) -> str:
    """The kind of clip, so `scheme:S1:summary` and `scheme:S2:summary` are one place."""
    if name.startswith("scheme:"):
        return "scheme:" + name.split(":")[2]
    for pre, cls in (("chip_", "menu_chip"), ("key_", "menu_key"), ("q_", "box_question"),
                     ("rephrase_", "box_rephrase"), ("keypad_", "keypad_box"), ("door_a_", "door_a")):
        if name.startswith(pre):
            return cls
    return name


def _heard(c: dict[str, Any]) -> tuple[float, float]:
    """When this clip was really heard: start, end (end <= start: never heard)."""
    return c["start"], (c["cut_at"] if c["cut_at"] is not None else c["end"])


def measure(base: Result, res: Result, T: float, kind: str, clip: dict[str, Any]) -> dict[str, Any]:
    k = KINDS[kind]
    row: dict[str, Any] = {"error": res.error}
    injected = [u for u in res.said if u["t0"] >= T - 1e-6 and (u["t0"], u["text"]) not in
                {(b["t0"], b["text"]) for b in base.said}]
    injected = [u for u in injected if u["t0"] <= T + 5.0]
    speech_end = max((u["t1"] for u in injected), default=T)
    first_end = injected[0]["t1"] if injected else T
    audible = [c for c in res.clips if _heard(c)[1] > _heard(c)[0] + 1e-6]
    # was the agent talking at T, before the caller did anything (so: in the plain call)
    row["agent_talking"] = any(c["start"] <= T < c["end"] and (c["cut_at"] is None or c["cut_at"] > T)
                               for c in base.clips)
    row["left_ms"] = int(max(0.0, clip["end"] - T) * 1000)

    # did the agent stop, and how fast
    base_clears = {round(c, 3) for c in base.clears}
    win = (first_end if k["voice"] else T) + 1.0
    clear = next((c for c in res.clears if T - 1e-6 <= c <= win and round(c, 3) not in base_clears), None)
    row["stopped"] = clear is not None
    row["stop_ms"] = int(round((clear - T) * 1000)) if clear is not None else None
    cut = next((c for c in res.clips if clear is not None and c["cut_at"] == clear and c["start"] < clear), None)
    row["cut_clip"] = cut["name"] if cut else ""
    row["cut_place"] = place_of(cut["name"]) if cut else ""
    row["said_again"] = bool(cut) and any(c["name"] == cut["name"] and c["start"] >= clear for c in audible)

    # what the engine made of it
    after = [r for r in res.rows if r["t"] >= T - 1e-6]
    sp = [r for r in after if r.get("event") == "speech"]
    row["speech_rows"] = [(r.get("value", ""), bool(r.get("took")), r.get("why", "")) for r in sp][:6]
    row["false_cut"] = sum(1 for r in sp if r.get("why") == "false_cut")
    row["key_beat_speech"] = any(r.get("why") == "key_beat_speech" for r in sp)
    row["key_rows"] = [(r.get("value", ""), bool(r.get("took")), r.get("why", "")) for r in after
                       if r.get("event") == "key"][:4]
    got = [w for w in res.waits if w.get("got_t", 0) >= T - 1e-6]
    row["first_got"] = (got[0].get("got", ""), got[0].get("text", "")) if got else ("", "")
    # the words the engine got from what was put in (not from the script's later answers)
    row["heard_texts"] = [w.get("text", "") for w in got if w.get("got") == "Speech"
                          and w.get("got_t", 0) <= speech_end + 2.5][:4]

    def count(rows: list[dict[str, Any]], cls: tuple[str, ...]) -> int:
        return sum(1 for r in rows if r.get("class") in cls)

    row["extra_noise"] = count(res.log_rows, ("NOISE",)) - count(base.log_rows, ("NOISE",))
    row["extra_unclear"] = count(res.log_rows, ("UNCLEAR",)) - count(base.log_rows, ("UNCLEAR",))
    row["questions"] = count(res.log_rows, ("QUESTION",))
    turns = [r["turn_n"] for r in res.log_rows if "turn_n" in r and "class" in r]
    bturns = [r["turn_n"] for r in base.log_rows if "turn_n" in r and "class" in r]
    row["extra_turns"] = (max(turns) if turns else 0) - (max(bturns) if bturns else 0)

    # timing after the caller finished
    nxt = next((c for c in audible if c["start"] >= speech_end - 1e-6), None)
    row["reply_ms"] = int((nxt["start"] - speech_end) * 1000) if (nxt and injected) else None
    row["reply_clip"] = nxt["name"] if nxt else ""
    over = 0.0
    for u in injected:
        for c in audible:
            a, b = _heard(c)
            over += max(0.0, min(b, u["t1"]) - max(a, u["t0"]))
    row["talk_over_ms"] = int(over * 1000)
    end = res.closed_at or res.end_t
    gaps, last = [], T
    sounds = sorted([_heard(c) for c in audible] + [(u["t0"], u["t1"]) for u in res.said])
    for a, b in sounds:   # quiet = nobody talking, agent or caller
        if b <= T:
            continue
        if a > last:
            gaps.append(a - last)
        last = max(last, b)
    row["max_quiet_ms"] = int(max(gaps, default=0.0) * 1000)

    # the same clip said twice back to back
    dup = ""
    for a, b in zip(audible, audible[1:]):
        acted = any(a["start"] <= t <= b["start"] for t, _ in res.keys) or any(
            u["t1"] >= a["start"] and u["t0"] <= b["start"] for u in res.said)
        if b["start"] >= T and a["name"] == b["name"] and b["start"] - _heard(a)[1] < 0.3 \
                and a["cut_at"] is None and place_of(a["name"]) not in ("menu_key",) and not acted:
            # the caller did nothing between the two: the agent just said it twice
            dup = a["name"]
            break
    row["said_twice"] = dup

    # goodbye, hang-up, the log
    bye = [c for c in res.clips if c["name"] == "closing_farewell"]
    row["farewell"] = "none" if not bye else "whole" if (
        bye[-1]["cut_at"] is None and (res.closed_at or 0) >= bye[-1]["end"] - 0.02) else "chopped"
    row["caller_hung_up"] = res.hung_up_at is not None
    row["audio_after_hangup"] = sum(1 for c in res.clips if res.hung_up_at is not None and c["sent"] > res.hung_up_at + 0.05)
    stops = [r for r in res.log_rows if "stop" in r]
    row["stop"] = stops[-1]["stop"] if stops else ""
    row["n_stop"] = len(stops)
    row["stop_is_last"] = bool(res.log_rows) and "stop" in res.log_rows[-1]
    row["closed"] = res.closed_at is not None
    row["waits"] = len(res.waits)
    row["call_s"] = round(end - T0, 1)
    row["keypad_only"] = res.keypad_only

    # is the logged heard_ms true
    worst = 0
    for r in res.rows:
        if r.get("cut_clip") and (r.get("heard_ms") or -1) >= 0:
            c = min((c for c in res.clips if c["name"] == r["cut_clip"] and c["cut_at"] is not None
                     and c["cut_at"] <= r["t"] + 1e-6), key=lambda c: r["t"] - c["cut_at"], default=None)
            if c is not None:
                worst = max(worst, abs(int((c["cut_at"] - c["start"]) * 1000) - r["heard_ms"]))
    row["heard_ms_err"] = worst
    return row


def run_case(script: str, flags: str, clip_name: str, ms: int, kind: str, lang: str = "en", nth: int = 0,
             bed: int = QUIET) -> tuple[dict[str, Any], Result]:
    """One scenario by name: `kind` put in `ms` into the nth clip called `clip_name`. For tests."""
    base = run_call(script, flags, lang, bed=bed)
    clip = [c for c in base.clips if c["name"] == clip_name and (c["cut_at"] is None or c["cut_at"] > c["start"])][nth]
    T = clip["start"] + ms / 1000.0
    res = run_call(script, flags, lang, inject=make_inject(kind, T), bed=bed)
    return measure(base, res, T, kind, clip), res


OFFSETS = ("50", "200", "300", "mid", "end-150", "end+300")


def offset_s(off: str, clip: dict[str, Any]) -> float:
    dur = clip["end"] - clip["start"]
    if off == "mid":
        return dur / 2
    if off.startswith("end"):
        return dur + int(off[3:]) / 1000.0
    return int(off) / 1000.0


def run_group(job: tuple[str, str, str, int, int, list[tuple[int, str, str]]]) -> list[dict[str, Any]]:
    """One plain call, then every scenario asked for on top of it."""
    script, flags, lang, bed, echo, cases = job
    base = run_call(script, flags, lang, bed=bed, echo_level=echo)
    out = []
    for ci, off, kind in cases:
        clip = base.clips[ci]
        T = clip["start"] + offset_s(off, clip)
        res = run_call(script, flags, lang, inject=make_inject(kind, T), bed=bed, echo_level=echo)
        row = {"id": f"{script}/{flags}/{lang}/bed{bed}/{ci}:{clip['name']}@{off}/{kind}",
               "script": script, "flags": flags, "lang": lang, "bed": bed, "echo": echo,
               "clip_i": ci, "clip": clip["name"], "place": place_of(clip["name"]), "off": off, "kind": kind,
               "voice": KINDS[kind]["voice"], "real": bool(KINDS[kind].get("real")),
               "cmd": f"--show {script}:{flags} --lang {lang} --bed {bed} --at {ci}:{int(offset_s(off, clip) * 1000)} --kind {kind}"}
        row.update(measure(base, res, T, kind, clip))
        out.append(row)
    return out


def plan(quick: bool) -> list[tuple[str, str, str, int, int, list[tuple[int, str, str]]]]:
    """The whole matrix as groups of scenarios that share one plain call."""
    jobs = []
    key_kinds = [k for k, v in KINDS.items() if not v["voice"]]
    voice_kinds = [k for k, v in KINDS.items() if v["voice"]]
    if quick:
        combos = [("keys", "voice_qa", "en", 0), ("question", "voice_qa", "en", 0), ("spoken", "voice", "hi", 0)]
        offs: tuple[str, ...] = ("300", "mid")
        key_kinds, voice_kinds = ["key_valid", "hangup"], ["voice_question", "cough", "cough_long", "backchannel"]
    else:
        combos = [(s, f, l, 0) for s in SCRIPTS for f in FLAGS for l in ("en", "hi")]
        combos += [("keys", "voice_qa", "en", b) for b in (300, 550, 900)]          # the sound of the place
        combos += [("question", "voice_qa", "en", b) for b in (300, 550, 900)]
        offs = OFFSETS
    for script, flags, lang, bed in combos:
        base = run_call(script, flags, lang, bed=bed)
        seen: dict[str, int] = {}
        cases = []
        for c in base.clips:
            if c["cut_at"] is not None and c["cut_at"] <= c["start"]:
                continue   # queued but never heard in the plain call
            seen[place_of(c["name"])] = seen.get(place_of(c["name"]), 0) + 1
            if seen[place_of(c["name"])] > (1 if quick else 2):
                continue   # two of each kind of clip is enough
            for off in offs:
                kinds = key_kinds + (voice_kinds if flags != "keys_only" else ["voice_question", "cough_long"])
                if bed:
                    kinds = ["voice_question", "voice_yes", "cough", "cough_long", "key_valid"]
                cases += [(c["i"], off, kind) for kind in kinds]
        for i in range(0, len(cases), 60):
            jobs.append((script, flags, lang, bed, 0, cases[i:i + 60]))
    return jobs


def run_plain(script: str, flags: str, lang: str, bed: int, echo: int, stt_fail: bool = False) -> dict[str, Any]:
    """A plain call under some trouble (echo, a noisy place, speech-to-text down): how does it end."""
    quiet = run_call(script, flags, lang)
    res = run_call(script, flags, lang, bed=bed, echo_level=echo, stt_fail=stt_fail)
    stops = [r for r in res.log_rows if "stop" in r]
    spoke = [w for w in res.waits if w.get("got") in ("Speech", "Noise")]
    return {"script": script, "flags": flags, "bed": bed, "echo": echo, "stt_fail": stt_fail, "error": res.error,
            "closed": res.closed_at is not None, "stop": stops[-1]["stop"] if stops else "",
            "quiet_stop": next((r["stop"] for r in quiet.log_rows if "stop" in r), ""),
            "self_stops": len(res.clears) - len(quiet.clears), "ghost_inputs": len(spoke) - sum(
                1 for w in quiet.waits if w.get("got") in ("Speech", "Noise")),
            "call_s": round((res.closed_at or res.end_t) - T0, 1),
            "quiet_call_s": round((quiet.closed_at or quiet.end_t) - T0, 1),
            "keypad_only": res.keypad_only, "clips": len(res.clips), "quiet_clips": len(quiet.clips)}


# --- the scorecard -----------------------------------------------------------------------


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))] if xs else 0.0


def scorecard(rows: list[dict[str, Any]], plain: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Each check: what a good voice agent does, what we do, pass or fail, and one case to replay."""
    checks: list[dict[str, Any]] = []

    def add(cid: str, name: str, target: str, value: str, ok: Optional[bool], bad: list[dict[str, Any]], n: int,
            note: str = "") -> None:
        checks.append({"id": cid, "name": name, "target": target, "value": value, "n": n,
                       "status": "info" if ok is None else "pass" if ok else "FAIL",
                       "example": bad[0]["cmd"] if bad else "", "note": note,
                       "where": dict(Counter(f"{r['flags']}:{r['place']}" for r in bad).most_common(8))})

    quiet = [r for r in rows if r["bed"] == 0]
    on = [r for r in quiet if r["flags"] != "keys_only"]

    # C1 the call always ends cleanly
    bad = [r for r in rows if r["error"] or not r["closed"] or r["n_stop"] != 1 or not r["stop_is_last"]]
    add("C1", "every call ends cleanly (no crash, no loop, one stop row)", "100 %",
        f"{len(rows) - len(bad)} of {len(rows)}", not bad, bad, len(rows))

    # C2 a key stops the agent at once
    ks = [r for r in quiet if r["kind"] == "key_valid" and r["agent_talking"] and r["off"] not in ("50", "200")
          and r["place"] != "closing_farewell"]
    bad = [r for r in ks if not r["stopped"] or r["stop_ms"] > 50]
    add("C2", "a key stops the agent", "<= 50 ms, every time",
        f"max {max((r['stop_ms'] or 0 for r in ks), default=0)} ms, stopped {sum(r['stopped'] for r in ks)} of {len(ks)}",
        not bad, bad, len(ks))

    # C3 clear speech stops the agent: how fast
    vs = [r for r in on if r["real"] and r["kind"] != "voice_then_key" and r["agent_talking"] and r["left_ms"] >= 700
          and r["off"] not in ("50", "200") and r["place"] not in ("closing_farewell", "one_moment")]
    st = [r["stop_ms"] for r in vs if r["stopped"]]
    bad = sorted([r for r in vs if r["stopped"] and r["stop_ms"] > 300], key=lambda r: -r["stop_ms"])
    add("C3", "clear speech stops the agent fast", "<= 300 ms (good systems: 200-300)",
        f"median {int(statistics.median(st)) if st else 0} ms, p95 {int(_pct(st, .95))} ms, max {max(st, default=0)} ms",
        bool(st) and _pct(st, .95) <= 300, bad, len(st))

    # C4 reach: at which places clear speech gets through (stops the agent, or is heard), per flag set
    for fl in ("keys_only", "voice", "voice_qa"):
        v = [r for r in quiet if r["flags"] == fl and r["kind"] == "voice_question" and r["agent_talking"]
             and r["left_ms"] >= 700 and r["off"] not in ("50", "200") and r["place"] != "closing_farewell"]
        ok_rows = [r for r in v if r["stopped"] or QUESTION in r["heard_texts"]]
        places = sorted({r["place"] for r in v})
        deaf = sorted({r["place"] for r in v} - {r["place"] for r in ok_rows})
        bad = [r for r in v if r not in ok_rows]
        add(f"C4.{fl}", f"speech gets through at every place the agent talks (goodbye aside) [{fl}]", "every place",
            f"{len(places) - len(deaf)} of {len(places)} places; deaf at: {', '.join(deaf) or 'none'}",
            None if fl == "keys_only" else not deaf, bad, len(v),
            note="keys_only is today's default: voice cut-in is off on purpose" if fl == "keys_only" else "")

    # C5 a short cough never stops the agent
    cs = [r for r in on if r["kind"] in ("cough", "voice_soft") and r["agent_talking"]]
    bad = [r for r in cs if r["stopped"]]
    add("C5a", "a short cough or soft far voice does not stop the agent", "0 stops",
        f"{len(bad)} stops in {len(cs)}", not bad, bad, len(cs))
    cs = [r for r in on if r["kind"] == "two_coughs" and r["agent_talking"] and r["left_ms"] >= 900]
    bad = [r for r in cs if r["stopped"]]
    add("C5b", "two short coughs (250 ms each, 250 ms apart) do not stop the agent", "0 stops",
        f"{len(bad)} stops in {len(cs)}", not bad, bad, len(cs))

    # C6 a long cough / "hmm" must not cost the caller anything
    hs = [r for r in on if r["kind"] in ("cough_long", "backchannel") and r["agent_talking"] and r["left_ms"] >= 700
          and r["off"] not in ("50", "200")]
    stopped = [r for r in hs if r["stopped"]]
    # (a caller who pressed a key right after their own cough moved on by themselves)
    lost = [r for r in stopped if not r["said_again"] and not r["key_beat_speech"]]
    add("C6a", "a long cough or \"hmm\" does not make the caller lose what was being said",
        "agent keeps talking, or says the cut part again",
        f"stopped {len(stopped)} of {len(hs)}; cut part never said again in {len(lost)}", not lost, lost, len(hs))
    cost = [r for r in hs if r["extra_noise"] > 0 or r["extra_unclear"] > 0 or r["extra_turns"] > 0]
    add("C6b", "a long cough or \"hmm\" does not cost a turn or a strike", "0",
        f"{len(cost)} of {len(hs)} calls logged an extra NOISE / UNCLEAR turn", not cost, cost, len(hs))

    # C7 the caller's words are used whole, once
    ws = [r for r in on if r["kind"] in ("voice_question", "voice_stop_start", "voice_long") and r["stopped"]
          and r["place"] != "greeting_trilingual"]
    want = {"voice_question": QUESTION, "voice_stop_start": QUESTION, "voice_long": LONG_TALK}
    bad = [r for r in ws if r["heard_texts"][:1] != [want[r["kind"]]] or len(r["heard_texts"]) > 1]
    add("C7", "the caller's sentence reaches the engine whole and once (also with a breath in it, also when long)",
        "100 %", f"{len(ws) - len(bad)} of {len(ws)}", not bad, bad, len(ws),
        note=str(dict(Counter(r["kind"] for r in bad))))

    # C8 how long until the agent answers
    rs = [r for r in on if r["kind"] in ("voice_question", "voice_answer", "voice_yes") and r["reply_ms"] is not None
          and r["stopped"]]
    rp = [r["reply_ms"] for r in rs]
    bad = sorted([r for r in rs if r["reply_ms"] > 1500], key=lambda r: -r["reply_ms"])
    add("C8", "the agent starts to reply soon after the caller stops talking", "<= 1500 ms (good systems: ~1000)",
        f"median {int(statistics.median(rp)) if rp else 0} ms, p95 {int(_pct(rp, .95))} ms "
        f"(of this, fixed waits: 800 ms end-of-speech + {int(STT_S * 1000)} ms speech-to-text)",
        bool(rp) and _pct(rp, .95) <= 1500, bad, len(rp))

    # C9 the agent and the caller talking at the same time
    to = [r for r in on if r["kind"] in ("voice_question", "voice_answer", "voice_again") and r["agent_talking"]
          and r["flags"] == "voice_qa" and r["place"] not in ("closing_farewell", "one_moment")]
    tv = [r["talk_over_ms"] for r in to]
    bad = sorted([r for r in to if r["talk_over_ms"] > 600], key=lambda r: -r["talk_over_ms"])
    add("C9", "agent and caller do not talk over each other for long (one plain sentence)", "<= 600 ms",
        f"median {int(statistics.median(tv)) if tv else 0} ms, max {max(tv, default=0)} ms; over 600 ms in {len(bad)} of {len(to)}",
        not bad, bad, len(to))

    # C10 no long dead air after an input
    bad = sorted([r for r in quiet if r["max_quiet_ms"] > 9000 and not r["caller_hung_up"]], key=lambda r: -r["max_quiet_ms"])
    add("C10", "never more than one silence gap of dead air", "<= 9 s",
        f"max {max((r['max_quiet_ms'] for r in quiet if not r['caller_hung_up']), default=0)} ms", not bad, bad, len(quiet))

    # C11 nothing is said twice back to back
    bad = [r for r in quiet if r["said_twice"]]
    add("C11", "the agent never says the same clip twice in a row", "0",
        f"{len(bad)} of {len(quiet)}; clips: {dict(Counter(r['said_twice'] for r in bad).most_common(5))}", not bad, bad,
        len(quiet))

    # C12 the goodbye is heard whole
    fs = [r for r in quiet if r["farewell"] != "none" and not r["caller_hung_up"]]
    bad = [r for r in fs if r["farewell"] == "chopped"]
    add("C12", "the goodbye is always heard whole", "100 %", f"chopped in {len(bad)} of {len(fs)}", not bad, bad, len(fs),
        note=str(dict(Counter(r["kind"] for r in bad).most_common(6))))

    # C13 the logged heard_ms is true
    hm = [r for r in quiet if r["heard_ms_err"] is not None]
    bad = sorted([r for r in hm if r["heard_ms_err"] > 60], key=lambda r: -r["heard_ms_err"])
    add("C13", "the log knows how much of a cut clip was heard", "within 60 ms",
        f"max error {max((r['heard_ms_err'] for r in hm), default=0)} ms", not bad, bad, len(hm))

    # C14 a key beats speech; a hang-up ends it
    kv = [r for r in on if r["kind"] == "voice_then_key" and r["place"] != "closing_farewell"]
    bad = [r for r in kv if r["first_got"][0] != "Digit"]
    add("C14", "a key pressed while talking wins over the words", "100 %", f"{len(kv) - len(bad)} of {len(kv)}",
        not bad, bad, len(kv))
    hu = [r for r in quiet if r["kind"] in ("hangup", "voice_then_hangup")]
    bad = [r for r in hu if r["audio_after_hangup"] > 1 or r["n_stop"] != 1]
    add("C15", "after the caller hangs up the agent says nothing more", "at most the clip in flight",
        f"{len(hu) - len(bad)} of {len(hu)}", not bad, bad, len(hu))

    # C16 early input (first 250 ms of a clip)
    ek = [r for r in quiet if r["kind"] == "key_valid" and r["off"] in ("50", "200") and r["agent_talking"]]
    ev = [r for r in on if r["kind"] == "voice_question" and r["off"] in ("50", "200") and r["agent_talking"]
          and r["left_ms"] >= 700]
    ev = [r for r in ev if r["flags"] == "voice_qa" and r["place"] not in ("closing_farewell", "one_moment")]
    lostv = [r for r in ev if not r["heard_texts"] and r["first_got"][0] != "Speech"]
    add("C16", "input in the first 250 ms of a clip is not lost", "speech is still heard",
        f"keys: took {sum(1 for r in ek if any(t for _, t, _ in r['key_rows'][:1]))} of {len(ek)} "
        f"(rest dropped by the guard, on purpose); speech lost in {len(lostv)} of {len(ev)}", not lostv, lostv, len(ev))

    # C17 two cut-ins in a row
    tw = [r for r in on if r["kind"] == "voice_twice" and r["flags"] == "voice_qa" and r["stopped"]
          and r["place"] != "greeting_trilingual"]
    bad = [r for r in tw if "say that again" not in r["heard_texts"] and QUESTION not in r["heard_texts"]]
    add("C17", "a second cut-in right after the first is heard too", "100 %", f"{len(tw) - len(bad)} of {len(tw)}",
        not bad, bad, len(tw))

    # C18 the sound of the place
    for bed in sorted({r["bed"] for r in rows if r["bed"]}):
        b = [r for r in rows if r["bed"] == bed]
        ghosts = [r for r in b if r["kind"] in ("key_valid",) and (r["extra_noise"] > 0 or r["speech_rows"])]
        q = [r for r in b if r["kind"] == "voice_question" and r["agent_talking"] and r["left_ms"] >= 700
             and r["off"] not in ("50", "200") and r["place"] not in ("closing_farewell", "one_moment")]
        heard = [r for r in q if QUESTION in r["heard_texts"]]
        rp = [r["reply_ms"] for r in q if r["reply_ms"] is not None and r["stopped"]]
        bad = [r for r in q if QUESTION not in r["heard_texts"]] + ghosts
        add(f"C18.bed{bed}", f"works in a place with background sound level {bed} (voice starts at 700, ends under 400)",
            "question still heard, reply as fast as in a quiet room",
            f"question heard {len(heard)} of {len(q)}; reply median {int(statistics.median(rp)) if rp else 0} ms; "
            f"ghost inputs in {len(ghosts)} key-only cases", len(heard) == len(q) and not ghosts and
            (not rp or statistics.median(rp) <= 1800), bad, len(b))

    # C19 plain calls under trouble
    for p in plain:
        label = ("echo " + str(p["echo"])) if p["echo"] else ("bed " + str(p["bed"])) if p["bed"] else "speech-to-text down"
        same = p["stop"] == p["quiet_stop"] and not p["error"] and p["closed"] and p["self_stops"] <= 0
        add(f"C19.{p['script']}.{p['flags']}.{label.replace(' ', '')}",
            f"plain call, {label} [{p['script']}, {p['flags']}]", "ends like the quiet call, agent never stops itself",
            f"stop={p['stop'] or p['error']} (quiet: {p['quiet_stop']}), self-stops {p['self_stops']}, "
            f"ghost inputs {p['ghost_inputs']}, {p['call_s']} s (quiet {p['quiet_call_s']} s), keypad_only={p['keypad_only']}",
            None if p["stt_fail"] else same, [], 1)

    md = ["# Cut-in scorecard", "", f"{len(rows)} scenarios + {len(plain)} plain calls under trouble. "
          "Real engine and audio code on a virtual clock; fake line, speech-to-text and model.", "",
          "| | check | what good looks like | what we do | n | result |", "|---|---|---|---|---|---|"]
    for c in checks:
        md.append(f"| {c['id']} | {c['name']} | {c['target']} | {c['value']} | {c['n']} | **{c['status']}** |")
    md += ["", "## Failing checks: where, and one case to replay", ""]
    for c in checks:
        if c["status"] == "FAIL":
            md.append(f"- **{c['id']}** {c['name']}")
            if c["where"]:
                md.append(f"  - where: {c['where']}")
            if c["note"] and c["note"] != "{}":
                md.append(f"  - note: {c['note']}")
            if c["example"]:
                md.append(f"  - replay: `python -m tools.barge_eval {c['example']}`")
    return checks, "\n".join(md) + "\n"


def run_eval(quick: bool, workers: int, out_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    t0 = real_time.time()
    jobs = plan(quick)
    rows: list[dict[str, Any]] = []
    if workers <= 1:
        for j in jobs:
            rows += run_group(j)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for part in ex.map(run_group, jobs):
                rows += part
    plain = []
    if not quick:
        for script in ("keys", "question"):
            for flags in ("voice", "voice_qa"):
                plain += [run_plain(script, flags, "en", 0, e) for e in (500, 1500)]
                plain += [run_plain(script, flags, "en", b, 0) for b in (300, 550, 900)]
        plain += [run_plain("spoken", "voice_qa", "en", 0, 0, stt_fail=True),
                  run_plain("question", "voice_qa", "en", 0, 0, stt_fail=True)]
    checks, md = scorecard(rows, plain)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "results.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    (out_dir / "plain.json").write_text(json.dumps(plain, indent=1), encoding="utf-8")
    md += f"\nRun: {len(rows)} scenarios in {real_time.time() - t0:.0f} s.\n"
    (out_dir / "scorecard.md").write_text(md, encoding="utf-8")
    print(md)
    return rows, checks


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Cut-in check on a virtual clock.")
    ap.add_argument("--quick", action="store_true", help="a small sample, a few seconds")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--out-dir", default="scratch/barge-eval")
    ap.add_argument("--show", metavar="SCRIPT:FLAGS", help="print one call, e.g. keys:voice_qa")
    ap.add_argument("--at", metavar="CLIP:MS", help="with --show: put --kind in at MS into clip number CLIP")
    ap.add_argument("--kind", default="voice_question")
    ap.add_argument("--bed", type=int, default=0, help="background sound level of the place (0 = quiet room)")
    ap.add_argument("--echo", type=int, default=0)
    ap.add_argument("--lang", default="en", help="en or hi (mr when it is offered)")
    ap.add_argument("--win", type=float, default=12.0, help="with --at: seconds to show after the moment")
    args = ap.parse_args(argv)
    if args.show:
        s, f = args.show.split(":")
        inj = None
        T = T0
        if args.at:
            ci, ms = args.at.split(":")
            base = run_call(s, f, args.lang, bed=args.bed, echo_level=args.echo)
            T = base.clips[int(ci)]["start"] + int(ms) / 1000.0
            print(f"-- {args.kind} at {T - T0:.2f}s = {ms} ms into clip {ci} ({base.clips[int(ci)]['name']})")
            inj = make_inject(args.kind, T)
        lo, hi = (T - T0 - 3, T - T0 + args.win) if args.at else (0.0, 1e9)
        show(run_call(s, f, args.lang, inject=inj, bed=args.bed, echo_level=args.echo), lo, hi)
        return 0
    run_eval(args.quick, args.workers, Path(args.out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
