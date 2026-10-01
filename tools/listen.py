"""tools/listen.py — hear rendered clips, with their text printed first (plan 2.1).

    python -m tools.listen hi 5         # 5 random Hindi clips
    python -m tools.listen mr lines     # every Marathi fixed line
    python -m tools.listen all 1        # the trilingual greeting
    python -m tools.listen cards hi 10  # 10 Hindi card-chunk clips from audio-ready schemes
    python -m tools.listen cards hi all # all Hindi card-chunk clips from audio-ready schemes

Plays through macOS `afplay`. Clips not rendered yet are listed as missing.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

from haqdaar.audio.render import BASE_DIR, clip_path, has_clip, real_texts, ulaw_to_wav
from haqdaar.contracts import tunables


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2

    audio_dir = BASE_DIR / tunables.AUDIO_DIR

    if argv[0] == "cards":
        if len(argv) != 3:
            print("Usage: python -m tools.listen cards <L> <N>  (L in {hi, mr})")
            return 2
        lang, how = argv[1], argv[2]
        if lang not in ("hi", "mr"):
            print(f"cards mode language must be in {{hi, mr}}, got: {lang}")
            return 2

        current_file = BASE_DIR / "snapshots" / "CURRENT"
        if not current_file.exists():
            print("no snapshots/CURRENT found")
            return 1
        snap_id = current_file.read_text(encoding="utf-8").strip()
        snap_schemes_path = BASE_DIR / "snapshots" / snap_id / "schemes.jsonl"
        if not snap_schemes_path.exists():
            print(f"no snapshot schemes at {snap_schemes_path}")
            return 1

        with snap_schemes_path.open(encoding="utf-8") as f:
            snap_ids = set(json.loads(line)["scheme_id"] for line in f if line.strip())

        texts = [
            t
            for t in real_texts()
            if t.kind == "chunk" and t.lang == lang and t.ref.split("/")[0] in snap_ids
        ]
        if how == "all":
            picked = texts
        else:
            picked = random.sample(texts, min(int(how), len(texts)))
    else:
        if len(argv) != 2:
            print(__doc__)
            return 2
        lang, how = argv
        texts = [t for t in real_texts() if t.lang == lang]
        if how == "lines":
            picked = [t for t in texts if t.kind == "line"]
        elif how == "all":
            picked = texts
        else:
            picked = random.sample(texts, min(int(how), len(texts)))

    for n, item in enumerate(picked, 1):
        print(f"[{n}/{len(picked)}] {item.kind} {item.ref}")
        print(f"    {item.text}")
        if not has_clip(audio_dir, item.key):
            print("    (missing: not rendered yet)")
            continue
        wav = ulaw_to_wav(clip_path(audio_dir, item.key).read_bytes())
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            f.write(wav)
            f.flush()
            subprocess.run(["afplay", f.name], check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())

