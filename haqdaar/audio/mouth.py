"""haqdaar/audio/mouth.py

Plan 2.5 — what the caller hears.

The engine thread hands Mouth clips; Mouth cuts them into 1 s media frames, follows each clip
with a mark, and remembers the last sequence for `#`. A key press calls `clear()`, which tells
the phone line to drop everything it has buffered.

Threads. The engine runs on its own thread; the socket loop receives keys and marks. Both call
Mouth, and neither may ever wait on the other. So Mouth never touches the socket itself: it
hands each message to `emit`, which must be non-blocking and thread-safe (the server's emit puts
the message on an asyncio queue with `loop.call_soon_threadsafe`, and one writer task sends
them in order). The 15 Sep demo blocked the socket loop on its own send from inside `clear()`
and froze every key press for 10 s; that cannot happen here, because nothing in Mouth waits.
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Awaitable, Callable, Iterable, Optional

from haqdaar.audio.render import stretch
from haqdaar.audio.telephony import build_clear, build_mark, build_media
from haqdaar.contracts import tunables

Clip = tuple[str, bytes]  # (name for the log and the mark, 8 kHz mu-law audio)
Tag = tuple[int, str]     # (prompt_n, prompt name) the clips belong to, for the trace stamp


class Mouth:
    def __init__(
        self,
        emit: Callable[[dict[str, Any]], None],
        stream_sid: str,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] = lambda line: None,
    ) -> None:
        self._emit = emit
        self._sid = stream_sid
        self._clock = clock
        self._log = log
        self._lock = threading.Lock()
        self._seq = 0
        self._pending: set[str] = set()   # marks sent, not yet played back
        self._clip_schedules: list[dict[str, Any]] = []
        self._ends: dict[str, float] = {}  # clip name -> when its latest run should end (heard() asks)
        self._marked: set[str] = set()     # clip names whose mark came back
        self._play_until = 0.0            # when the buffered audio should end
        self._last: list[Clip] = []
        self._repeats = 0                 # `#` presses in a row
        self._cleared = 0                 # bumps on every clear(); a send in flight stops
        self.last_cut: tuple[str, int] = ("", -1)
        self.no_cut: frozenset[str] = frozenset()   # clips nothing may cut (the goodbye)
        self._resume: list[tuple[str, bytes, Optional[Tag]]] = []   # what the last clear() cut off
        self.ahead_max = 0.0              # most seconds of sound sent ahead of its playing time (line report)

    # --- engine thread -------------------------------------------------------------
    def play(self, clips: list[Clip], tag: Optional[Tag] = None) -> None:
        """Queue a sequence of clips. It becomes what `#` repeats."""
        with self._lock:
            self._last = list(clips)
            self._repeats = 0
            self.last_cut = ("", -1)
            self._resume = []
        self._send(clips, tag)

    def play_stream(self, name: str, chunks: Iterable[bytes], tag: Optional[Tag] = None) -> bytes:
        """Play ONE clip whose sound arrives in pieces (live voice, 7.14). Each piece is sent as it
        comes and the clip grows; its one mark is sent after the last piece. A clear() stops the
        sending, not the reading. Returns the whole sound."""
        frame = min(tunables.FRAME_BYTES, int(0.200 * tunables.SAMPLE_RATE))
        with self._lock:
            self._last = []
            self._repeats = 0
            self.last_cut = ("", -1)
            self._resume = []
            generation = self._cleared
            start_t = max(self._clock(), self._play_until)
            self._seq += 1
            mark = f"{self._seq}:{name}"
            self._pending.add(mark)
            self._marked.discard(name)
            cs: dict[str, Any] = {"mark": mark, "name": name, "start": start_t, "end": start_t,
                                  "dur_ms": 0, "tag": tag, "audio": b""}
            self._clip_schedules.append(cs)
        whole = bytearray()
        try:
            for chunk in chunks:
                dry = 0.0
                with self._lock:
                    if self._cleared == generation and whole:
                        # 5 Oct: the piece came after the sound sent so far ran out: the caller
                        # heard a hole this long. The clock moves with it, and the log says so.
                        dry = self._clock() - cs["end"]
                        if dry > 0.05:
                            start_t += dry
                if dry > 0.05:
                    self._log(f"!! live voice ran dry for {dry * 1000:.0f} ms inside {name} (a hole in the sound)")
                whole += chunk
                with self._lock:
                    if self._cleared != generation:
                        continue
                    cs["audio"] = bytes(whole)
                    cs["end"] = start_t + len(whole) / tunables.SAMPLE_RATE
                    cs["dur_ms"] = int(len(whole) * 1000 / tunables.SAMPLE_RATE)
                    self._play_until = self._ends[name] = cs["end"]
                    self.ahead_max = max(self.ahead_max, cs["end"] - self._clock())
                for i in range(0, len(chunk), frame):
                    if self._cleared != generation:
                        break
                    self._emit(build_media(self._sid, chunk[i:i + frame]))
        finally:
            with self._lock:
                live = self._cleared == generation
                if live:
                    self._last = [(name, bytes(whole))]
            if live:
                self._emit(build_mark(self._sid, mark))
            self._log(f"-> say {name} ({len(whole) / tunables.SAMPLE_RATE:.1f} s, streamed)")
        return bytes(whole)

    def repeat(self, tag: Optional[Tag] = None) -> None:
        """`#`: say the last sequence again. A second `#` in a row says it slower (D13)."""
        with self._lock:
            self._repeats += 1
            slow = self._repeats >= 2
            clips = list(self._last)
        if slow:
            clips = [(name, stretch(audio, tunables.SLOW_PACE)) for name, audio in clips]
        self._send(clips, tag)

    # --- either thread -------------------------------------------------------------
    def clear(self) -> tuple[str, int]:
        """Stop talking now. Never waits: safe from the socket loop.

        Returns (cut_clip, heard_ms) for the clip sounding when cleared. A `no_cut` clip that is
        sounding is not cut at all; one still waiting behind other clips is sent again.
        """
        with self._lock:
            now = self._clock()
            cut_clip = ""
            heard_ms = -1
            waiting = [cs for cs in self._clip_schedules if cs["mark"] in self._pending]
            if waiting and waiting[0]["name"] in self.no_cut:
                return ("", -1)
            keep = [cs for cs in waiting if cs["name"] in self.no_cut]
            self._resume = [(cs["name"], cs["audio"], cs["tag"]) for cs in waiting
                            if cs["name"] not in self.no_cut]
            for cs in self._clip_schedules:
                if cs["mark"] in self._pending:
                    cut_clip = cs["name"]
                    if now < cs["start"]:
                        heard_ms = 0
                    else:
                        heard_ms = max(0, min(int((now - cs["start"]) * 1000), cs["dur_ms"]))
                    break
            for cs in self._clip_schedules:
                if cs["mark"] in self._pending and cs["end"] > now:
                    self._ends.pop(cs["name"], None)  # cut before its end: not heard
            self._pending.clear()
            self._clip_schedules.clear()
            self._play_until = now
            self._cleared += 1
            self.last_cut = (cut_clip, heard_ms)
        self._emit(build_clear(self._sid))
        for cs in keep:
            self._send([(cs["name"], cs["audio"])], cs["tag"])
        return (cut_clip, heard_ms)

    def resume(self) -> bool:
        """Say again what the last clear() cut off, from the start of the cut clip. For a cut
        that turned out to be nothing (a cough, "hmm"): the caller loses no words. False when
        there is nothing to say again."""
        return self.say_again(self.take_cut())

    def take_cut(self) -> list[tuple[str, bytes, Optional[Tag]]]:
        """What the last clear() cut off, taken out of the Mouth (the next play() would forget it)."""
        with self._lock:
            clips, self._resume = self._resume, []
        return clips

    def say_again(self, clips: list[tuple[str, bytes, Optional[Tag]]]) -> bool:
        """Say clips from take_cut(), each from its start. False when there are none."""
        with self._lock:
            self.last_cut = ("", -1)
        for name, audio, tag in clips:
            self._send([(name, audio)], tag)
        return bool(clips)

    def rebind(self, emit: Callable[[dict[str, Any]], None], stream_sid: str) -> int:
        """Step 1.0: the stream dropped and a new one is open for the same call. From now on the
        sound goes there. Every clip whose mark never came back (it was sounding, or was queued
        while the line was down) is sent again, each from its start, under its old mark, so the
        engine does not have to know. Returns how many clips. Never waits: safe from the socket loop.
        """
        frame = min(tunables.FRAME_BYTES, int(0.200 * tunables.SAMPLE_RATE))
        with self._lock:
            self._emit = emit
            self._sid = stream_sid
            again = [cs for cs in self._clip_schedules if cs["mark"] in self._pending]
            at = self._clock()
            for cs in again:
                cs["start"], cs["end"] = at, at + len(cs["audio"]) / tunables.SAMPLE_RATE
                at = self._ends[cs["name"]] = cs["end"]
                for i in range(0, len(cs["audio"]), frame):
                    emit(build_media(stream_sid, cs["audio"][i:i + frame]))
                emit(build_mark(stream_sid, cs["mark"]))
            if again:
                self._play_until = at
        return len(again)

    def on_mark(self, name: str) -> None:
        """The line played up to this mark."""
        with self._lock:
            self._pending.discard(name)
            idx = -1
            for i, cs in enumerate(self._clip_schedules):
                if cs["mark"] == name:
                    idx = i
                    break
            if idx >= 0:
                self._marked.add(self._clip_schedules[idx]["name"])
                self._clip_schedules = self._clip_schedules[idx + 1:]

    def sounding(self) -> Optional[Tag]:
        """The (prompt_n, name) of the clip that is sounding now, if it was queued with a tag.

        The engine queues several prompts at once, so the newest prompt_n is not the one the
        caller is hearing. A key or a hangup is stamped with this one in the trace.
        """
        with self._lock:
            for cs in self._clip_schedules:
                if cs["mark"] in self._pending:
                    return cs["tag"]
        return None

    def clip_heard(self, name: str) -> bool:
        """Did a clip of this name play to its end: its mark came back, or its time ran out
        with no clear in between."""
        with self._lock:
            if name in self._marked:
                return True
            end = self._ends.get(name)
            return end is not None and self._clock() >= end

    @property
    def playing(self) -> bool:
        return self.remaining() > 0

    def remaining(self) -> float:
        """Seconds of audio still to play. 0 once every mark has come back, with clock guess as timeout."""
        with self._lock:
            if not self._pending:
                return 0.0
            now = self._clock()
            if now > self._play_until + 1.0:
                return 0.0
            return max(self._play_until - now, 0.05)

    # -------------------------------------------------------------------------------
    def _send(self, clips: list[Clip], tag: Optional[Tag] = None) -> None:
        frame = min(tunables.FRAME_BYTES, int(0.200 * tunables.SAMPLE_RATE))
        with self._lock:
            generation = self._cleared
        for name, audio in clips:
            with self._lock:
                if self._cleared != generation:
                    return  # a key stopped this sequence: send none of the rest
                now = self._clock()
                start_t = max(now, self._play_until)
                dur_s = len(audio) / tunables.SAMPLE_RATE
                dur_ms = int(dur_s * 1000)
                end_t = start_t + dur_s
                self._play_until = end_t
                self.ahead_max = max(self.ahead_max, end_t - now)
                self._seq += 1
                mark = f"{self._seq}:{name}"
                self._pending.add(mark)
                self._ends[name] = end_t
                self._marked.discard(name)
                self._clip_schedules.append({
                    "mark": mark,
                    "name": name,
                    "start": start_t,
                    "end": end_t,
                    "dur_ms": dur_ms,
                    "tag": tag,
                    "audio": audio,
                })
            for i in range(0, len(audio), frame):
                if self._cleared != generation:
                    return
                self._emit(build_media(self._sid, audio[i:i + frame]))
            self._emit(build_mark(self._sid, mark))
            self._log(f"-> say {name} ({dur_s:.1f} s)")


class Outbox:
    """The one road to the socket. `emit` from any thread, never blocks; `run` sends in order.

    The server starts `run()` as a task on the socket's loop and calls `close()` at hang-up.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, send: Callable[[dict[str, Any]], Awaitable[None]]):
        self._loop = loop
        self._send = send
        self._queue: asyncio.Queue[Optional[dict[str, Any]]] = asyncio.Queue()
        self.closed = False

    def emit(self, msg: dict[str, Any]) -> None:
        if self.closed:
            return
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, msg)
        except RuntimeError:  # loop already gone: the call is over
            self.closed = True

    def close(self) -> None:
        self.emit(None)  # type: ignore[arg-type]
        self.closed = True

    async def run(self) -> None:
        while True:
            msg = await self._queue.get()
            if msg is None:
                return
            try:
                await self._send(msg)
            except Exception:  # socket gone: drop the rest quietly
                self.closed = True
                return
