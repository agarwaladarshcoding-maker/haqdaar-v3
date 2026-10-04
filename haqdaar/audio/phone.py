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
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from haqdaar.audio import live_tts
from haqdaar.audio.lines import MENU_KEYS
from haqdaar.audio.mouth import Clip, Mouth
from haqdaar.audio.turn import HANGUP, Turn
from haqdaar.contracts import tunables
from haqdaar.contracts.types import (
    SCHEME_CHUNKS, Digit, Hangup, Input, Lang, LangSource, Noise, Silence, Speech, compute_render_key,
)

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
        trace: Optional[Any] = None,
        speak: Optional[Callable[[str, str], Optional[bytes]]] = None,
    ) -> None:
        self.corpus = corpus
        self.pool = pool
        self.mouth = mouth
        self.turn = turn
        self._close = close
        self._log = log
        self.trace = trace
        if trace is None and hasattr(log, "input_event"):
            self.trace = log
        if hasattr(self.turn, "trace") and getattr(self.turn, "trace", None) is None:
            self.turn.trace = self.trace
        if hasattr(self.turn, "_log"):
            self.turn._log = self._log
        self._speak = speak   # text, lang -> mu-law bytes or None; live Sarvam when not given
        self.language: Lang = "hi"
        self._silence = 0
        self._token_clips: dict[str, list[str]] = {}   # token -> names of the clips it played
        self._filler = False   # 7.4: "one_moment" was said and not yet stopped

    # --- what the engine calls -----------------------------------------------------
    def select_language(self) -> tuple[Lang, LangSource] | Input:
        """Say the greeting and wait once. A language key gives (lang, "keypad"). Anything
        else comes back as the input it was (Silence, Hangup, a wrong key): the engine asks
        again, so no language is ever picked for a caller who did not pick one."""
        self.say(("greeting_trilingual",))
        key = self.turn.wait(tunables.TURN0_GAP_S)
        if key in tunables.turn0_keys():
            self._silence = 0
            self.language = tunables.turn0_keys()[key]
            self._log(f"<- key {key}: language {self.language}")
            return self.language, "keypad"
        if key is None:
            self._silence += 1
            self._log(f"<- silence {self._silence} (turn0)")
            return Silence(n=self._silence)
        if key == HANGUP:
            return Hangup()
        self._silence = 0
        self._log(f"<- key {key}: not a language")
        return Digit(digit=key)

    def say(self, sequence: tuple[str, ...]) -> None:
        clips: list[Clip] = []
        for token in sequence:
            made = self._clips(token)
            self._token_clips[token] = [name for name, _ in made]
            clips.extend(made)
        if clips:
            self._play(clips, sequence[0] if sequence else "")
        self._filler = sequence == ("one_moment",) and bool(clips)

    def say_text(self, text: str) -> bool:
        """Say a sentence made during the call (QA_SPEAK). False: nothing was said."""
        if not tunables.QA_SPEAK or self.turn.hung_up.is_set():
            return False
        lang = self.language
        text = live_tts.clean(text, lang)
        if not text:
            return False
        t0 = time.monotonic()
        key = compute_render_key(text, lang)
        audio = self._saved_answer(key)
        cached = audio is not None
        if audio is None:
            audio = (self._speak or live_tts.speak)(text, lang)
        self._log(
            f"-> live say answer ({len(text)} chars, {time.monotonic() - t0:.1f} s, "
            f"{'cached' if cached else 'rendered' if audio else 'failed'})"
        )
        if not audio:
            return False
        if not cached:
            self._save_answer(key, audio)
        self._token_clips["answer"] = ["answer"]
        self.stop_filler()  # after the render, so the filler covers the wait and the answer never queues behind it
        self._play([("answer", bytes(audio))], "answer")
        return True

    def stop_filler(self) -> None:
        """7.4: cut "one_moment" if it is still sounding. Never waits. Not a caller cut, so
        was_cut() must not see it."""
        if not self._filler:
            return
        self._filler = False
        if self.mouth.remaining() > 0:
            self.mouth.clear()
            self.mouth.last_cut = ("", -1)

    def heard(self, token: str) -> bool:
        """Did every clip of the last say() of `token` play to its end?"""
        names = self._token_clips.get(token, [token])
        return bool(names) and all(self.mouth.clip_heard(n) for n in names)

    def repeat(self) -> None:
        n = self.turn.start_prompt("repeat") if hasattr(self.turn, "start_prompt") else None
        if n:
            self.mouth.repeat(tag=(n, "repeat"))
        else:
            self.mouth.repeat()

    def clear(self) -> None:
        self.mouth.clear()

    def pending_key(self) -> Optional[Digit]:
        """Check for a pending key stamped for the open prompt (G7)."""
        if hasattr(self.turn, "get_pending_key"):
            return self.turn.get_pending_key()
        return None

    def was_cut(self, token: str) -> bool:
        """Was the last thing said cut by a key before it ended (G11)? Any cut since the last
        say() means `token` was not heard to the end."""
        cut_clip, _ = getattr(self.mouth, "last_cut", ("", -1))
        return cut_clip != ""

    def on_mark(self, mark: str) -> float:
        if hasattr(self.mouth, "on_mark"):
            self.mouth.on_mark(mark)
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

    def prefetch(self, scheme_ids: Iterable[str]) -> None:
        """Prefetch scheme audio chunks into Tier 1 LRU cache.

        Resolved via Corpus.chunks() and AudioPool.prefetch().
        Must never block or crash the call: failures log and continue.
        """
        if not tunables.AUDIO_PREFETCH_ON_STOP:
            return
        if not hasattr(self, "pool") or self.pool is None:
            return
        try:
            keys: list[str] = []
            for sid in scheme_ids:
                if hasattr(self.corpus, "chunks"):
                    chunks = self.corpus.chunks(sid, self.language)
                    if chunks:
                        keys.extend(chunks)
            if keys and hasattr(self.pool, "prefetch"):
                self.pool.prefetch(keys)
        except Exception as e:
            self._log(f"!! prefetch failed: {e!r}")

    def _play(self, clips: list[Clip], prompt_name: str) -> None:
        """One prompt: the Turn counts it, the Mouth plays it tagged so a key is stamped with
        the prompt that is sounding, not the newest one queued."""
        n = self.turn.start_prompt(prompt_name) if hasattr(self.turn, "start_prompt") else None
        if n:
            self.mouth.play(clips, tag=(n, prompt_name))
        else:
            self.mouth.play(clips)

    def _saved_answer(self, key: str) -> Optional[bytes]:
        """A live answer said before: same text, language and voice, same sound. Free."""
        try:
            return bytes(self.pool.get(key))
        except Exception:
            return None

    def _save_answer(self, key: str, audio: bytes) -> None:
        """Keep it in the pool's folder under its render key. A failed save only costs a re-render."""
        try:
            path = Path(self.pool.audio_dir) / f"{key}.ulaw"
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(audio)
            tmp.replace(path)
        except Exception as e:
            self._log(f"!! answer not saved: {e!r}")

    # --- tokens -> clips -----------------------------------------------------------
    def _clips(self, token: str) -> list[Clip]:
        if token.startswith(("name:", "end:")):
            return []  # engine bookkeeping marks, not speech
        if token.startswith("scheme:"):
            parts = token.split(":", 2)
            if len(parts) != 3:
                self._log(f"!! malformed scheme token: {token!r}")
                return []
            _, sid, section = parts
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
