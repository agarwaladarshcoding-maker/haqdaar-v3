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
import time
from typing import Any, Optional

from haqdaar.audio.mouth import Mouth
from haqdaar.contracts.types import Digit, Hangup, Input, Silence

HANGUP = "h"


class Turn:
    def __init__(self, mouth: Mouth, ear: Optional[Any] = None) -> None:
        self._mouth = mouth
        self.ear = ear
        self._keys: "queue.Queue[str]" = ear._keys if ear is not None else queue.Queue()
        self.hung_up = threading.Event()

    # --- socket loop ---------------------------------------------------------------
    def push_key(self, digit: str) -> None:
        """A key arrived. Stop whatever is playing, and keep the key for the engine."""
        if self._mouth.playing:
            self._mouth.clear()
        if self.ear is not None:
            self.ear.push_dtmf(digit)
        else:
            self._keys.put(digit)

    def push_hangup(self) -> None:
        self.hung_up.set()
        self._keys.put(HANGUP)
        if self.ear is not None:
            self.ear.push_hangup()

    def push_media(self, payload: bytes, is_ulaw: bool = True) -> None:
        """Push telephony audio packets to Ear."""
        if self.ear is not None:
            self.ear.push_media(payload, is_ulaw=is_ulaw)

    # --- engine thread -------------------------------------------------------------
    @property
    def keypad_only(self) -> bool:
        if self.ear is not None:
            return getattr(self.ear, "keypad_only", False)
        return False

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

    def wait_input(
        self,
        gap_s: float,
        profile: str = "normal",
        lang: str = "",
        hint: str = "",
    ) -> Input:
        """Wait for input: DTMF digit, spoken audio via Ear, silence, or hangup."""
        # 1. Any pre-queued DTMF key wins immediately
        if not self._keys.empty():
            key = self._keys.get_nowait()
            if key == HANGUP:
                return Hangup()
            return Digit(digit=key)

        if self.hung_up.is_set():
            return Hangup()

        # 2. Spoken profile with active Ear
        if profile in ("spoken", "turn0", "confirm") and self.ear is not None and not self.keypad_only:
            # Wait for line to finish playing before listening, checking for barge-in keys
            while self._mouth.remaining() > 0 and not self.hung_up.is_set():
                if not self._keys.empty():
                    key = self._keys.get_nowait()
                    if key == HANGUP:
                        return Hangup()
                    return Digit(digit=key)
                time.sleep(0.02)

            if self.hung_up.is_set():
                return Hangup()
            if not self._keys.empty():
                key = self._keys.get_nowait()
                if key == HANGUP:
                    return Hangup()
                return Digit(digit=key)

            if hasattr(self.ear, "drain_media"):
                self.ear.drain_media()
            return self.ear.listen(timeout=gap_s, lang=lang, hint=hint)

        # 3. Keypad mode (or normal profile)
        key = self.wait(gap_s)
        if key is None:
            return Silence(n=1)
        if key == HANGUP:
            return Hangup()
        return Digit(digit=key)
