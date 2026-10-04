"""haqdaar/audio/turn.py

Plan 2.6 & Step 7.0b — what the caller does: keys, silence, or hanging up.

The socket loop pushes keys in; the audio gate stamps each key with prompt_n, time,
and playback cut state. wait_input gives back only keys that pass fixed gate rules:
- G1: Key while prompt clip plays -> cuts clip, key is answer
- G2: Repeat within KEY_REPEAT_MS -> dropped, logged
- G3/G4/G8: Extra keys after answered prompt / keys in gap -> dropped, logged
- G5: Key in first KEY_GUARD_MS of prompt -> dropped, logged
- G7: Key stamped for open prompt beats speech / router
- G10: Hangup is its own event, never a key Digit("h")
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import queue
import threading
import time
from typing import Any, Callable, Optional

from haqdaar.audio.mouth import Mouth
from haqdaar.contracts import tunables
from haqdaar.contracts.types import Digit, Hangup, Input, Noise, Silence, Speech

HANGUP = "h"


@dataclass
class StampedKey:
    digit: str
    prompt_n: int
    t: float
    prompt_open: bool
    prompt_start_t: float
    prompt_name: str
    cut_clip: str = ""
    heard_ms: int = -1
    # The prompt that was really sounding (the engine may have queued several). Trace only:
    # the gate still judges the key against prompt_n, the prompt the engine waits on.
    sound_n: int = -1
    sound_name: str = ""

    def stamp(self) -> tuple[int, str]:
        if self.sound_n >= 0:
            return self.sound_n, self.sound_name
        return self.prompt_n, self.prompt_name


class Turn:
    def __init__(
        self,
        mouth: Mouth,
        ear: Optional[Any] = None,
        trace: Optional[Any] = None,
        log: Callable[[str], None] = lambda line: None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._mouth = mouth
        self.ear = ear
        self.trace = trace
        self._log = log
        self._clock = clock
        self.hung_up = threading.Event()
        self.prompt_n: int = 0
        self.prompt_open: bool = True
        self.prompt_start_t: float = 0.0
        self.current_prompt_name: str = ""
        self._last_key_digit: str = ""
        self._last_key_prompt_n: int = -1
        self._last_key_t: float = 0.0
        self._answered_prompt_n: int = -1
        self._stashed_key: Optional[Digit] = None
        self._keys: "queue.Queue[StampedKey]" = queue.Queue()
        self._lock = threading.Lock()
        if self.ear is not None:
            self.ear._turn_gate = self

    # --- engine thread prompt state ------------------------------------------------
    def start_prompt(self, name: str = "") -> int:
        """Advance prompt_n when a prompt begins to sound on the line."""
        with self._lock:
            self.prompt_n += 1
            self.prompt_open = True
            self.prompt_start_t = self._clock()
            self.current_prompt_name = name
            return self.prompt_n

    def _log_event(
        self,
        event: str,
        value: str,
        took: bool,
        why: str,
        prompt_n: Optional[int] = None,
        prompt_name: Optional[str] = None,
        cut_clip: str = "",
        heard_ms: int = -1,
        t: Optional[float] = None,
    ) -> None:
        p_n = prompt_n if prompt_n is not None else self.prompt_n
        p_name = prompt_name if prompt_name is not None else self.current_prompt_name
        if self.trace is not None and hasattr(self.trace, "input_event"):
            self.trace.input_event(
                prompt_n=p_n,
                prompt=p_name,
                event=event,
                value=value,
                took=took,
                why=why,
                cut_clip=cut_clip,
                heard_ms=heard_ms,
                ts=t,
            )
        elif self._log is not None:
            if not took:
                self._log(f"   dropped {event} {value} ({why})")
            else:
                self._log(f"   took {event} {value} ({why})")

    def _sounding(self) -> Optional[tuple[int, str]]:
        return getattr(self._mouth, "sounding", lambda: None)()

    # --- socket loop ---------------------------------------------------------------
    def push_key(self, digit: str) -> None:
        """A key arrived. Stop whatever is playing, and stamp the key with prompt_n and time."""
        now = self._clock()
        cut_clip, heard_ms = ("", -1)
        was_playing = self._mouth.playing
        sound = self._sounding() if was_playing else None
        # A key in the guard window will be dropped (G5): it must not cut the new prompt.
        in_guard = self.prompt_n > 1 and (now - self.prompt_start_t) < (tunables.KEY_GUARD_MS / 1000.0)
        if was_playing and not in_guard:
            cut_clip, heard_ms = self._mouth.clear()

        with self._lock:
            is_open = self.prompt_open or was_playing
            sk = StampedKey(
                digit=digit,
                prompt_n=self.prompt_n,
                t=now,
                prompt_open=is_open,
                prompt_start_t=self.prompt_start_t,
                prompt_name=self.current_prompt_name,
                cut_clip=cut_clip,
                heard_ms=heard_ms,
                sound_n=sound[0] if sound else -1,
                sound_name=sound[1] if sound else "",
            )
            self._keys.put(sk)

        if self.ear is not None:
            self.ear.push_dtmf(digit)

    def push_hangup(self) -> None:
        self.hung_up.set()
        self.prompt_open = False
        sound = self._sounding()
        self._log_event(
            event="hangup", value="", took=True, why="ok",
            prompt_n=sound[0] if sound else None,
            prompt_name=sound[1] if sound else None,
        )
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

    def get_valid_key(self, block: bool = False, timeout: Optional[float] = None) -> Optional[Digit]:
        """Fetch and gate the next key according to G2, G3, G4, G5, G8."""
        if self._stashed_key is not None:
            k = self._stashed_key
            self._stashed_key = None
            return k

        deadline = self._clock() + (timeout if timeout is not None else 0.0)
        while True:
            try:
                if block:
                    rem = deadline - self._clock()
                    if timeout is not None and rem <= 0:
                        return None
                    wait_s = rem if timeout is not None else None
                    sk = self._keys.get(timeout=wait_s)
                else:
                    sk = self._keys.get_nowait()
            except queue.Empty:
                return None

            # Gate evaluation:
            # G2: Repeat check (same key within KEY_REPEAT_MS on same prompt)
            if (
                sk.prompt_n == self._last_key_prompt_n
                and sk.digit == self._last_key_digit
                and (sk.t - self._last_key_t) < (tunables.KEY_REPEAT_MS / 1000.0)
            ):
                self._last_key_t = sk.t
                self._log_event(
                    event="key",
                    value=sk.digit,
                    took=False,
                    why="repeat",
                    prompt_n=sk.stamp()[0],
                    prompt_name=sk.stamp()[1],
                    cut_clip=sk.cut_clip,
                    heard_ms=sk.heard_ms,
                )
                continue

            # G3 & G4 & G8: Prompt closed, extra keys for answered prompt, or gap
            # Also a key stamped for an older prompt: it must not answer a prompt it never heard.
            if not sk.prompt_open or sk.prompt_n <= self._answered_prompt_n or sk.prompt_n < self.prompt_n:
                self._last_key_digit = sk.digit
                self._last_key_prompt_n = sk.prompt_n
                self._last_key_t = sk.t
                self._log_event(
                    event="key",
                    value=sk.digit,
                    took=False,
                    why="prompt_closed",
                    prompt_n=sk.stamp()[0],
                    prompt_name=sk.stamp()[1],
                    cut_clip=sk.cut_clip,
                    heard_ms=sk.heard_ms,
                )
                continue

            # G5: Guard window (first KEY_GUARD_MS of a new prompt, dropped because meant for one before)
            if sk.prompt_n > 1 and sk.prompt_start_t > 0 and (sk.t - sk.prompt_start_t) < (tunables.KEY_GUARD_MS / 1000.0):
                self._last_key_digit = sk.digit
                self._last_key_prompt_n = sk.prompt_n
                self._last_key_t = sk.t
                self._log_event(
                    event="key",
                    value=sk.digit,
                    took=False,
                    why="guard",
                    prompt_n=sk.stamp()[0],
                    prompt_name=sk.stamp()[1],
                    cut_clip=sk.cut_clip,
                    heard_ms=sk.heard_ms,
                )
                continue

            # Key passed all gate checks! (G1, G9, ok)
            with self._lock:
                self._last_key_digit = sk.digit
                self._last_key_prompt_n = sk.prompt_n
                self._last_key_t = sk.t
                self._answered_prompt_n = sk.prompt_n
                self.prompt_open = False

            self._log_event(
                event="key",
                value=sk.digit,
                took=True,
                why="ok",
                prompt_n=sk.stamp()[0],
                prompt_name=sk.stamp()[1],
                cut_clip=sk.cut_clip,
                heard_ms=sk.heard_ms,
            )
            return Digit(digit=sk.digit, prompt_n=sk.prompt_n, cut_clip=sk.cut_clip, heard_ms=sk.heard_ms)

    def get_pending_key(self) -> Optional[Digit]:
        """Look for a key stamped for the open prompt (G7)."""
        return self.get_valid_key(block=False)

    def has_key(self) -> bool:
        """A valid key is waiting."""
        if self._stashed_key is not None:
            return True
        key = self.get_valid_key(block=False)
        if key is not None:
            self._stashed_key = key
            return True
        return False

    def wait(self, gap_s: float) -> Optional[str]:
        """The next key, HANGUP, or None after `gap_s` of quiet once the line stops playing."""
        inp = self.wait_input(gap_s=gap_s, profile="normal")
        if isinstance(inp, Digit):
            return inp.digit
        if isinstance(inp, Hangup):
            return HANGUP
        return None

    def wait_input(
        self,
        gap_s: float,
        profile: str = "normal",
        lang: str = "",
        hint: str = "",
    ) -> Input:
        """Wait for input: DTMF digit, spoken audio via Ear, silence, or hangup."""
        if self.hung_up.is_set():
            self.prompt_open = False
            return Hangup()

        # 1. Any pre-queued DTMF key that passes gate wins immediately
        key = self.get_valid_key(block=False)
        if key is not None:
            return key

        if self.hung_up.is_set():
            self.prompt_open = False
            return Hangup()

        # 2. Spoken profile with active Ear. The results menu (readback) listens for words only
        # when questions are on (7.1 rule 11).
        spoken = ("spoken", "turn0", "confirm") + (("readback",) if tunables.QA_ENABLED else ())
        if profile in spoken and self.ear is not None and not self.keypad_only:
            # The caller's voice may stop a playing clip (S1-S7). Never on turn0 (S5).
            cut_in = (
                tunables.SPEECH_CUT_IN
                and profile != "turn0"
                and hasattr(self.ear, "watch_voice")
            )
            if cut_in:
                self.ear.drain_media()
                self.ear.start_watch()
            cut: Optional[tuple[str, int]] = None
            stamp: Optional[tuple[int, str]] = None   # the prompt the cut clip belonged to
            # Wait for line to finish playing before listening, checking for barge-in keys
            while self._mouth.remaining() > 0 and not self.hung_up.is_set():
                key = self.get_valid_key(block=False)
                if key is not None:
                    return key
                if cut_in:
                    in_guard = self.prompt_start_t > 0 and (
                        self._clock() - self.prompt_start_t < tunables.KEY_GUARD_MS / 1000.0
                    )
                    heard = self.ear.watch_voice(in_guard)
                    if heard == "short":
                        self._log_event(event="speech", value="", took=False, why="short_voice")
                    elif heard == "cut":
                        sound = self._sounding()
                        cut = self._mouth.clear()
                        stamp = sound
                        break
                time.sleep(0.02)

            if self.hung_up.is_set():
                self.prompt_open = False
                return Hangup()
            key = self.get_valid_key(block=False)
            if key is not None:
                if cut is not None:
                    self._log_event(event="speech", value="", took=False, why="key_beat_speech")
                return key

            if cut_in:
                inp = self.ear.listen(timeout=gap_s, lang=lang, hint=hint, resume=True)
            else:
                if hasattr(self.ear, "drain_media"):
                    self.ear.drain_media()
                inp = self.ear.listen(timeout=gap_s, lang=lang, hint=hint)
            if isinstance(inp, Hangup):
                self.prompt_open = False
                return Hangup()
            if isinstance(inp, Digit):
                if cut is not None:
                    self._log_event(event="speech", value="", took=False, why="key_beat_speech")
                self.prompt_open = False
                return inp
            if isinstance(inp, (Silence, Noise)):
                self.prompt_open = False
                return inp
            # Speech: prompt stays open until confirm / router
            if isinstance(inp, Speech):
                if cut is not None:
                    self._log_event(
                        event="speech", value=inp.text, took=True, why="cut_in",
                        cut_clip=cut[0], heard_ms=cut[1],
                        prompt_n=stamp[0] if stamp else None, prompt_name=stamp[1] if stamp else None,
                    )
                    return replace(inp, prompt_n=self.prompt_n, cut_clip=cut[0], heard_ms=cut[1])
                return replace(inp, prompt_n=self.prompt_n)
            return inp

        # 3. Keypad mode (or normal profile)
        deadline = self._clock() + self._mouth.remaining() + gap_s
        while True:
            if self.hung_up.is_set():
                self.prompt_open = False
                return Hangup()
            key = self.get_valid_key(block=True, timeout=0.05)
            if key is not None:
                return key
            now = self._clock()
            if self._mouth.remaining() > 0:
                deadline = max(deadline, now + self._mouth.remaining() + gap_s)
            elif now >= deadline:
                break

        if self.hung_up.is_set():
            self.prompt_open = False
            return Hangup()
        self.prompt_open = False
        return Silence(n=1)
