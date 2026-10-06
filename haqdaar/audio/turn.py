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

from haqdaar.audio.lang_words import language_from_words
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


# Sounds a listener makes while the other side talks. Not an answer to anything.
FILLER_SOUNDS: frozenset[str] = frozenset({
    "hmm", "hm", "hmmm", "mm", "mmm", "mhm", "uh", "um", "umm", "uh huh", "हम्म", "हूँ", "हूं", "हं",
})
# Words that only mean "I am listening" while a clip plays. At a yes/no they may be a yes.
FILLER_WORDS: frozenset[str] = FILLER_SOUNDS | frozenset({
    "ok", "okay", "accha", "achha", "acha", "अच्छा", "ओके", "बरं",
})


def real_words(text: str) -> int:
    """How many of the words are more than a listening sound ("hmm", "ok", "अच्छा")."""
    words = (w.strip(" .,!?।…\"'-").lower() for w in text.split())
    return len([w for w in words if w and w not in FILLER_WORDS])


class Turn:
    keys_mode: bool = False   # 3.1: the call is in its keys part: every key works as in a keys call

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
        self._gap_watch: bool = False   # 7.5: newer_input already started this busy time's voice watch
        self._ear_on: bool = False      # 2.2: the voice watch began at the reply's first sound
        self._push: tuple[str, int, float] = ("", -1, 0.0)   # the last key that came in: digit, prompt_n, time
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

    def _talk_ignores(self, digit: str, prompt_name: str) -> bool:
        """2.4: in a talk call a key the talk does not act on must not stop the voice or answer the
        prompt. It still comes through and is logged "keys are off". Acted on: key 9 (the photo link),
        the keys key (6, goes to keys), and the language keys while the greeting sounds (any key there
        works as before). In the keys part of a call no key is stray."""
        if not tunables.TALK_ONLY or self.keys_mode or prompt_name == "greeting_trilingual":
            return False
        return not ((tunables.PHOTO_IN_CALL and digit == "9") or (tunables.KEYS_IN_TALK and digit == tunables.KEYS_KEY))

    # --- socket loop ---------------------------------------------------------------
    def push_key(self, digit: str) -> None:
        """A key arrived. Stop whatever is playing, and stamp the key with prompt_n and time."""
        now = self._clock()
        cut_clip, heard_ms = ("", -1)
        was_playing = self._mouth.playing
        sound = self._sounding() if was_playing else None
        # A key in the guard window will be dropped (G5): it must not cut the new prompt.
        in_guard = self.prompt_n > 1 and (now - self.prompt_start_t) < (tunables.KEY_GUARD_MS / 1000.0)
        # The same key again within KEY_REPEAT_MS will be dropped too (G2): it must not cut either.
        last_digit, last_n, last_t = self._push
        repeat = digit == last_digit and self.prompt_n == last_n and (now - last_t) < (tunables.KEY_REPEAT_MS / 1000.0)
        self._push = (digit, self.prompt_n, now)
        stray = self._talk_ignores(digit, sound[1] if sound else self.current_prompt_name)
        if was_playing and not in_guard and not repeat and not stray:
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
        if tunables.TALK_ONLY:      # 7.13: a talk call has no keys to fall back to; keep listening
            return False
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
            stray = self._talk_ignores(sk.digit, sk.stamp()[1])
            with self._lock:
                self._last_key_digit = sk.digit
                self._last_key_prompt_n = sk.prompt_n
                self._last_key_t = sk.t
                if not stray:   # 2.4: a stray key answered nothing: a key 9 after it in the same reply still counts
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

    def newer_input(self, gap_s: float, lang: str = "") -> Optional[Input]:
        """7.5: the caller spoke while the engine was busy. Their words, or None if they stayed quiet.

        Reads what the ear queued during the busy time with the same voice test as the cut-in,
        then listens on to the end of the utterance. Waits only while the caller is still
        talking. Never judged by the key guards: those are for keys, and keys keep their rules.
        """
        ear = self.ear
        if (
            ear is None
            or self.hung_up.is_set()
            or self.keypad_only
            or not tunables.SPEECH_CUT_IN
            or not hasattr(ear, "watch_voice")
        ):
            return None
        if not self._gap_watch:
            # The first look of a busy time starts clean; later looks carry on, so a few words
            # that began just before the last look are not cut short.
            ear.start_watch()
            self._gap_watch = True
        if ear.watch_voice(False) != "cut":
            return None
        self._gap_watch = False
        inp = ear.listen(timeout=gap_s, lang=lang, resume=True)
        return inp if isinstance(inp, (Speech, Digit)) else None

    def ear_on(self) -> None:
        """2.2: a talk reply's first sound goes out. The cut-in gate listens from here, not from when
        the whole reply is queued: what the caller says over the start of the reply is kept for
        wait_input instead of being thrown away there. Only with the gate on."""
        if (
            not (tunables.CUT_IN_GATE and tunables.TALK_ONLY)
            or self.ear is None
            or self.keypad_only
            or not hasattr(self.ear, "watch_voice")
        ):
            return
        self.ear.drain_media()
        self.ear.start_watch()
        self._ear_on = True

    def _false_cut(self, inp: Input, profile: str) -> bool:
        """Did the caller's sound stop a clip without being an input? Sound with no words, or a
        listening sound ("hmm", "accha"). Never when speech-to-text broke (the engine must
        hear of that). At a yes/no or the language pick only a bare sound counts, never a word."""
        if isinstance(inp, Noise):
            return not self.keypad_only
        if isinstance(inp, Speech):
            word = inp.text.strip(" .,!?।…").lower()
            return word in (FILLER_SOUNDS if profile in ("confirm", "greeting") else FILLER_WORDS)
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
        self._gap_watch = False
        early, self._ear_on = self._ear_on, False
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
        # when questions are on (7.1 rule 11). "greeting" (7.5) is the language pick: unlike
        # "turn0" the voice cuts it, and the words are heard.
        spoken = ("spoken", "turn0", "confirm", "greeting") + (("readback",) if tunables.QA_ENABLED else ())
        if profile in spoken and self.ear is not None and not self.keypad_only:
            # The caller's voice may stop a playing clip (S1-S7). Never on turn0 (S5).
            # 7.14 (B5) the strict gate of a talk call: more voice is needed to pause the agent,
            # and fewer than CUT_IN_GATE_WORDS real words means it says the cut sentence again.
            # 2.3: the greeting too: real words over it stop it and are turn 1 (the language pick keeps them).
            gate = tunables.CUT_IN_GATE and tunables.TALK_ONLY and profile in ("spoken", "greeting")
            cut_in = (
                ((tunables.SPEECH_CUT_IN and profile != "turn0") or gate)
                and hasattr(self.ear, "watch_voice")
            )
            # 2.2: a watch begun at the reply's first sound carries on: its sound is the caller's, not stale.
            early = early and gate and cut_in
            if cut_in and not early:
                self.ear.drain_media()
                self.ear.start_watch()
            false_cuts = 0
            while True:
                cut: Optional[tuple[str, int]] = None
                stamp: Optional[tuple[int, str]] = None   # the prompt the cut clip belonged to
                # Wait for line to finish playing before listening, checking for barge-in keys
                while self._mouth.remaining() > 0 and not self.hung_up.is_set():
                    key = self.get_valid_key(block=False)
                    if key is not None:
                        return key
                    if cut_in:
                        # No guard on an early watch: the guard starts when a sentence is queued, not when
                        # it sounds, so it would throw away (or start again) voice heard since the reply began.
                        in_guard = not early and self.prompt_start_t > 0 and (
                            self._clock() - self.prompt_start_t < tunables.KEY_GUARD_MS / 1000.0
                        )
                        need_ms = tunables.CUT_IN_GREETING_MS if profile == "greeting" else tunables.CUT_IN_GATE_MS
                        heard = (self.ear.watch_voice(in_guard, need_ms, tunables.CUT_IN_GATE_GAP_MS)
                                 if gate else self.ear.watch_voice(in_guard))
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
                # A cut that was no input (a cough, "hmm"): say the cut clips again and wait on,
                # as if nothing happened. No turn, no strike, no words lost.
                if gate:
                    nothing = isinstance(inp, Noise) or (
                        isinstance(inp, Speech) and real_words(inp.text) < tunables.CUT_IN_GATE_WORDS
                        and not (profile == "greeting" and language_from_words(inp.text)))   # "English" is the pick, not a false cut
                else:
                    nothing = false_cuts < tunables.CUT_IN_FALSE_MAX and self._false_cut(inp, profile)
                if (
                    cut is not None and cut[0]
                    and nothing
                    and getattr(self._mouth, "resume", lambda: False)()
                ):
                    false_cuts += 1
                    if gate and false_cuts >= tunables.CUT_IN_FALSE_MAX:
                        cut_in = False      # a noisy place: the rest of this reply is said with strict turns
                    self._log_event(
                        event="speech", value=getattr(inp, "text", ""), took=False, why="false_cut",
                        cut_clip=cut[0], heard_ms=cut[1],
                        prompt_n=stamp[0] if stamp else None, prompt_name=stamp[1] if stamp else None,
                    )
                    self.ear.drain_media()
                    self.ear.start_watch()
                    continue
                break
            if isinstance(inp, Hangup):
                self.prompt_open = False
                return Hangup()
            if isinstance(inp, Digit):
                if cut is not None:
                    self._log_event(event="speech", value="", took=False, why="key_beat_speech")
                self.prompt_open = False
                return inp
            if isinstance(inp, Silence):
                self.prompt_open = False
                return inp
            if isinstance(inp, Noise):
                # Sound with no words is not an answer: the phone waits on, so a key that comes
                # next must still be taken (a closed prompt dropped it, call ..50a7a2).
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
