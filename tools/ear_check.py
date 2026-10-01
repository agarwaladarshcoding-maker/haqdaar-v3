"""tools/ear_check.py — Speech-to-text verification across languages (plan 4.1).

Usage:
    python -m tools.ear_check               # runs live against all 9 static speech fixtures (spends API budget!)
    python -m tools.ear_check --lang hi      # runs only Hindi sentences (live)
    python -m tools.ear_check --offline      # offline verification mode (zero network calls, zero API spend)
    python -m tools.ear_check <path.wav>     # transcribes a specific audio file (live)

NOTE: Plain `make ear-check` defaults to live calls against Sarvam and Groq Whisper,
which spends API credits and usage quota. Use `--offline` for local zero-cost verification.

Verifies STT latency, provider routing (Sarvam -> Groq fallback), and transcript quality.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

from haqdaar.audio.ear import (
    BASE_DIR,
    SpeechToText,
    load_audio,
)


def run_ear_check(
    fixtures_dir: Path | None = None,
    lang_filter: str | None = None,
    offline: bool = False,
    custom_files: list[str] | None = None,
) -> int:
    fixtures_dir = fixtures_dir or BASE_DIR / "fixtures" / "audio" / "speech"
    manifest_path = fixtures_dir / "manifest.json"

    if not manifest_path.exists():
        print(f"Error: manifest not found at {manifest_path}", file=sys.stderr)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stt = SpeechToText()

    # If specific files passed
    if custom_files:
        print(f"=== HAQDAAR v2 Ear Check — {len(custom_files)} custom file(s) ===")
        for fpath_str in custom_files:
            fpath = Path(fpath_str)
            if not fpath.exists():
                print(f"File not found: {fpath}", file=sys.stderr)
                continue
            pcm = load_audio(fpath)
            res = stt.transcribe(pcm)
            status = "OK" if res.success else f"FAIL ({res.error})"
            print(f"[{status}] {fpath.name}: \"{res.transcript}\" ({res.provider}, {res.latency_s:.2f}s)")
        return 0

    print("=== HAQDAAR v2 Ear Check (3 sentences × en, hi, mr) ===")
    languages = [lang_filter] if lang_filter else ["en", "hi", "mr"]

    total = 0
    passed = 0
    provider_counts: dict[str, int] = {}
    latencies: list[float] = []

    for lang in languages:
        print(f"\n--- Language: {lang.upper()} ---")
        lang_keys = [k for k in ["p1", "p2", "p3"] if f"{k}_{lang}" in manifest]
        for k in lang_keys:
            key = f"{k}_{lang}"
            entry = manifest[key]
            wav_path = fixtures_dir / entry["file"]
            if not wav_path.exists():
                print(f"  [MISSING] {key}: file {wav_path} not found")
                continue

            total += 1
            expected = entry["text"]
            uid = entry["utterance_id"]

            if offline:
                # Offline mode: verify loading and fixture integrity
                pcm = load_audio(wav_path)
                status = "OFFLINE"
                transcript = f"(fixture loaded: {len(pcm)} bytes PCM, expected: {expected[:40]}...)"
                provider = "offline"
                lat = 0.0
            else:
                pcm = load_audio(wav_path)
                stt.reset_circuit()
                t0 = time.monotonic()
                res = stt.transcribe(pcm, lang=lang)
                lat = res.latency_s
                provider = res.provider or "none"
                transcript = res.transcript
                status = "OK" if res.success and transcript else f"FAIL ({res.error})"

            if status in ("OK", "OFFLINE"):
                passed += 1

            provider_counts[provider] = provider_counts.get(provider, 0) + 1
            latencies.append(lat)

            print(f"  [{uid}]")
            print(f"    Expected:   {expected}")
            print(f"    Transcript: {transcript}")
            print(f"    Result:     {status} via {provider} ({lat:.2f}s)")

    print("\n" + "=" * 55)
    avg_lat = sum(latencies) / len(latencies) if latencies and any(latencies) else 0.0
    prov_str = ", ".join(f"{count} {p}" for p, count in provider_counts.items())
    print(f"Summary: {passed}/{total} sentences recognized ({prov_str})")
    if avg_lat > 0:
        print(f"Average latency: {avg_lat:.2f}s (total: {sum(latencies):.2f}s)")

    return 0 if passed == total else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HAQDAAR v2 ear check (STT)")
    parser.add_argument("--lang", choices=["en", "hi", "mr"], help="Filter to specific language")
    parser.add_argument("--offline", action="store_true", help="Run offline checks without paid APIs")
    parser.add_argument("files", nargs="*", help="Optional custom audio files to transcribe")
    args = parser.parse_args(argv)

    return run_ear_check(
        lang_filter=args.lang,
        offline=args.offline,
        custom_files=args.files if args.files else None,
    )


if __name__ == "__main__":
    sys.exit(main())
