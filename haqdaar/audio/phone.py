"""haqdaar/audio/phone.py

Plan 2.7 — the engine's `audio` on a real phone line.

The engine speaks in tokens: a fixed line id ("section_menu"), a scheme chunk
("scheme:pmfby:summary"), or a mark ("name:pmfby", "end:pmfby"). PhoneAudio turns each token into
its clip through the corpus (token -> render key) and the pool (render key -> bytes), and hands
the clips to Mouth. Keys and silence come from Turn.

A keypad question ("keypad_age", and "opener_prompt" for the topic) is followed by its menu:
each choice's chip, then "press N.", then "press 0 if you do not know" (D13). The engine only
names the question; the menu is built here from `corpus.values(box)`, in the same order the
engine reads the digit back.

A clip that cannot be found is logged and skipped, never raised: a missing word is bad, a dead
call is worse. Corpus.load has already refused any snapshot with a missing clip.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from haqdaar.audio.lines import MENU_KEYS
from haqdaar.audio.mouth import Clip, Mouth
from haqdaar.audio.turn import HANGUP, Turn
from haqdaar.contracts import tunables
from haqdaar.contracts.types import SCHEME_CHUNKS, Digit, Hangup, Input, Lang, LangSource, Noise, Silence, Speech

# Which box a question token asks about, so its menu can follow it.
MENU_BOX: dict[str, str] = {
    "opener_prompt": "category",
    "keypad_gender": "gender",
    "keypad_social_category": "social_category",
    "keypad_age": "age",
    "keypad_income_band": "income_band",
    "keypad_occupation": "occupation",
}
TURN0_KEYS: dict[str, Lang] = {"1": "hi", "2": "mr", "3": "en"}
# Played even over a waiting key: the call is ending, nothing comes after it to answer.
ALWAYS_SAY: frozenset[str] = frozenset({"closing_farewell"})


class PhoneAudio:
    def __init__(
        self,
        corpus: Any,
        pool: Any,
        mouth: Mouth,
        turn: Turn,
        close: Callable[[], None],
        log: Callable[[str], None] = lambda line: None,
    ) -> None:
        self.corpus = corpus
        self.pool = pool
        self.mouth = mouth
        self.turn = turn
        self._close = close
        self._log = log
        self.language: Lang = "hi"
        self._silence = 0

    # --- what the engine calls -----------------------------------------------------
    def select_language(self) -> tuple[Lang, LangSource]:
        self.say(("greeting_trilingual",))
        key = self.turn.wait(tunables.TURN0_GAP_S)
        if key in TURN0_KEYS:
            self.language = TURN0_KEYS[key]
            self._log(f"<- key {key}: language {self.language}")
            return self.language, "keypad"
        self.language = "hi"
        self._log(f"<- {'no key' if key is None else 'key ' + key}: language hi (default)")
        return self.language, "default"

    def say(self, sequence: tuple[str, ...]) -> None:
        if self.turn.has_key() and not ALWAYS_SAY.intersection(sequence):
            # The caller has already answered (barge-in): do not talk over the next step.
            self._log(f"   skip {' '.join(sequence)} (a key is waiting)")
            return
        clips: list[Clip] = []
        for token in sequence:
            clips.extend(self._clips(token))
        if clips:
            self.mouth.play(clips)

    def repeat(self) -> None:
        self.mouth.repeat()

    def clear(self) -> None:
        self.mouth.clear()

    def on_mark(self, mark: str) -> float:
        return time.time()

    @property
    def keypad_only(self) -> bool:
        return getattr(self.turn, "keypad_only", False)

    def next_input(self, profile: str = "normal") -> Input:
        if hasattr(self.turn, "wait_input"):
            inp = self.turn.wait_input(tunables.SILENCE_GAP_S, profile=profile, lang=self.language)
            if isinstance(inp, Silence):
                self._silence += 1
                inp = Silence(n=self._silence)
                self._log(f"<- silence {self._silence} ({profile})")
            elif isinstance(inp, Digit):
                self._silence = 0
                self._log(f"<- key {inp.digit} ({profile})")
            elif isinstance(inp, (Speech, Noise)):
                self._silence = 0
            return inp

        key = self.turn.wait(tunables.SILENCE_GAP_S)
        if key is None:
            self._silence += 1
            self._log(f"<- silence {self._silence} ({profile})")
            return Silence(n=self._silence)
        self._silence = 0
        if key == HANGUP:
            return Hangup()
        self._log(f"<- key {key} ({profile})")
        return Digit(digit=key)

    def hangup(self) -> None:
        """Let the goodbye finish playing, then end the call."""
        deadline = time.monotonic() + tunables.HANGUP_WAIT_S
        while self.mouth.remaining() > 0 and not self.turn.hung_up.is_set():
            if time.monotonic() > deadline:
                break
            time.sleep(0.1)
        self._close()

    # --- tokens -> clips -----------------------------------------------------------
    def _clips(self, token: str) -> list[Clip]:
        if token.startswith(("name:", "end:")):
            return []  # engine bookkeeping marks, not speech
        if token.startswith("scheme:"):
            _, sid, section = token.split(":", 2)
            keys = self.corpus.chunks(sid, self.language)
            ix = SCHEME_CHUNKS.index(section) if section in SCHEME_CHUNKS else -1
            return self._clip(token, keys[ix] if 0 <= ix < len(keys) else "")
        lang = "all" if token == "greeting_trilingual" else self.language
        clips = self._clip(token, self.corpus.audio(token, lang))
        box = MENU_BOX.get(token)
        if box:
            clips.extend(self._menu(box))
        return clips

    def _menu(self, box: str) -> list[Clip]:
        clips: list[Clip] = []
        for n, value in zip(MENU_KEYS, self.corpus.values(box)):
            clips += self._clip(f"chip_{box}_{value}", self.corpus.audio(box, self.language, value))
            clips += self._clip(f"key_{n}", self.corpus.audio(f"key_{n}", self.language))
        clips += self._clip(
            "keypad_unknown_suffix", self.corpus.audio("keypad_unknown_suffix", self.language)
        )
        return clips

    def _clip(self, name: str, render_key: str) -> list[Clip]:
        if not render_key:
            self._log(f"!! no clip for {name} [{self.language}]")
            return []
        try:
            return [(name, bytes(self.pool.get(render_key)))]
        except Exception as e:
            self._log(f"!! clip {name} [{self.language}] failed: {e!r}")
            return []
