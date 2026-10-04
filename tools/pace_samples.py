"""tools/pace_samples.py — the same lines at three speeds, to pick a pace by ear (step 7.7a).

    python -m tools.pace_samples                       # slower 0.9, now 1.0, faster 1.1
    python -m tools.pace_samples --slower 0.85 --faster 1.15

Writes scratch/pace-samples/<line>.<lang>.<slower|now|faster>.wav and prints a table.
Plays nothing and calls no API. `stretch` is only a mock-up of the speed; the final voice
comes from a re-record at the chosen pace, so quality will differ.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from haqdaar.audio.render import BASE_DIR, clip_path, real_texts, stretch, ulaw_to_wav
from haqdaar.contracts import tunables

OUT_DIR = BASE_DIR / "scratch" / "pace-samples"
LANGS = ("en", "hi", "mr")
# (name used in the file, text kind, ref). The card is a long summary so the pace is easy to hear.
LINES = (
    ("greeting", "line", "opener_prompt"),
    ("card", "chunk", "pm-kisan/summary"),
    ("menu", "line", "section_menu"),
)


def write_samples(
    name: str, lang: str, ulaw: bytes, out_dir: Path, slower: float, faster: float
) -> list[tuple[str, float, float]]:
    """Write the three WAVs for one clip. Returns (file name, speed, seconds) rows."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, speed in (("slower", slower), ("now", 1.0), ("faster", faster)):
        clip = ulaw if speed == 1.0 else stretch(ulaw, speed)
        path = out_dir / f"{name}.{lang}.{label}.wav"
        path.write_bytes(ulaw_to_wav(clip))
        rows.append((path.name, speed, len(clip) / tunables.SAMPLE_RATE))
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--slower", type=float, default=0.9)
    ap.add_argument("--faster", type=float, default=1.1)
    args = ap.parse_args(argv)

    audio_dir = BASE_DIR / tunables.AUDIO_DIR
    texts = {(t.lang, t.kind, t.ref): t for t in real_texts()}
    rows = []
    for name, kind, ref in LINES:
        for lang in LANGS:
            t = texts[(lang, kind, ref)]
            path = clip_path(audio_dir, t.key)
            if not path.exists():
                print(f"missing clip: {kind} {ref} {lang}")
                return 1
            rows += write_samples(name, lang, path.read_bytes(), OUT_DIR, args.slower, args.faster)

    print(f"{'file':32} {'speed':>5} {'seconds':>8}")
    for fname, speed, secs in rows:
        print(f"{fname:32} {speed:5.2f} {secs:8.2f}")
    print(f"written to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
