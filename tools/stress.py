"""tools/stress.py

Plan 3.6 — many random keypad callers against a real snapshot, through the real engine.

    make stress                  # 1,000 callers on snapshots/CURRENT
    make stress N=200 SEED=7

Each caller presses random keys: mostly menu digits, with some 0 ("don't know"), `#`, `*`,
silence, noise, and an early hang-up. Every call's delivery log is then read back and checked:

  crash         the engine raised. Must be 0.
  truth         a scheme was read that contradicts an answer: an answered box whose mask does
                not include the scheme. Boxes the widening ladder may drop (WIDENING_ORDER) are
                excused only on a call whose log says ladder_rung > 0. Must be 0.

It also reports questions per call, schemes read, endings, and how long each keypad menu is
(the chips and "press N" clips in seconds), so a menu too long to sit through shows up here.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import random
import statistics
import sys
import tempfile
import traceback
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from haqdaar.contracts import tunables
from haqdaar.data.corpus import Corpus
from haqdaar.engine.call import Engine

from haqdaar.contracts.types import UNKNOWN, WIDENING_ORDER
from haqdaar.data.log import Log
from haqdaar.sim import FakeAudio

KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]


def random_keys(rng: random.Random, n: int = 40) -> list[str]:
    """One caller's key presses: the language, then a mix a real caller might make."""
    out = [rng.choice(["1", "2", "3", "3", "s"])]
    for _ in range(n):
        r = rng.random()
        if r < 0.62:
            out.append(rng.choice(KEYS[:5]) if rng.random() < 0.7 else rng.choice(KEYS))
        elif r < 0.74:
            out.append("0")
        elif r < 0.80:
            out.append("#")
        elif r < 0.84:
            out.append("*")
        elif r < 0.92:
            out.append("s")
        elif r < 0.97:
            out.append("n")
        else:
            out.append("h")
            break
    return out


class ScriptedCaller(FakeAudio):
    """FakeAudio that never reads the keyboard: out of keys means hang up."""

    def _get_next_raw_input(self, prompt: str) -> str:
        if self._canned_idx < len(self.canned_inputs):
            self._canned_idx += 1
            return self.canned_inputs[self._canned_idx - 1]
        return "h"


def _scheme_index(corpus: Corpus) -> dict[str, int]:
    ix: dict[str, int] = {}
    while corpus.scheme_id(len(ix)):  # "" past the end
        ix[corpus.scheme_id(len(ix))] = len(ix)
    return ix


def check_truth(rows: list[dict[str, Any]], corpus: Corpus, index: dict[str, int]) -> list[str]:
    """Every scheme read must fit every answer the caller gave (except ladder-dropped boxes)."""
    # Walk the log in order: "anything else" -> 1 starts a new round with a new topic, so each
    # scheme is checked against the answers given before it was read, not the call's last ones.
    rung = max((int(r.get("ladder_rung", 0) or 0) for r in rows if "ladder_rung" in r), default=0)
    problems = []
    answers: dict[str, Any] = {}
    for row in rows:
        if row.get("class") == "ANSWER" and row.get("box"):
            answers[row["box"]] = row.get("value")
            continue
        if not ("slug" in row and "ending" in row):
            continue
        slug = row["slug"]
        bit = 1 << index[slug]
        for box, value in answers.items():
            if value in (UNKNOWN, "UNKNOWN", None, ""):
                continue
            if rung > 0 and box in WIDENING_ORDER:
                continue
            if not corpus.mask(box, value) & bit:
                problems.append(f"{slug} read, but {box}={value}")
    return problems


def menu_seconds(corpus: Corpus, lang: str) -> dict[str, float]:
    """How long each keypad menu plays: every choice's chip + "press N" + the "press 0" line."""
    from haqdaar.audio.lines import MENU_KEYS
    from haqdaar.audio.phone import MENU_BOX

    audio_dir = Path(tunables.AUDIO_DIR)

    def secs(key: str) -> float:
        p = audio_dir / f"{key}.ulaw"
        return p.stat().st_size / tunables.SAMPLE_RATE if key and p.exists() else 0.0

    out = {}
    for token, box in MENU_BOX.items():
        total = secs(corpus.audio(token, lang)) + secs(corpus.audio("keypad_unknown_suffix", lang))
        for n, value in zip(MENU_KEYS, corpus.values(box)):
            total += secs(corpus.audio(box, lang, value)) + secs(corpus.audio(f"key_{n}", lang))
        out[box] = total
    return out


def run(n: int, seed: int, snapshot: str = "CURRENT") -> dict[str, Any]:
    corpus = Corpus.load(snapshot)
    index = _scheme_index(corpus)
    rng = random.Random(seed)
    crashes: list[str] = []
    truth: list[str] = []
    questions: list[int] = []
    read_counts: list[int] = []
    stops: Counter[str] = Counter()
    endings: Counter[str] = Counter()
    langs: Counter[str] = Counter()

    with tempfile.TemporaryDirectory() as logs_dir:
        for i in range(n):
            keys = random_keys(rng)
            call_id = f"stress_{seed}_{i}"
            try:
                log = Log.open(call_id=call_id, snapshot_id=corpus.snapshot_id, logs_dir=logs_dir)
                audio = ScriptedCaller(canned_inputs=keys)
                with contextlib.redirect_stdout(io.StringIO()):
                    Engine.run_call(audio=audio, model=None, corpus=corpus, log=log)
            except Exception:
                crashes.append(f"{call_id} keys={' '.join(keys)}\n{traceback.format_exc(limit=3)}")
                continue
            path = Path(logs_dir) / f"{call_id}.jsonl"
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
            for p in check_truth(rows, corpus, index):
                truth.append(f"{call_id} keys={' '.join(keys)}: {p}")
            questions.append(sum(1 for r in rows if r.get("class") == "ANSWER" and r.get("box")))
            read_counts.append(sum(1 for r in rows if "slug" in r and "ending" in r))
            stops.update(r["stop"] for r in rows if "stop" in r)
            endings.update(r["ending"] for r in rows if "ending" in r)
            langs.update(r["lang"] for r in rows if r.get("lang_source"))
    return {
        "calls": n, "crashes": crashes, "truth": truth, "questions": questions,
        "read": read_counts, "stops": stops, "endings": endings, "langs": langs,
        "menus": {lang: menu_seconds(corpus, lang) for lang in ("hi", "mr", "en")},
        "schemes": len(index),
    }


def print_report(r: dict[str, Any]) -> None:
    q, rd = r["questions"] or [0], r["read"] or [0]
    print(f"callers {r['calls']} on {r['schemes']} schemes")
    print(f"  crashes {len(r['crashes'])}   truth failures {len(r['truth'])}")
    print(f"  questions per call: median {statistics.median(q)}, max {max(q)}")
    print(f"  schemes read per call: median {statistics.median(rd)}, max {max(rd)}, none {rd.count(0)}")
    print(f"  how calls stopped: {dict(r['stops'].most_common())}")
    print(f"  scheme endings: {dict(r['endings'].most_common())}")
    print("  keypad menu length, seconds (hi / mr / en):")
    for box in r["menus"]["hi"]:
        print(f"    {box:16s} " + " / ".join(f"{r['menus'][l][box]:5.1f}" for l in ("hi", "mr", "en")))
    for line in (r["crashes"] + r["truth"])[:10]:
        print("  !! " + line)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("-n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--snapshot", default="CURRENT")
    a = ap.parse_args(argv)
    r = run(a.n, a.seed, a.snapshot)
    print_report(r)
    return 1 if r["crashes"] or r["truth"] else 0


if __name__ == "__main__":
    sys.exit(main())
