"""haqdaar/sim.py

Console driver simulator for Haqdaar v2 (T17, Build-Plan Step 6).
Plays a whole call with keypad input typed at the terminal against fixtures/.
No audio hardware, no telephony, no network, no model.

Usage:
    make sim                       # interactive, type digits
    make demo-fixture              # all three personas, non-interactive
    python -m haqdaar.sim --persona p2
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
)
from haqdaar.data.corpus import Corpus
from haqdaar.data.log import Log
from haqdaar.data.pipeline.p6_snapshot import build_snapshot
from haqdaar.engine.call import Engine


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
    # Widened match: the caller cannot name a subject, Door A is struck out,
    #      and one rung of the ladder recovers a scheme. category now has all
    #      9 vocab.CATEGORY values as valid keys, so "0" (not "3") is the
    #      out-of-menu strike digit; the box asked right after the struck-out
    #      opener is income_band, not state (planner minimax order). S4's D6
    #      fixture migration gives it a real state constraint (MAHARASHTRA-
    #      only, like S3/S5), so state=OTHER excludes it too, and
    #      income_band=50000 (second band) misses both S1 and S2.
    "widened": ["1", "0", "0", "2", "2", "1", "3", "9", "2"],
}
DEFAULT_PERSONA: str = "p1"


class FakeAudio:
    """Console-based mock audio session for testing and simulation."""

    def __init__(
        self,
        language: Lang = "hi",
        canned_inputs: Optional[list[str]] = None,
        fallback: Optional[list[str]] = None,
    ) -> None:
        self.language: Lang = language
        self.fallback: list[str] = list(fallback) if fallback else list(PERSONAS[DEFAULT_PERSONA])
        self.played_lines: list[str] = []
        self._last_played: tuple[str, ...] = ()
        self.canned_inputs: list[str] = list(canned_inputs) if canned_inputs else []
        self._canned_idx: int = 0
        self._silence_count: int = 0

    def select_language(self) -> tuple[Lang, LangSource]:
        """Simulate Turn 0 trilingual language selection."""
        print("\n--- TURN 0: LANGUAGE SELECTION ---")
        print("[AUDIO PLAY] greeting_trilingual")
        self.played_lines.append("greeting_trilingual")

        val = self._get_next_raw_input("Select language: 1=Hindi, 2=Marathi, 3=English (default 1): ")
        if val == "2":
            self.language = "mr"
            return "mr", "keypad"
        elif val == "3":
            self.language = "en"
            return "en", "keypad"
        else:
            self.language = "hi"
            return "hi", "keypad" if val == "1" else "default"

    def say(self, sequence: tuple[str, ...]) -> None:
        """Simulate playing an audio sequence."""
        self._last_played = sequence
        for token in sequence:
            self.played_lines.append(token)
            print(f"[AUDIO SAY] {token}")

    def repeat(self) -> None:
        """Simulate replaying the last sequence."""
        print("[AUDIO REPEAT]")
        if self._last_played:
            for token in self._last_played:
                self.played_lines.append(token)
                print(f"[AUDIO SAY] {token}")

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

    def next_input(self, profile: str = "normal") -> Digit | Noise | Silence | Hangup:
        """Get next input from user, canned sequence, or non-interactive fallback."""
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
            return Digit(digit=digit_char)

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
) -> Path:
    """Run full simulation against fixtures/ and return path to log file."""
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

            c_id = call_id or f"sim_{int(time.time())}"
            log = Log.open(
                call_id=c_id,
                snapshot_id=snap_id,
                logs_dir=logs_dir,
            )

            audio = FakeAudio(
                canned_inputs=canned_inputs,
                fallback=PERSONAS.get(persona, PERSONAS[DEFAULT_PERSONA]),
            )

            print("==================================================")
            print(f"Starting Haqdaar Sim: call_id={c_id} persona={persona}")
            print("==================================================")

            Engine.run_call(
                audio=audio,
                model=None,
                corpus=corpus,
                log=log,
            )

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
        finally:
            tunables.SNAPSHOTS_DIR = orig_snap_dir
            tunables.AUDIO_DIR = orig_audio_dir


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
    args = ap.parse_args(argv)

    run_sim(
        canned_inputs=list(PERSONAS[args.persona]) if args.canned else None,
        call_id=args.call_id,
        logs_dir=args.logs_dir,
        persona=args.persona,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
