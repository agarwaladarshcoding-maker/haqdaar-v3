"""tools/judge.py

Offline delivery log judge (PLAN-V2 5.2, T04, T16, T18).
Evaluates call delivery logs alone: pass/fail from D9 delivery records + turn lines.
No audio, no re-running the engine. Stdlib-only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Optional, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from haqdaar.contracts.log_schema import (
    STOP_LE_4_SURVIVORS,
    STOP_MAX_QUESTIONS,
    STOP_MAX_TURNS,
    STOP_NO_SPLIT,
    STOP_REASONS,
    STOP_ZERO_SURVIVORS,
)
from haqdaar.contracts.tunables import STOP_SURVIVORS
from haqdaar.contracts.types import UNASKED, UNKNOWN, WIDENING_ORDER
from haqdaar.data.corpus import Corpus
from haqdaar.engine.filter import Filter

ALLOWED_SECTIONS = {
    "summary",
    "benefit_text",
    "how_to_apply",
    "documents",
    "who_can_apply",
}

VALID_TERMINAL_ENDINGS = {
    "direct_match",
    "overflow",
    "widened_match",
    "nearest",
}


class JudgeResult:
    """Outcome of judging a single call log."""

    def __init__(self, passed: bool, call_id: str, reason: str, log_path: Optional[Path] = None):
        self.passed = passed
        self.call_id = call_id
        self.reason = reason
        self.log_path = log_path

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"<JudgeResult {status} {self.call_id}: {self.reason}>"


def _load_corpus_for_snapshot(snapshot_id: Optional[str], custom_snapshot: Optional[str] = None) -> Optional[Corpus]:
    """Attempt to load Corpus for the given snapshot id or path without raising."""
    candidates: list[str] = []
    if custom_snapshot:
        candidates.append(custom_snapshot)
        candidates.append(Path(custom_snapshot).name)

    if snapshot_id:
        candidates.append(snapshot_id)
        candidates.append(f"snapshots/{snapshot_id}")

    # Fallback to CURRENT
    candidates.append("CURRENT")
    candidates.append("snapshots/CURRENT")

    for cand in candidates:
        try:
            cand_path = Path(cand)
            if cand_path.name == "CURRENT" and cand_path.is_file():
                content = cand_path.read_text(encoding="utf-8").strip()
                return Corpus.load(Path(content).name)
            return Corpus.load(cand_path.name if cand_path.is_dir() else cand)
        except Exception:
            continue
    return None


def judge_call_log(
    log_source: Path | str | list[dict[str, Any]],
    corpus: Optional[Corpus] = None,
    snapshot: Optional[str] = None,
) -> JudgeResult:
    """Judge a single call log (from a file path or in-memory list of record dicts).

    FAIL iff any of T04's three conditions:
      (1) untrue — named scheme not in survivors, nearest read as matches,
          dead-end without the widening step, benefit/document claim outside the corpus;
      (2) system hung up unprompted (close reason shows system-side close before terminal);
      (3) ended before a terminal state (read-back started / honest dead-end / keypad-only-then-terminal).
    """
    records: list[dict[str, Any]] = []
    log_path: Optional[Path] = None

    if isinstance(log_source, (str, Path)):
        log_path = Path(log_source)
        if not log_path.exists() or log_path.stat().st_size == 0:
            return JudgeResult(passed=False, call_id=log_path.stem, reason="empty or missing log file", log_path=log_path)
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line_idx, line in enumerate(f, 1):
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        records.append(json.loads(line_str))
                    except json.JSONDecodeError as e:
                        return JudgeResult(
                            passed=False,
                            call_id=log_path.stem,
                            reason=f"invalid JSON at line {line_idx}: {e}",
                            log_path=log_path,
                        )
        except Exception as e:
            return JudgeResult(passed=False, call_id=log_path.stem, reason=f"cannot read log: {e}", log_path=log_path)
    else:
        records = list(log_source)

    if not records:
        cid = log_path.stem if log_path else "unknown"
        return JudgeResult(passed=False, call_id=cid, reason="no log records found", log_path=log_path)

    # 1. Identify header, turns, deliveries, and close
    header = records[0] if "call_id" in records[0] else {}
    call_id = header.get("call_id") or (log_path.stem if log_path else "call")
    snapshot_id = header.get("snapshot_id")

    delivery_records: list[dict[str, Any]] = []
    close_record: Optional[dict[str, Any]] = None
    turn_records: list[dict[str, Any]] = []
    mode_records: list[dict[str, Any]] = []

    for r in records:
        if "slug" in r and "ending" in r:
            delivery_records.append(r)
        elif "stop" in r:
            close_record = r
        elif "turn_n" in r and ("class" in r or "turn_class" in r):
            turn_records.append(r)
        elif "mode" in r and len(r) == 1:
            mode_records.append(r)

    # 2. Extract answered box vector (ONLY confirmed ANSWER lines; PROPOSAL lines are ignored)
    box_vector: dict[str, str] = {}
    for r in turn_records:
        cls_name = str(r.get("turn_class") or r.get("class") or "").upper().strip()
        if cls_name == "PROPOSAL":
            continue
        if cls_name == "ANSWER":
            box = r.get("box")
            val = r.get("value")
            if box and val:
                box_vector[str(box)] = str(val)

    # 3. Resolve corpus if needed
    active_corpus = corpus
    if active_corpus is None:
        active_corpus = _load_corpus_for_snapshot(snapshot_id, custom_snapshot=snapshot)

    # --- Condition 2: System hung up unprompted ---
    # Close reason shows system-side close before terminal
    if close_record is not None:
        stop_reason = close_record.get("stop")
        if stop_reason in ("hangup", "system_hangup", "unprompted_hangup", "error", "internal_error", "crash"):
            return JudgeResult(
                passed=False,
                call_id=call_id,
                reason=f"system hung up unprompted (close reason '{stop_reason}' shows system-side close before terminal)",
                log_path=log_path,
            )
        if stop_reason not in STOP_REASONS:
            return JudgeResult(
                passed=False,
                call_id=call_id,
                reason=f"system hung up unprompted (invalid close reason '{stop_reason}')",
                log_path=log_path,
            )
        # If stop reason claims survivors_le_4 but zero schemes were delivered and no readback happened
        if stop_reason == STOP_LE_4_SURVIVORS and not delivery_records:
            return JudgeResult(
                passed=False,
                call_id=call_id,
                reason="ended before a terminal state (stop reason is survivors_le_4 but no schemes delivered)",
                log_path=log_path,
            )

    # --- Condition 3: Ended before a terminal state ---
    # T04: "read-back started · honest dead-end delivered · keypad-only fallback delivered"
    readback_started = len(delivery_records) > 0
    honest_dead_end = (
        close_record is not None
        and close_record.get("stop") == STOP_ZERO_SURVIVORS
    )
    ordinary_terminal = (
        close_record is not None
        and close_record.get("stop") in STOP_REASONS
    )

    if not readback_started and not honest_dead_end and not ordinary_terminal:
        return JudgeResult(
            passed=False,
            call_id=call_id,
            reason="ended before a terminal state (call terminated mid-air without reaching a terminal)",
            log_path=log_path,
        )

    # --- Condition 1: Untrue claims ---
    # (a) Benefit/document claim outside the corpus
    for d in delivery_records:
        slug = d.get("slug")
        ending = d.get("ending")
        sections = d.get("sections", [])

        if not slug or not isinstance(sections, list) or not sections:
            return JudgeResult(
                passed=False,
                call_id=call_id,
                reason=f"untrue: delivery record for '{slug}' has missing or empty sections: {sections}",
                log_path=log_path,
            )

        for sec in sections:
            if sec not in ALLOWED_SECTIONS:
                return JudgeResult(
                    passed=False,
                    call_id=call_id,
                    reason=f"untrue: benefit/document claim outside corpus (unsupported section '{sec}' for scheme '{slug}')",
                    log_path=log_path,
                )

        if active_corpus is not None:
            corpus_slugs = getattr(active_corpus, "_scheme_ids", ())
            if slug not in corpus_slugs:
                return JudgeResult(
                    passed=False,
                    call_id=call_id,
                    reason=f"untrue: named scheme '{slug}' outside corpus",
                    log_path=log_path,
                )

    # (b) Nearest read as matches
    for d in delivery_records:
        slug = d.get("slug")
        ending = d.get("ending")
        sections = d.get("sections", [])

        if ending == "nearest":
            # T18: Nearest reads summary ONLY, no section_menu offers
            if set(sections) != {"summary"}:
                return JudgeResult(
                    passed=False,
                    call_id=call_id,
                    reason=f"untrue: nearest read as matches (nearest scheme '{slug}' read sections beyond summary: {sections})",
                    log_path=log_path,
                )

    # (c) Dead-end without the widening step
    is_dead_end = (
        (close_record is not None and close_record.get("stop") == STOP_ZERO_SURVIVORS)
        or any(d.get("ending") in ("nearest", "empty") for d in delivery_records)
    )
    if is_dead_end:
        answered_soft = [
            b for b, v in box_vector.items()
            if b in WIDENING_ORDER and v not in (None, UNASKED, UNKNOWN, "UNKNOWN")
        ]
        ladder_rung = close_record.get("ladder_rung") if close_record else None
        if answered_soft and (ladder_rung is None or ladder_rung == 0):
            return JudgeResult(
                passed=False,
                call_id=call_id,
                reason=f"untrue: dead-end without the widening step (answered soft boxes {answered_soft} but ladder_rung is {ladder_rung})",
                log_path=log_path,
            )

    # (d) Named scheme not in survivors (and nearest read as matches)
    if active_corpus is not None and delivery_records:
        for d in delivery_records:
            slug = d.get("slug")
            ending = d.get("ending")

            if ending in ("direct_match", "overflow"):
                raw_surv_indices = Filter.survivors(box_vector, active_corpus)
                raw_surv_slugs = [active_corpus.scheme_id(ix) for ix in raw_surv_indices]

                if slug not in raw_surv_slugs:
                    return JudgeResult(
                        passed=False,
                        call_id=call_id,
                        reason=f"untrue: named scheme '{slug}' not in survivors for answered vector {box_vector}",
                        log_path=log_path,
                    )
                # Check speaking rule
                if not Filter.speakable(slug, box_vector, active_corpus):
                    return JudgeResult(
                        passed=False,
                        call_id=call_id,
                        reason=f"untrue: named scheme '{slug}' violates speaking rule for vector {box_vector}",
                        log_path=log_path,
                    )

            elif ending == "widened_match":
                ladder_rung = close_record.get("ladder_rung", 1) if close_record else 1
                widened_vector = dict(box_vector)
                dropped_count = 0
                for soft_b in WIDENING_ORDER:
                    if widened_vector.get(soft_b) not in (None, UNASKED, UNKNOWN, "UNKNOWN"):
                        widened_vector.pop(soft_b, None)
                        dropped_count += 1
                        if dropped_count >= ladder_rung:
                            break
                widened_survs = [active_corpus.scheme_id(ix) for ix in Filter.survivors(widened_vector, active_corpus)]
                if slug not in widened_survs:
                    return JudgeResult(
                        passed=False,
                        call_id=call_id,
                        reason=f"untrue: named scheme '{slug}' not in widened survivors (ladder rung {ladder_rung})",
                        log_path=log_path,
                    )
                if not Filter.speakable(slug, widened_vector, active_corpus):
                    return JudgeResult(
                        passed=False,
                        call_id=call_id,
                        reason=f"untrue: named scheme '{slug}' violates speaking rule under widened vector",
                        log_path=log_path,
                    )

            elif ending == "nearest":
                # Ensure it belongs to nearest schemes
                nearest_indices = Filter.nearest(box_vector, active_corpus)
                nearest_slugs = [active_corpus.scheme_id(ix) for ix in nearest_indices]
                if slug not in nearest_slugs:
                    return JudgeResult(
                        passed=False,
                        call_id=call_id,
                        reason=f"untrue: nearest scheme '{slug}' not in valid nearest set {nearest_slugs}",
                        log_path=log_path,
                    )

    # --- All PASS rules satisfied ---
    slugs_delivered = [d.get("slug", "") for d in delivery_records]
    if delivery_records:
        ending = delivery_records[0].get("ending", "delivered")
        if ending == "nearest":
            rung = close_record.get("ladder_rung", 0) if close_record else 0
            reason = f"dead-end through full ladder (rung {rung}) with {len(slugs_delivered)} nearest schemes labelled nearest ({', '.join(slugs_delivered)})"
        else:
            reason = f"delivered {len(slugs_delivered)} {ending} schemes honestly ({', '.join(slugs_delivered)})"
    elif honest_dead_end:
        rung = close_record.get("ladder_rung", 0) if close_record else 0
        reason = f"honest empty dead-end through full ladder (rung {rung})"
    else:
        stop = close_record.get("stop") if close_record else "terminal"
        mode = close_record.get("mode") if close_record else "normal"
        reason = f"ordinary terminal reached ({stop}, mode={mode})"

    return JudgeResult(passed=True, call_id=call_id, reason=reason, log_path=log_path)


def judge_logs_dir(
    target_path: Path | str,
    snapshot: Optional[str] = None,
    corpus: Optional[Corpus] = None,
) -> list[JudgeResult]:
    """Judge all log files in a directory (or a single log file)."""
    p = Path(target_path)
    if p.is_file():
        return [judge_call_log(p, corpus=corpus, snapshot=snapshot)]

    if not p.is_dir():
        print(f"Error: Target path does not exist: {p}", file=sys.stderr)
        return []

    # Gather .jsonl log files, excluding non-call logs
    log_files = sorted(
        [
            f for f in p.glob("*.jsonl")
            if not f.name.endswith("_usage.jsonl") and not f.name.startswith("muse_") and not f.name.startswith("stt_") and not f.name.startswith("groq_")
        ]
    )

    results: list[JudgeResult] = []
    for f in log_files:
        res = judge_call_log(f, corpus=corpus, snapshot=snapshot)
        results.append(res)
    return results


def run_judge(target_path: Path | str, snapshot: Optional[str] = None) -> int:
    """CLI runner printing per-call PASS/FAIL + one-line reason, summary counts, exit 1 if any FAIL."""
    results = judge_logs_dir(target_path, snapshot=snapshot)
    if not results:
        print(f"Error: No valid JSONL logs found in {target_path}", file=sys.stderr)
        return 1

    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    failed_count = total - passed_count

    print("=" * 70)
    print(f"HAQDAAR v2 Delivery Log Judge — {total} Calls Evaluated")
    print("Mode: Offline log analysis (D9 delivery records + turn lines)")
    print("=" * 70)

    for idx, r in enumerate(results, 1):
        status = "PASS" if r.passed else "FAIL"
        fname = r.log_path.name if r.log_path else r.call_id
        print(f"[{idx:02d}/{total}] {status:<4} {fname:<25} {r.reason}")

    print("\n" + "=" * 70)
    print("JUDGE SUMMARY")
    print("=" * 70)
    print(f"Total Calls: {total}")
    print(f"PASS:        {passed_count}/{total} ({(passed_count/total)*100:.1f}%)")
    print(f"FAIL:        {failed_count}/{total} ({(failed_count/total)*100:.1f}%)")
    print("=" * 70)

    if failed_count > 0:
        print(f"\n{failed_count} CALL(S) FAILED:")
        for r in results:
            if not r.passed:
                fname = r.log_path.name if r.log_path else r.call_id
                print(f"  - {fname}: {r.reason}")
        return 1

    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="HAQDAAR Delivery Log Judge")
    parser.add_argument("logs", help="Path to logs directory or single JSONL log file")
    parser.add_argument("--snapshot", default=None, help="Snapshot id or directory to use for corpus evaluation")
    args = parser.parse_args(argv)

    return run_judge(args.logs, snapshot=args.snapshot)


if __name__ == "__main__":
    sys.exit(main())
