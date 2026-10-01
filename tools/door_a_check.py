"""tools/door_a_check.py

Offline top-1 accuracy check for Door A (3 forms × 30 schemes = 90 utterances).
Evaluates accuracy across English, Hindi, and Marathi spoken utterances.
Zero API cost: entirely offline using token matching, normalization, and Devanagari transliteration.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from haqdaar.engine.door_a import DoorA

BASE_DIR = Path(__file__).resolve().parent.parent


def run_door_a_check() -> int:
    utterances_path = BASE_DIR / "fixtures" / "door_a_utterances.json"
    if not utterances_path.exists():
        print(f"Error: Fixture file not found: {utterances_path}", file=sys.stderr)
        return 1

    utterances = json.loads(utterances_path.read_text(encoding="utf-8"))
    total = len(utterances)

    print("=" * 70)
    print(f"HAQDAAR v2 Door A Offline Evaluation — {total} Utterances (30 schemes × 3 forms)")
    print("Mode: Offline (exact alias fast-path + cross-script token matcher)")
    print("=" * 70)

    door_a = DoorA()

    correct = 0
    lang_stats = {"en": {"correct": 0, "total": 0}, "hi": {"correct": 0, "total": 0}, "mr": {"correct": 0, "total": 0}}
    latencies: list[float] = []
    failures = []

    for idx, u in enumerate(utterances, 1):
        slug = u["slug"]
        lang = u["lang"]
        text = u["transcript"]

        t0 = time.monotonic()
        res = door_a.match(text, lang=lang)
        lat = time.monotonic() - t0
        latencies.append(lat)

        lang_stats[lang]["total"] += 1
        predicted = res.scheme_ids[0] if (res.action == "read" and res.scheme_ids) else ""
        is_hit = (predicted == slug and res.action == "read")

        if is_hit:
            correct += 1
            lang_stats[lang]["correct"] += 1
            status = "HIT"
        else:
            status = "MISS"
            failures.append({
                "idx": idx,
                "expected": slug,
                "predicted": predicted,
                "action": res.action,
                "lang": lang,
                "text": text,
                "shortlist": res.shortlist[:3],
            })

        print(f"[{idx:02d}/90] [{lang}] {status:<4} expected={slug:<14} pred={predicted:<14} act={res.action:<13} ({lat*1000:.2f}ms)")

    overall_acc = (correct / total) * 100.0 if total else 0.0
    mean_lat = sum(latencies) / len(latencies) if latencies else 0.0

    print("\n" + "=" * 70)
    print("DOOR A EVALUATION SUMMARY")
    print("=" * 70)
    print(f"Total Utterances:   {total}")
    print(f"Top-1 Hits:         {correct}/{total} ({overall_acc:.2f}%)")
    for l in ("en", "hi", "mr"):
        c_l = lang_stats[l]["correct"]
        t_l = lang_stats[l]["total"]
        pct = (c_l / t_l * 100.0) if t_l else 0.0
        print(f"  - [{l.upper()}] Accuracy:   {c_l}/{t_l} ({pct:.2f}%)")
    print(f"Mean Latency:       {mean_lat*1000:.2f} ms")
    print("=" * 70)

    if failures:
        print(f"\n{len(failures)} MISSED UTTERANCES:")
        for f in failures:
            print(f"  #{f['idx']:02d} [{f['lang']}] Expected '{f['expected']}', got '{f['predicted']}' (action={f['action']})")
            print(f"      Text: \"{f['text']}\"")
            print(f"      Top shortlist: {f['shortlist']}")

    return 0 if overall_acc >= 90.0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Door A Offline Accuracy Check")
    args = parser.parse_args()
    sys.exit(run_door_a_check())


if __name__ == "__main__":
    main()
