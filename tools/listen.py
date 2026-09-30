"""tools/listen.py — hear rendered clips, with their text printed first (plan 2.1).

    python -m tools.listen hi 5        # 5 random Hindi clips
    python -m tools.listen mr lines    # every Marathi fixed line
    python -m tools.listen all 1       # the trilingual greeting

Plays through macOS `afplay`. Clips not rendered yet are listed as missing.
"""
from __future__ import annotations

import random
import subprocess
import sys
import tempfile
from pathlib import Path

from haqdaar.audio.render import BASE_DIR, clip_path, has_clip, real_texts, ulaw_to_wav
from haqdaar.contracts import tunables


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print(__doc__)
        return 2
    lang, how = argv
    audio_dir = BASE_DIR / tunables.AUDIO_DIR
    texts = [t for t in real_texts() if t.lang == lang]
    if how == "lines":
        picked = [t for t in texts if t.kind == "line"]
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
