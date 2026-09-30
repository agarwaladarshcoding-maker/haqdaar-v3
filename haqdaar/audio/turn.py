"""haqdaar/audio/turn.py

Plan 2.6 — what the caller does: keys, silence, or hanging up.

The socket loop pushes keys in; the engine thread waits here for the next one. The silence
clock starts only when the line has finished playing (Mouth.remaining() reaches 0), so a long
scheme reading never counts as the caller being silent.

Keys are never thrown away. A key pressed while a prompt, a retry line or a "not understood"
line is playing stops that line (barge-in) and stays in the queue, so the next wait() returns it
at once. The 15 Sep demo lost those keys and made the caller press twice (NOTES "Kept key").
"""
from __future__ import annotations

import queue
import threading
from typing import Optional

from haqdaar.audio.mouth import Mouth

HANGUP = "h"


class Turn:
    def __init__(self, mouth: Mouth) -> None:
        self._mouth = mouth
        self._keys: "queue.Queue[str]" = queue.Queue()
        self.hung_up = threading.Event()

    # --- socket loop ---------------------------------------------------------------
    def push_key(self, digit: str) -> None:
        """A key arrived. Stop whatever is playing, and keep the key for the engine."""
        if self._mouth.playing:
            self._mouth.clear()
        self._keys.put(digit)

    def push_hangup(self) -> None:
        self.hung_up.set()
        self._keys.put(HANGUP)

    # --- engine thread -------------------------------------------------------------
    def has_key(self) -> bool:
        """A key is waiting. The engine should not start a new line over it."""
        return not self._keys.empty()

    def wait(self, gap_s: float) -> Optional[str]:
        """The next key, HANGUP, or None after `gap_s` of quiet once the line stops playing."""
        while True:
            try:
                return self._keys.get(timeout=self._mouth.remaining() + gap_s)
            except queue.Empty:
                if self._mouth.remaining() > 0:
                    continue  # still talking (more audio was queued): the gap has not begun
                return None
