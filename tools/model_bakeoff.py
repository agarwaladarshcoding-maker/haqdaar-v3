"""tools/model_bakeoff.py — 30-utterance Model Client & Span Guard Bake-Off.

Usage:
    python -m tools.model_bakeoff               # runs against 30 fixtures with faked HTTP (zero API spend)
    python -m tools.model_bakeoff --live        # runs live against Groq API (owner only, spends Groq tokens)
    python -m tools.model_bakeoff --model <id>  # live evaluation on a specific Groq model

Computes and prints:
- Extraction accuracy (exact stamp matches against ground truth)
- Span guard survival & filtering
- Latency statistics (min, mean, p50, p95, max)
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from haqdaar.contracts.types import Stamp
from haqdaar.model.client import GroqModelClient, ModelClientResponse
from haqdaar.model.router import Model

BASE_DIR = Path(__file__).resolve().parent.parent


def compute_percentile(values: list[float], pct: float) -> float:
    """Compute percentile value without external dependencies."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    d = k - f
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * d


class FakedFixtureClient(GroqModelClient):
    """Faked HTTP client answering each fixture with expected stamps + testing span guard."""

    def __init__(self, utterances: list[dict[str, Any]]) -> None:
        super().__init__(api_key="fake_offline_key")
        self.utterance_map = {u["transcript"].strip(): u for u in utterances}

    def call(self, messages: list[dict[str, str]], task: str = "model_router") -> ModelClientResponse:
        t0 = time.monotonic()
        # Find transcript from user message
        user_content = messages[-1]["content"]
        matched_u = None
        for tx, u in self.utterance_map.items():
            if tx in user_content:
                matched_u = u
                break

        if not matched_u:
            return ModelClientResponse(success=True, data={"stamps": []}, latency_s=0.005)

        stamps_data = [
            {"box": s["box"], "value": s["value"], "span": s["span"]}
            for s in matched_u.get("expected_stamps", [])
        ]

        # Add a simulated hallucinated stamp without transcript provenance
        # to verify that the span guard actively catches and drops it
        hallucinated_stamp = {"box": "income_band", "value": "<100000", "span": "hallucinated low income"}
        stamps_with_hallucination = stamps_data + [hallucinated_stamp]

        latency = time.monotonic() - t0 + 0.008  # ~8ms simulated latency
        return ModelClientResponse(
            success=True,
            data={"stamps": stamps_with_hallucination},
            latency_s=latency,
            prompt_tokens=350,
            completion_tokens=45,
        )


def load_bakeoff_utterances() -> list[dict[str, Any]]:
    """Load the 30 speech fixtures from fixtures/audio/speech/manifest.json."""
    manifest_path = BASE_DIR / "fixtures" / "audio" / "speech" / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"{manifest_path} not found")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    utterances = []
    for k, v in manifest.items():
        if k in ("silence", "noise"):
            continue
        utterances.append({
            "utterance_id": v["utterance_id"],
            "lang": v["lang"],
            "transcript": v["text"],
            "expected_stamps": v.get("expected_stamps", []),
        })
    return utterances


def run_bakeoff(live: bool = False, model_name: str | None = None) -> int:
    try:
        utterances = load_bakeoff_utterances()
    except Exception as e:
        print(f"Error loading utterances: {e}", file=sys.stderr)
        return 1

    total_utterances = len(utterances)

    mode_str = f"Live Groq ({model_name or 'llama-3.3-70b-versatile'})" if live else "Offline (faked HTTP)"
    print("=" * 65)
    print(f"HAQDAAR v2 Model Bake-Off — {total_utterances} Utterances")
    print(f"Mode: {mode_str}")
    print("=" * 65)

    if live:
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            print("Error: GROQ_API_KEY not found in environment for live run.", file=sys.stderr)
            return 1
        client = GroqModelClient(api_key=api_key, model=model_name)
    else:
        client = FakedFixtureClient(utterances)

    model = Model(client=client)

    correct_utterances = 0
    total_expected_stamps = 0
    matched_stamps = 0
    hallucinations_dropped = 0
    latencies: list[float] = []

    for i, u in enumerate(utterances, 1):
        uid = u["utterance_id"]
        lang = u["lang"]
        transcript = u["transcript"]
        expected = u.get("expected_stamps", [])
        total_expected_stamps += len(expected)

        t0 = time.monotonic()
        stamps_res = model.opener(transcript, lang=lang)
        call_latency = time.monotonic() - t0
        latencies.append(call_latency)

        if isinstance(stamps_res, list):
            produced_boxes = {(s.box, str(s.value)) for s in stamps_res}
            expected_boxes = {(s["box"], str(s["value"])) for s in expected}

            # Check for hallucinated drops
            # Verify that the injected hallucination was actually dropped by SpanGuard
            if not live:
                if ("income_band", "<100000") not in produced_boxes:
                    hallucinations_dropped += 1

            # Matches
            matches = produced_boxes & expected_boxes
            matched_stamps += len(matches)

            # Regression gate: produced must equal expected exactly.
            # If produced ⊄ expected (e.g. leaked hallucinations), status is MISS.
            is_perfect = (produced_boxes == expected_boxes)
            if is_perfect:
                correct_utterances += 1
                status = "PASS"
            else:
                status = "MISS"

            summary = ", ".join(f"{s.box}={s.value}" for s in stamps_res)
            print(f"[{i:02d}/30] {uid:<6} ({lang}) {status} in {call_latency*1000:.1f}ms -> [{summary}]")
        else:
            print(f"[{i:02d}/30] {uid:<6} ({lang}) FAIL ({stamps_res.reason})")

    p50 = compute_percentile(latencies, 50)
    p95 = compute_percentile(latencies, 95)
    mean_lat = sum(latencies) / len(latencies) if latencies else 0.0

    print("\n" + "=" * 65)
    print("BAKE-OFF RESULTS SUMMARY")
    print("=" * 65)
    print(f"Total Utterances:       {total_utterances}")
    print(f"Perfect Utterances:     {correct_utterances}/{total_utterances} ({correct_utterances/total_utterances*100:.1f}%)")
    print(f"Expected Stamps:        {total_expected_stamps}")
    print(f"Matched Stamps:         {matched_stamps}/{total_expected_stamps} ({matched_stamps/total_expected_stamps*100:.1f}%)")
    print(f"Span Guard Drops:       {hallucinations_dropped} hallucinated stamps intercepted")
    print(f"Latency Mean:           {mean_lat*1000:.1f} ms")
    print(f"Latency p50:            {p50*1000:.1f} ms")
    print(f"Latency p95:            {p95*1000:.1f} ms")
    print("=" * 65)

    return 0 if correct_utterances == total_utterances else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="HAQDAAR v2 Model Bake-Off")
    parser.add_argument("--live", action="store_true", help="Run against live Groq API (owner only)")
    parser.add_argument("--model", type=str, default=None, help="Groq model ID for live evaluation")
    args = parser.parse_args()

    sys.exit(run_bakeoff(live=args.live, model_name=args.model))


if __name__ == "__main__":
    main()
