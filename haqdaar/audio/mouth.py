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
from typing import Any, Awaitable, Callable, Optional

from haqdaar.audio.render import stretch
from haqdaar.audio.telephony import build_clear, build_mark, build_media
from haqdaar.contracts import tunables

Clip = tuple[str, bytes]  # (name for the log and the mark, 8 kHz mu-law audio)


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
        self._play_until = 0.0            # when the buffered audio should end
        self._last: list[Clip] = []
        self._repeats = 0                 # `#` presses in a row
        self._cleared = 0                 # bumps on every clear(); a send in flight stops

    # --- engine thread -------------------------------------------------------------
    def play(self, clips: list[Clip]) -> None:
        """Queue a sequence of clips. It becomes what `#` repeats."""
        with self._lock:
            self._last = list(clips)
            self._repeats = 0
        self._send(clips)

    def repeat(self) -> None:
        """`#`: say the last sequence again. A second `#` in a row says it slower (D13)."""
        with self._lock:
            self._repeats += 1
            slow = self._repeats >= 2
            clips = list(self._last)
        if slow:
            clips = [(name, stretch(audio, tunables.SLOW_PACE)) for name, audio in clips]
        self._send(clips)

    # --- either thread -------------------------------------------------------------
    def clear(self) -> None:
        """Stop talking now. Never waits: safe from the socket loop."""
        with self._lock:
            self._pending.clear()
            self._play_until = self._clock()
            self._cleared += 1
        self._emit(build_clear(self._sid))

    def on_mark(self, name: str) -> None:
        """The line played up to this mark."""
        with self._lock:
            self._pending.discard(name)

    @property
    def playing(self) -> bool:
        return self.remaining() > 0

    def remaining(self) -> float:
        """Seconds of audio still to play. 0 once every mark has come back."""
        with self._lock:
            if not self._pending:
                return 0.0
            return max(self._play_until - self._clock(), 0.0)

    # -------------------------------------------------------------------------------
    def _send(self, clips: list[Clip]) -> None:
        frame = tunables.FRAME_BYTES
        with self._lock:
            generation = self._cleared
        for name, audio in clips:
            with self._lock:
                if self._cleared != generation:
                    return  # a key stopped this sequence: send none of the rest
                self._seq += 1
                mark = f"{self._seq}:{name}"
                self._pending.add(mark)
                now = self._clock()
                self._play_until = max(now, self._play_until) + len(audio) / tunables.SAMPLE_RATE
            for i in range(0, len(audio), frame):
                if self._cleared != generation:
                    return
                self._emit(build_media(self._sid, audio[i:i + frame]))
            self._emit(build_mark(self._sid, mark))
            self._log(f"-> say {name} ({len(audio) / tunables.SAMPLE_RATE:.1f} s)")


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
