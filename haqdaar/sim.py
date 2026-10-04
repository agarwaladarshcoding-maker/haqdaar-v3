"""haqdaar/sim.py

Console driver simulator for Haqdaar v2 (T17, Build-Plan Step 6).
Plays a whole call with keypad input typed at the terminal against fixtures/.
No audio hardware, no telephony, no network, no model.

Usage:
    make sim                       # interactive, type digits
    make demo-fixture              # all three personas, non-interactive
    python -m haqdaar.sim --persona p2
    python -m haqdaar.sim --snapshot snapshots/CURRENT     # the real 12 schemes (plan 2.3)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
from typing import Any, Optional

from haqdaar.contracts import tunables
from haqdaar.contracts.types import (
    Digit,
    Hangup,
    Lang,
    LangSource,
    Noise,
    Silence,
    Speech,
)
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.data.trace import Trace
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.engine.call import Engine
from haqdaar.model.client import GroqModelClient, ModelClientResponse
from haqdaar.model.router import Model


class SimModelClient(GroqModelClient):
    """Offline simulated Groq client at the seam for simulation and tests."""

    def __init__(self, corpus: Any = None) -> None:
        super().__init__(api_key="sim_offline_key", model="llama-3.3-70b-versatile")
        self.corpus = corpus
        self.speech_fixtures: dict[str, Any] = {}
        manifest_path = Path(__file__).resolve().parent.parent / "fixtures" / "audio" / "speech" / "manifest.json"
        if manifest_path.exists():
            try:
                self.speech_fixtures = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                pass

    def call(
        self,
        messages: list[dict[str, str]],
        task: str = "model_opener",
    ) -> ModelClientResponse:
        user_content = messages[-1]["content"] if messages else ""

        if task == "model_opener":
            for k, item in self.speech_fixtures.items():
                txt = item.get("text", "")
                if txt and txt in user_content:
                    stamps = [
                        {"box": s["box"], "value": s["value"], "span": s["span"]}
                        for s in item.get("expected_stamps", [])
                    ]
                    return ModelClientResponse(success=True, data={"stamps": stamps}, latency_s=0.005)

            lower = user_content.lower()
            if any(w in lower for w in ("कृषी", "शेती", "farming", "farmer", "agriculture", "किसान", "खेती")):
                span = "कृषी" if "कृषी" in user_content else ("शेती" if "शेती" in user_content else "farming")
                return ModelClientResponse(
                    success=True,
                    data={"stamps": [{"box": "category", "value": "farming", "span": span}]},
                    latency_s=0.005,
                )
            if any(w in lower for w in ("व्यवसाय", "व्यापार", "business", "loan", "shop", "दुकान")):
                span = "व्यवसाय" if "व्यवसाय" in user_content else "business"
                return ModelClientResponse(
                    success=True,
                    data={"stamps": [{"box": "category", "value": "business_loans", "span": span}]},
                    latency_s=0.005,
                )
            # Unmatched opener speech returns UNCLEAR
            return ModelClientResponse(
                success=True,
                data={"class": "UNCLEAR", "stamps": []},
                latency_s=0.005,
            )

        elif task == "model_turn":
            lower = user_content.lower()
            if any(w in lower for w in ("repeat", "पुन्हा", "दोबारा", "फिर से")):
                return ModelClientResponse(success=True, data={"class": "REPEAT"}, latency_s=0.005)
            if any(w in lower for w in ("clarify", "help", "काय", "क्या", "madat")):
                return ModelClientResponse(success=True, data={"class": "CLARIFY"}, latency_s=0.005)

            if "farmer" in lower or "शेतकरी" in user_content or "किसान" in user_content:
                span = "शेतकरी" if "शेतकरी" in user_content else ("किसान" if "किसान" in user_content else "farmer")
                return ModelClientResponse(
                    success=True,
                    data={"class": "ANSWER", "box": "occupation", "value": "farmer", "span": span},
                    latency_s=0.005,
                )
            if any(w in lower for w in ("yes", "हो", "हाँ", "maharashtra")):
                span = "हो" if "हो" in user_content else ("हाँ" if "हाँ" in user_content else "yes")
                return ModelClientResponse(
                    success=True,
                    data={"class": "ANSWER", "box": "state", "value": "MAHARASHTRA", "span": span},
                    latency_s=0.005,
                )
            if any(w in lower for w in ("no", "नाही", "नहीं", "other")):
                span = "नाही" if "नाही" in user_content else ("नहीं" if "नहीं" in user_content else "no")
                return ModelClientResponse(
                    success=True,
                    data={"class": "ANSWER", "box": "state", "value": "OTHER", "span": span},
                    latency_s=0.005,
                )
            if any(w in lower for w in ("female", "महिला", "स्त्री")):
                span = "महिला" if "महिला" in user_content else ("स्त्री" if "स्त्री" in user_content else "female")
                return ModelClientResponse(
                    success=True,
                    data={"class": "ANSWER", "box": "gender", "value": "female", "span": span},
                    latency_s=0.005,
                )

            return ModelClientResponse(
                success=True,
                data={"class": "UNCLEAR", "reason": "unrecognized"},
                latency_s=0.005,
            )

        return ModelClientResponse(success=True, data={}, latency_s=0.005)



# Canned keypad runs for the three keypad-only personas. The first digit is the
# turn 0 language choice. See tests/test_call.py for what each one proves.
# Digits are keypad positions in vocab.py order (D6, step 1.5a), not the old
# alphabetical-over-discovered-values order. `state` D6 fixture migration:
# BIHAR -> ANY for the "central" schemes S1, S2, S4, S6 (key 2 = OTHER, "not
# in Maharashtra", still matches them); KARNATAKA -> MAHARASHTRA for S3, S5
# (key 1 = MAHARASHTRA).
PERSONAS: dict[str, list[str]] = {
    # P1 · direct match: farming from outside Maharashtra ("OTHER"), female,
    # SC -> named schemes (S1 is state=ANY/central, so it still matches).
    "p1": ["1", "1", "2", "1", "3", "9", "9", "9", "2"],
    # P2 · dead end: business_loans (handloom) from outside Maharashtra does
    # not exist — S5 (the sole business_loans scheme) is state=MAHARASHTRA-
    # only (D6). The ladder is exhausted and two nearest schemes are named as
    # non-matches.
    "p2": ["1", "2", "2", "1", "3", "2"],
    # P3 · second subject: Door B re-opens the opener and runs a second
    # terminal. state=OTHER carries over from round 1 (Door B clears only
    # category), so round 2's business_loans answer hard-misses S5 again.
    "p3": ["1", "1", "2", "1", "3", "0", "1", "2", "2"],
    # Widened match: the caller cannot name a subject, Door A is declined,
    #      and one rung of the ladder recovers a scheme. category now has all
    #      9 vocab.CATEGORY values as valid keys, so there is no out-of-menu
    #      strike digit left for it; "0" on the opener means "don't know"
    #      (D7/F8, step 1.6) and drops it to UNKNOWN in a single key, not two
    #      strikes. The box asked right after the declined opener is
    #      income_band, not state (planner minimax order). S4's D6 fixture
    #      migration gives it a real state constraint (MAHARASHTRA-only, like
    #      S3/S5), so state=OTHER excludes it too. income_band is now a band
    #      box (step 1.5b): the fixture corpus's bands are "0-29999",
    #      "30000-30000","30001-49999","50000-50000","50001-74999",
    #      "75000-75000","75001+" — key 4 picks "50000-50000", which misses
    #      both S1 (75000) and S2 (30000).
    "widened": ["1", "0", "4", "2", "1", "3", "9", "2"],
}
DEFAULT_PERSONA: str = "p1"


TURN0_LANGS = {"1": "hi", "2": "mr", "3": "en"}


class FakeAudio:
    """Console-based mock audio session for testing and simulation."""

    def __init__(
        self,
        language: Lang = "hi",
        canned_inputs: Optional[list[str]] = None,
        fallback: Optional[list[str]] = None,
        clock: Optional[Any] = None,
    ) -> None:
        self.language: Lang = language
        self.fallback: list[str] = list(fallback) if fallback else list(PERSONAS[DEFAULT_PERSONA])
        self.played_lines: list[str] = []
        self._last_played: tuple[str, ...] = ()
        self.canned_inputs: list[str] = list(canned_inputs) if canned_inputs else []
        self._canned_idx: int = 0
        self._silence_count: int = 0
        self.note: Any = lambda line: None  # the call trace, when _run_call sets one
        self.trace: Any = None

        # Gate state (Step 7.0b)
        self.prompt_n: int = 0
        self.prompt_open: bool = False
        self.prompt_start_t: float = 0.0
        self._answered_prompt_n: int = -1
        self._last_key_digit: str = ""
        self._last_key_t: float = -1000.0
        self._clock: Any = clock or time.monotonic
        self._pending_key: Optional[Digit] = None
        self._queued_keys: list[Digit] = []
        self._cut_tokens: set[str] = set()
        self.last_cut: Optional[tuple[str, int]] = None
        self.dropped_events: list[dict[str, Any]] = []
        self.trace_events: list[dict[str, Any]] = []
        self._scripted_cuts: dict[str, tuple[str, int]] = {}
        self._current_prompt: str = ""

    def select_language(self) -> tuple[Lang, LangSource]:
        """Simulate Turn 0 trilingual language selection."""
        print("\n--- TURN 0: LANGUAGE SELECTION ---")
        print("[AUDIO PLAY] greeting_trilingual")
        self.played_lines.append("greeting_trilingual")
        self.note("-> say greeting_trilingual")
        self.prompt_n = 1
        self.prompt_open = True
        self.prompt_start_t = self._clock()
        self._current_prompt = "greeting_trilingual"

        val = self._get_next_raw_input("Select language (key 1 is the first offered, default 1): ")
        picked = tunables.turn0_keys().get(val)
        self.note(f"<- key {val}: language {picked or 'hi'}")
        self.language = picked or "hi"
        return self.language, "keypad" if picked else "default"

    def say(self, sequence: tuple[str, ...]) -> None:
        """Simulate playing an audio sequence."""
        self._last_played = sequence
        prompt_name = sequence[0] if sequence else ""
        self._current_prompt = prompt_name
        self.prompt_n += 1
        self.prompt_open = True
        self.prompt_start_t = self._clock()
        for token in sequence:
            self.played_lines.append(token)
            print(f"[AUDIO SAY] {token}")
            self.note(f"-> say {token}")
            if token in self._scripted_cuts:
                cut_digit, cut_ms = self._scripted_cuts[token]
                self._cut_tokens.add(token)
                self.last_cut = (token, cut_ms)
                self.push_key(cut_digit, t=self.prompt_start_t + (cut_ms / 1000.0), cut_clip=token, heard_ms=cut_ms)
                break

    def say_text(self, text: str) -> bool:
        """Show a typed-out answer (7.1). The call viewer shows unknown trace lines as plain notes."""
        print(f"[AUDIO ANSWER] {text}")
        self.note(f"-> answer {text}")
        return True

    def repeat(self) -> None:
        """Simulate replaying the last sequence."""
        print("[AUDIO REPEAT]")
        self.prompt_n += 1
        self.prompt_open = True
        self.prompt_start_t = self._clock()
        if self._last_played:
            for token in self._last_played:
                self.played_lines.append(token)
                print(f"[AUDIO SAY] {token}")
                self.note(f"-> say {token}")

    def clear(self) -> None:
        """Simulate clearing audio playback buffer."""
        print("[AUDIO CLEAR]")

    def on_mark(self, mark: str) -> float:
        """Simulate mark playback confirmation."""
        print(f"[AUDIO MARK] {mark}")
        return time.time()

    def hangup(self) -> None:
        """Simulate call termination."""
        print("[AUDIO HANGUP]")

    def push_hangup(self) -> None:
        """Simulate hangup event arrival."""
        print("[AUDIO HANGUP]")
        self.prompt_open = False
        self._queued_keys.append(Hangup())

    def prefetch(self, scheme_ids: Any) -> None:
        """No-op prefetch in simulation."""
        pass

    def push_key(
        self,
        digit: str,
        t: Optional[float] = None,
        cut_clip: str = "",
        heard_ms: int = -1,
    ) -> bool:
        """Process an inbound DTMF key press through gate rules G1-G5, G8. Returns True if taken."""
        if t is None:
            t = self._clock()

        # G2: Repeat same key within KEY_REPEAT_MS on same prompt
        if (
            self.prompt_n == getattr(self, "_last_key_prompt_n", -1)
            and digit == self._last_key_digit
            and (t - self._last_key_t) < (tunables.KEY_REPEAT_MS / 1000.0)
        ):
            self._last_key_t = t
            self._log_event(event="key", value=digit, took=False, why="repeat", t=t, cut_clip=cut_clip, heard_ms=heard_ms)
            return False

        # G3 & G4 & G8: Prompt closed, extra keys for answered prompt, or gap
        if not self.prompt_open or self.prompt_n <= self._answered_prompt_n:
            self._last_key_digit = digit
            self._last_key_prompt_n = self.prompt_n
            self._last_key_t = t
            self._log_event(event="key", value=digit, took=False, why="prompt_closed", t=t, cut_clip=cut_clip, heard_ms=heard_ms)
            return False

        # G5: Guard window (first KEY_GUARD_MS of prompt)
        if self.prompt_start_t > 0.0 and (t - self.prompt_start_t) < (tunables.KEY_GUARD_MS / 1000.0):
            self._last_key_digit = digit
            self._last_key_prompt_n = self.prompt_n
            self._last_key_t = t
            self._log_event(event="key", value=digit, took=False, why="guard", t=t, cut_clip=cut_clip, heard_ms=heard_ms)
            return False

        # Key passed gate!
        self._last_key_digit = digit
        self._last_key_prompt_n = self.prompt_n
        self._last_key_t = t
        self._answered_prompt_n = self.prompt_n
        self.prompt_open = False
        k = Digit(digit=digit, prompt_n=self.prompt_n, cut_clip=cut_clip, heard_ms=heard_ms)
        self._queued_keys.append(k)
        self._log_event(event="key", value=digit, took=True, why="ok", t=t, cut_clip=cut_clip, heard_ms=heard_ms)
        return True

    def _log_event(
        self,
        event: str,
        value: str,
        took: bool,
        why: str,
        t: float,
        cut_clip: str = "",
        heard_ms: int = -1,
    ) -> None:
        rec = {
            "ts": t,
            "prompt_n": self.prompt_n,
            "prompt": getattr(self, "_current_prompt", ""),
            "event": event,
            "value": value,
            "took": took,
            "why": why,
            "cut_clip": cut_clip,
            "heard_ms": heard_ms,
        }
        self.trace_events.append(rec)
        if not took:
            self.dropped_events.append(rec)
        if self.trace is not None and hasattr(self.trace, "input_event"):
            self.trace.input_event(
                prompt_n=self.prompt_n,
                prompt=getattr(self, "_current_prompt", ""),
                event=event,
                value=value,
                took=took,
                why=why,
                cut_clip=cut_clip,
                heard_ms=heard_ms,
                ts=t,
            )

    def pending_key(self) -> Optional[Digit]:
        """Return pending key if one arrived for the open prompt (G7)."""
        if self._pending_key is not None:
            k = self._pending_key
            self._pending_key = None
            return k
        if self._queued_keys:
            return self._queued_keys.pop(0)
        return None

    def was_cut(self, token: str) -> bool:
        if token in self._cut_tokens:
            return True
        if self.last_cut and (self.last_cut[0] == token or token in self.last_cut[0] or self.last_cut[0] in token):
            return True
        return False

    def script_cut(self, clip: str, key: str, ms: int = 150) -> None:
        """Script a barge-in key that cuts a specific clip after ms milliseconds."""
        self._scripted_cuts[clip] = (key, ms)

    def next_input(self, profile: str = "normal") -> Digit | Noise | Silence | Hangup | Speech:
        """The next input, noted in the call trace in the same words the phone server uses."""
        inp = self._next_input(profile)
        if isinstance(inp, Digit):
            self.note(f"<- key {inp.digit} ({profile})")
        elif isinstance(inp, Speech):
            self.note(f'<- speech "{inp.text}"')
        elif isinstance(inp, Silence):
            self.note(f"<- silence {inp.n} ({profile})")
        elif isinstance(inp, Noise):
            self.note("<- noise")
        elif isinstance(inp, Hangup):
            self.note("stop    caller hung up")
        return inp

    def _next_input(self, profile: str = "normal") -> Digit | Noise | Silence | Hangup | Speech:
        """Get next input from user, canned sequence, or non-interactive fallback."""
        if self._queued_keys:
            return self._queued_keys.pop(0)

        while self.canned_inputs and self._canned_idx < len(self.canned_inputs):
            cand = self.canned_inputs[self._canned_idx].strip()
            self._canned_idx += 1

            if cand.lower().startswith("gap_key:"):
                key_digit = cand.split(":", 1)[1].strip()
                prev_open = self.prompt_open
                self.prompt_open = False
                self.push_key(key_digit)
                self.prompt_open = prev_open
                continue

            elif cand.lower().startswith("fast_keys:"):
                keys_list = [k.strip() for k in cand.split(":", 1)[1].split(",")]
                now = self._clock() + 0.3
                for i, k in enumerate(keys_list):
                    self.push_key(k, t=now + (i * 0.05))
                if self._queued_keys:
                    return self._queued_keys.pop(0)
                continue

            elif cand.lower().startswith("key_after_speech:"):
                parts = cand.split(":", 1)[1].split(",", 1)
                txt = parts[0].strip()
                key = parts[1].strip() if len(parts) > 1 else "1"
                self._pending_key = Digit(digit=key, prompt_n=self.prompt_n)
                return Speech(text=txt, prompt_n=self.prompt_n)

            elif cand.lower().startswith("cut_clip:"):
                parts = cand.split(":", 1)[1].split(",", 1)
                clip = parts[0].strip()
                key = parts[1].strip() if len(parts) > 1 else "1"
                self.script_cut(clip, key)
                continue

            elif cand.lower().startswith(("say:", "speech:")):
                txt = cand.split(":", 1)[1].strip()
                print(f"[AUDIO STT ({profile})] Canned speech: {txt}")
                return Speech(text=txt, prompt_n=self.prompt_n)

            elif cand.lower() in ("s", "silence"):
                self._silence_count += 1
                return Silence(n=self._silence_count)

            elif cand.lower() in ("n", "noise"):
                self._silence_count = 0
                return Noise()

            elif cand.lower() in ("h", "hangup"):
                return Hangup()

            elif cand.lower().startswith(("key:", "dtmf:")):
                digit = cand.split(":", 1)[1].strip()
                t = max(self._clock(), self.prompt_start_t + 0.3)
                if self.push_key(digit, t=t):
                    return self._queued_keys.pop(0)
                continue

            elif cand in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "#"):
                t = max(self._clock(), self.prompt_start_t + 0.3)
                if self.push_key(cand, t=t):
                    return self._queued_keys.pop(0)
                continue

            else:
                return Speech(text=cand, prompt_n=self.prompt_n)

        if profile == "spoken":
            if sys.stdin.isatty() and not self.canned_inputs:
                prompt_text = f"[VOICE ({profile})] Speak / type answer (or s=silence, n=noise, h=hangup, or digit): "
                val = input(prompt_text).strip()
                if val.lower() in ("s", "silence"):
                    self._silence_count += 1
                    return Silence(n=self._silence_count)
                elif val.lower() in ("n", "noise"):
                    self._silence_count = 0
                    return Noise()
                elif val.lower() in ("h", "hangup"):
                    return Hangup()
                elif val.isdigit() and len(val) == 1:
                    t = max(self._clock(), self.prompt_start_t + 0.3)
                    if self.push_key(val, t=t):
                        return self._queued_keys.pop(0)
                elif val:
                    return Speech(text=val, prompt_n=self.prompt_n)

            # Simulated speech at the seam for non-interactive / canned keys:
            simulated_speech = {
                "mr": "मला कृषी योजना हवी आहे",
                "hi": "मुझे कृषि योजना चाहिए",
                "en": "I am looking for agriculture schemes",
            }.get(self.language, "I am looking for agriculture schemes")
            print(f"[AUDIO STT (spoken)] Simulated speech: {simulated_speech}")
            return Speech(text=simulated_speech, prompt_n=self.prompt_n)

        prompt_text = f"[KEYPAD ({profile})] Enter digit (0-9, *, #, s=silence, n=noise, h=hangup): "
        val = self._get_next_raw_input(prompt_text).lower()

        if val in ("s", "silence"):
            self._silence_count += 1
            return Silence(n=self._silence_count)
        elif val in ("n", "noise"):
            self._silence_count = 0
            return Noise()
        elif val in ("h", "hangup"):
            return Hangup()
        else:
            self._silence_count = 0
            digit_char = val if val in ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "#") else "1"
            t = max(self._clock(), self.prompt_start_t + 0.3)
            self.push_key(digit_char, t=t)
            if self._queued_keys:
                return self._queued_keys.pop(0)
            return Digit(digit=digit_char, prompt_n=self.prompt_n)

    def _get_next_raw_input(self, prompt: str) -> str:
        """Read input string from canned list or interactive terminal."""
        if self.canned_inputs and self._canned_idx < len(self.canned_inputs):
            res = self.canned_inputs[self._canned_idx]
            self._canned_idx += 1
            print(f"{prompt}{res} (canned)")
            return res

        if sys.stdin.isatty():
            try:
                return input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[INPUT EOF]")
                return "h"

        # Non-interactive fallback: keep walking the selected persona, then hang up
        # rather than answering forever with one hardcoded digit.
        if self._canned_idx < len(self.fallback):
            res = self.fallback[self._canned_idx]
        else:
            res = "h"
        self._canned_idx += 1
        print(f"{prompt}{res} (auto)")
        return res


def run_sim(
    canned_inputs: Optional[list[str]] = None,
    call_id: Optional[str] = None,
    logs_dir: str = "logs",
    persona: str = DEFAULT_PERSONA,
    snapshot: Optional[str] = None,
    model: Optional[Any] = None,
    spoken: bool = True,
    audio: Optional["FakeAudio"] = None,
    real_model: bool = False,
) -> Path:
    """Run full simulation against fixtures/ and return path to log file.

    With `snapshot` (an id, "CURRENT", or a path like snapshots/CURRENT) the call runs on that
    built snapshot and its real audio pool instead of a throwaway fixture snapshot.
    """
    if snapshot is not None:
        corpus = Corpus.load(Path(snapshot).name)
        return _run_call(corpus, corpus.snapshot_id, canned_inputs, call_id, logs_dir, persona, model=model, spoken=spoken, audio=audio, real_model=real_model)

    root_dir = Path(__file__).resolve().parent.parent
    fixtures_dir = root_dir / "fixtures"
    schemes_file = fixtures_dir / "schemes.jsonl"

    schemes: list[dict[str, Any]] = []
    with open(schemes_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                if row.get("scheme_id") != "S6":
                    schemes.append(row)

    with tempfile.TemporaryDirectory() as td:
        snap_dir = Path(td) / "snapshots"
        audio_dir = Path(td) / "audio"
        snap_dir.mkdir(parents=True, exist_ok=True)
        audio_dir.mkdir(parents=True, exist_ok=True)

        orig_snap_dir = tunables.SNAPSHOTS_DIR
        orig_audio_dir = tunables.AUDIO_DIR
        tunables.SNAPSHOTS_DIR = str(snap_dir)
        tunables.AUDIO_DIR = str(audio_dir)

        try:
            snap_id = build_snapshot(
                schemes_data=schemes,
                snapshot_id="sim_fixtures_snap",
                snapshots_dir=snap_dir,
                audio_dir=audio_dir,
                render_stubs=True,
            )
            corpus = Corpus.load(snap_id)
            return _run_call(corpus, snap_id, canned_inputs, call_id, logs_dir, persona, model=model, spoken=spoken, audio=audio, real_model=real_model)
        finally:
            tunables.SNAPSHOTS_DIR = orig_snap_dir
            tunables.AUDIO_DIR = orig_audio_dir


def _run_call(
    corpus: Corpus,
    snap_id: str,
    canned_inputs: Optional[list[str]],
    call_id: Optional[str],
    logs_dir: str,
    persona: str,
    model: Optional[Any] = None,
    spoken: bool = True,
    audio: Optional["FakeAudio"] = None,
    real_model: bool = False,
) -> Path:
    """One call on a loaded corpus. Returns the log path."""
    c_id = call_id or f"sim_{int(time.time())}"
    log = Log.open(
        call_id=c_id,
        snapshot_id=snap_id,
        logs_dir=logs_dir,
    )

    audio = audio or FakeAudio(
        canned_inputs=canned_inputs,
        fallback=PERSONAS.get(persona, PERSONAS[DEFAULT_PERSONA]),
    )
    # The timed copy of this call for the call page (`make calls-ui`).
    trace = Trace(c_id, logs_dir, snap_id)
    log.tap = trace.record
    audio.note = trace

    print("==================================================")
    print(f"Starting Haqdaar Sim: call_id={c_id} persona={persona}")
    print("==================================================")

    if model is None and spoken:
        # real_model: the typed test call with QA_ENABLED on, which needs the live Model.
        client = None if real_model else SimModelClient(corpus)
        model = Model(corpus=corpus, client=client)

    Engine.run_call(
        audio=audio,
        model=model,
        corpus=corpus,
        log=log,
    )

    trace(f"call    {c_id} finished")
    trace.close()

    log_path = Path(logs_dir) / f"{c_id}.jsonl"
    print("==================================================")
    print(f"Simulation completed. LOG written to: {log_path}")
    print("==================================================")

    if log_path.exists():
        print("\n--- Persisted LOG Lines ---")
        with open(log_path, "r", encoding="utf-8") as f:
            for l in f:
                print(l.strip())

    return log_path


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Haqdaar console call simulator")
    ap.add_argument(
        "--persona",
        choices=sorted(PERSONAS),
        default=DEFAULT_PERSONA,
        help="which canned keypad run to use when stdin is not a terminal",
    )
    ap.add_argument(
        "--canned",
        action="store_true",
        help="use the persona's digits even at a terminal (no typing)",
    )
    ap.add_argument("--call-id", default=None)
    ap.add_argument("--logs-dir", default="logs")
    ap.add_argument(
        "--snapshot",
        default=None,
        help="run on a built snapshot and its real audio, e.g. snapshots/CURRENT",
    )
    ap.add_argument(
        "--keys",
        default=None,
        help='the keys to press, space-separated, e.g. "2 1 1 s h" (s=silence, h=hang up)',
    )
    ap.add_argument(
        "--spoken",
        action="store_true",
        default=None,
        help="enable spoken mode with simulated STT/model",
    )
    ap.add_argument(
        "--keypad-only",
        action="store_true",
        help="force keypad-only mode without model",
    )
    args = ap.parse_args(argv)

    if args.keys is not None:
        canned = args.keys.split()
        spoken = not args.keypad_only
    else:
        canned = list(PERSONAS[args.persona]) if args.canned else None
        # Persona runs without explicit --spoken or --keys run keypad-only
        spoken = False if args.keypad_only or (args.canned and not args.spoken) else bool(args.spoken)

    run_sim(
        canned_inputs=canned,
        call_id=args.call_id,
        logs_dir=args.logs_dir,
        persona=args.persona,
        snapshot=args.snapshot,
        spoken=spoken,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

