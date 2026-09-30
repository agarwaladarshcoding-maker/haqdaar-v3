"""haqdaar/data/pipeline/run_all.py

Step 1.15 (plan 1.13, D11) — run the whole pipeline, and count what it costs.

    python -m haqdaar.data.pipeline.run_all              # p2 -> p6, no paid step runs
    python -m haqdaar.data.pipeline.run_all --yes        # allow the paid steps
    python -m haqdaar.data.pipeline.run_all --rescrape --yes
    python -m haqdaar.data.pipeline.run_all --cost       # just the bill, run nothing

Two rules from D11, and the whole file exists to keep them:

1. **No paid work without being asked.** p1 (scraping), p3 (Groq) and p4 (Sarvam) can spend
   money or hammer someone's site. They run only with `--yes`, and p1 additionally only with
   `--rescrape`, because the raw cache does not expire. Without the flags the step is SKIPPED
   and said so, not run quietly.
2. **A warm run is free.** p3 and p4 are content-addressed, so running them again after a
   clean run makes zero requests. `--cost` reads the ledgers and shows it.

The steps are deliberately run in-process rather than as subprocesses: a step that raises
should stop the pipeline with its own traceback, not a return code nobody reads.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from haqdaar.contracts import tunables

REPORTS_DIR = Path("data_cache/reports")
GROQ_LEDGER = REPORTS_DIR / "groq_usage.jsonl"
SARVAM_LEDGER = REPORTS_DIR / "sarvam_usage.jsonl"
SARVAM_TTS_LEDGER = REPORTS_DIR / "sarvam_tts_usage.jsonl"


class Step:
    """One pipeline step: what it is called, whether it spends, and how to run it."""

    def __init__(self, name: str, paid: bool, run: Callable[[], Any], needs_rescrape: bool = False):
        self.name = name
        self.paid = paid
        self.run = run
        self.needs_rescrape = needs_rescrape


def _steps() -> list[Step]:
    # Imported inside, so `--cost` needs none of the pipeline's dependencies.
    from haqdaar.data.pipeline import (
        p1_scrape,
        p2_derive,
        p3_cards,
        p4_translate,
        p5_gates,
    )

    return [
        Step("p1 scrape", paid=True, run=p1_scrape.run_pipeline_scrape, needs_rescrape=True),
        Step("p2 derive", paid=True, run=p2_derive.run_pipeline_extract),
        Step("p3 cards", paid=True, run=p3_cards.run_cards),
        Step("p4 translate", paid=True, run=p4_translate.run_translate),
        Step("p4 lines", paid=True, run=p4_translate.run_translate_lines),
        Step("p5 gates", paid=False, run=p5_gates.run_gates),
        Step("p6 snapshot", paid=False, run=_run_snapshot),
    ]


def _run_snapshot() -> int:
    """Build a snapshot from what p2..p5 wrote, and say what audio is still missing."""
    from haqdaar.data.pipeline.texts import _load_schemes, all_texts, missing

    derived_dir = Path(tunables.CARDS_FILE).parent
    schemes = _load_schemes(derived_dir)
    texts = all_texts(schemes)
    gaps = missing(schemes)
    print(f"texts the call can say: {len(texts)}")
    print(f"texts still missing: {len(gaps)}")
    return 0


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a half-written line is not worth failing a cost report over
    return rows


def print_cost() -> int:
    """What has been spent so far, from the two ledgers.

    These are running totals over every run ever made, not the cost of one run: the ledgers
    are append-only on purpose, so a bill cannot be made to look smaller by re-running.
    """
    groq = _read_ledger(GROQ_LEDGER)
    sarvam = _read_ledger(SARVAM_LEDGER)

    print("Groq (cards, facets, aliases, summary)")
    print(f"  requests: {len(groq)}")
    prompt = sum(int(r.get("prompt_tokens") or 0) for r in groq)
    completion = sum(int(r.get("completion_tokens") or 0) for r in groq)
    print(f"  prompt tokens: {prompt}")
    print(f"  completion tokens: {completion}")
    print(f"  tokens total: {prompt + completion}")
    by_task: dict[str, int] = defaultdict(int)
    for row in groq:
        by_task[str(row.get("task") or "?")] += 1
    for task in sorted(by_task):
        print(f"    {task}: {by_task[task]} requests")

    print("Sarvam Translate")
    print(f"  requests: {len(sarvam)}")
    chars = sum(int(r.get("chars") or 0) for r in sarvam)
    print(f"  chars: {chars}")
    by_lang: dict[str, int] = defaultdict(int)
    for row in sarvam:
        by_lang[str(row.get("lang") or "?")] += int(row.get("chars") or 0)
    for lang in sorted(by_lang):
        print(f"    {lang}: {by_lang[lang]} chars")

    tts = _read_ledger(SARVAM_TTS_LEDGER)
    print("Sarvam TTS (make render)")
    print(f"  requests: {len(tts)}")
    print(f"  chars: {sum(int(r.get('chars') or 0) for r in tts)}")
    tts_by_lang: dict[str, int] = defaultdict(int)
    for row in tts:
        tts_by_lang[str(row.get("lang") or "?")] += int(row.get("chars") or 0)
    for lang in sorted(tts_by_lang):
        print(f"    {lang}: {tts_by_lang[lang]} chars")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--cost" in argv:
        return print_cost()

    yes = "--yes" in argv
    rescrape = "--rescrape" in argv

    for step in _steps():
        skip_reason = None
        if step.needs_rescrape and not rescrape:
            skip_reason = "needs --rescrape (the raw cache does not expire)"
        elif step.paid and not yes:
            skip_reason = "paid step, needs --yes"

        if skip_reason:
            print(f"== {step.name}: SKIPPED, {skip_reason}")
            continue

        print(f"== {step.name}")
        rc = step.run()
        if isinstance(rc, int) and rc != 0:
            print(f"{step.name} failed with {rc}", file=sys.stderr)
            return rc

    print()
    print("== cost so far")
    print_cost()
    return 0


if __name__ == "__main__":
    sys.exit(main())
